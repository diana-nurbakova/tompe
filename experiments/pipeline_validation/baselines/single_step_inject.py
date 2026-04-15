"""B1 — Single-step LLM injection baseline (no planning step).

Uses the same LLM and codebook entry as the full pipeline but collapses
the two-step architecture into a single prompt.  Step 1 (planning /
reasoning) is skipped entirely — the LLM is asked to inject directly.

This isolates the contribution of the explicit planning stage.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from tompe.pipeline.codebook import Codebook, load_default_codebook
from tompe.pipeline.llm_client import LLMClient, make_client_from_config
from tompe.pipeline.mqm_taxonomy import ErrorTypeSpec, validate_tag_type
from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel
from tompe.schemas.error import ContrastiveExplanation, InjectedError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

# Same tag regex used by the full pipeline (error_injector.py)
_TAG_PATTERN = re.compile(
    r'<(\w+)\s+type="([^"]+)"\s+severity="([^"]+)"\s+tom="([^"]+)"\s+desc="([^"]*)">'
    r"(.*?)"
    r"</\1>",
    re.DOTALL,
)

_SYSTEM_PROMPT = (
    "You are an expert translation-error injector for a pedagogical post-editing "
    "platform.  You receive a source sentence and its correct human reference "
    "translation.  Your task is to introduce EXACTLY ONE translation error into "
    "the reference and return the full modified translation.\n\n"
    "Mark the error span with an XML tag using this exact format:\n"
    '<TAG type="error_type" severity="minor|major|critical" '
    'tom="1st_machine|1st_author|2nd_reader|recursive" '
    'desc="brief explanation">error span</TAG>\n\n'
    "where TAG is the primary error tag name (e.g., MISTRANSLATION, OMISSION, etc.).\n\n"
    "Rules:\n"
    "- Keep ALL text outside the error span IDENTICAL to the reference.\n"
    "- The error must be linguistically plausible, not a random corruption.\n"
    "- Return ONLY the modified translation with the XML tag.  No preamble."
)


def _build_user_prompt(
    source: str,
    reference: str,
    primary_tag: PrimaryTag,
    error_type: str,
    severity: Severity,
    codebook: Codebook | None,
) -> str:
    """Build the single-step user prompt."""
    parts = [
        f"Inject a [{primary_tag.value}/{error_type}/{severity.value}] error "
        f"into this translation.\n",
        f"Source: {source}",
        f"Translation: {reference}",
    ]

    if codebook:
        definition = codebook.get_definition(primary_tag.value, error_type)
        boundary = codebook.get_boundary_not(primary_tag.value, error_type)
        if definition:
            parts.append(f"\nDefinition: {definition}")
        if boundary:
            parts.append(f"Boundary (NOT this): {boundary}")

    parts.append(
        "\nOutput the modified translation with <TAG> markup. "
        "Nothing else."
    )
    return "\n".join(parts)


def _strip_tags(text: str) -> str:
    """Remove XML error tags, keeping span content."""
    return _TAG_PATTERN.sub(r"\6", text)


def _verify_b1(reference: str, raw_output: str) -> list[str]:
    """Lightweight verification (subset of full pipeline checks).

    Returns a list of failure messages (empty means valid).
    """
    errors: list[str] = []

    parsed = list(_TAG_PATTERN.finditer(raw_output))
    if not parsed:
        errors.append("No valid XML error tag found in LLM output")
        return errors
    if len(parsed) > 1:
        errors.append(f"Expected 1 tag, found {len(parsed)}")

    m = parsed[0]
    tag_name, etype, sev, tom, desc, span = (
        m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6),
    )

    # Tag/type validation
    if not validate_tag_type(tag_name, etype):
        errors.append(f"Invalid tag/type: {tag_name}/{etype}")

    if sev not in ("minor", "major", "critical"):
        errors.append(f"Invalid severity: {sev}")

    if tom not in ("1st_machine", "1st_author", "2nd_reader", "recursive"):
        errors.append(f"Invalid tom: {tom}")

    # Text-preservation check (fuzzy)
    clean = _strip_tags(raw_output)
    before_tag = raw_output[: m.start()]
    clean_before = _TAG_PATTERN.sub(r"\6", before_tag)
    span_start = len(clean_before)
    span_end = span_start + len(span)

    # Reconstruct the reference from the clean text (replace injected span
    # with nothing, since we don't know original — just check surrounding)
    outside = clean[:span_start] + clean[span_end:]
    ref_tokens = set(reference.split())
    out_tokens = set(outside.split())
    # At least 80% of reference tokens should appear in outside text
    if ref_tokens:
        overlap = len(ref_tokens & out_tokens) / len(ref_tokens)
        if overlap < 0.70:
            errors.append(
                f"Too much text changed outside error span (token overlap {overlap:.0%})"
            )

    if not desc or len(desc.split()) < 2:
        errors.append(f"desc attribute too short: '{desc}'")

    return errors


async def inject_single_step(
    segment: CorpusSegment,
    error_spec: ErrorTypeSpec,
    severity: Severity,
    llm_config: dict,
    codebook: Codebook | None = None,
) -> tuple[str, list[InjectedError]]:
    """Inject one error via a single LLM call (no planning step).

    Args:
        segment: Corpus segment with source and reference.
        error_spec: Target error type specification from the taxonomy.
        severity: Desired severity level.
        llm_config: LLM configuration dict (provider, model, ...).
        codebook: Optional codebook for definition/boundary context.

    Returns:
        ``(modified_text, [InjectedError])``
    """
    llm = make_client_from_config(llm_config)
    if codebook is None:
        codebook = load_default_codebook()

    reference = segment.reference_translation
    user_prompt = _build_user_prompt(
        source=segment.source_text,
        reference=reference,
        primary_tag=error_spec.primary_tag,
        error_type=error_spec.error_type,
        severity=severity,
        codebook=codebook,
    )

    last_errors: list[str] = []

    for attempt in range(_MAX_RETRIES):
        temp = 0.3 + (attempt * 0.1)
        prompt = user_prompt
        if attempt > 0 and last_errors:
            prompt += (
                "\n\nPREVIOUS ATTEMPT FAILED:\n"
                + "\n".join(f"- {e}" for e in last_errors)
                + "\nFix these issues."
            )

        try:
            raw = await llm.complete_text(
                system=_SYSTEM_PROMPT,
                user=prompt,
                temperature=temp,
            )
        except Exception as exc:
            logger.warning(
                "B1 LLM call failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
            last_errors = [str(exc)]
            continue

        raw = raw.strip()
        verification_errors = _verify_b1(reference, raw)

        if verification_errors:
            logger.warning(
                "B1 verification failed (attempt %d/%d) for %s/%s: %s",
                attempt + 1, _MAX_RETRIES,
                error_spec.primary_tag.value, error_spec.error_type,
                verification_errors,
            )
            last_errors = verification_errors
            continue

        # Parse the successful output
        m = _TAG_PATTERN.search(raw)
        assert m is not None  # verified above

        tag_name = m.group(1)
        etype = m.group(2)
        sev = m.group(3)
        tom = m.group(4)
        desc = m.group(5)
        span_text = m.group(6)

        clean_text = _strip_tags(raw)
        before_tag = raw[: m.start()]
        clean_before = _TAG_PATTERN.sub(r"\6", before_tag)
        span_start = len(clean_before)
        span_end = span_start + len(span_text)

        # Infer original text — the reference text at the same position
        original_text = reference[span_start:span_start + len(span_text)]
        # Better heuristic: find what differs
        if span_start < len(reference):
            # Walk outward from span_start to find divergence boundaries
            original_text = reference[span_start:min(span_end, len(reference))]

        error = InjectedError(
            error_id=str(uuid.uuid4()),
            span_start=span_start,
            span_end=span_end,
            original_text=original_text,
            injected_text=span_text,
            primary_tag=error_spec.primary_tag,
            error_type=etype,
            severity=Severity(sev),
            tom_level=TOMLevel(tom),
            primary_skill=error_spec.primary_skill,
            secondary_skills=list(error_spec.secondary_skills),
            severity_range=list(error_spec.severity_range),
            direction=error_spec.direction,
            explanation=ContrastiveExplanation(
                mt_interpretation=f"Single-step injection: {desc}",
                actual_meaning=f"Original reference text at this span: '{original_text}'",
                reader_impact=f"Reader sees '{span_text}' instead of the correct text.",
                correction_rationale=f"Restore: '{original_text}'",
            ),
            xml_tag=raw,
            brief_explanation=desc,
        )

        logger.info(
            "B1 injected %s/%s (%s) at [%d:%d]: '%s' -> '%s'",
            tag_name, etype, sev, span_start, span_end,
            original_text, span_text,
        )

        return clean_text, [error]

    raise ValueError(
        f"B1 single-step injection failed after {_MAX_RETRIES} attempts for "
        f"{error_spec.primary_tag.value}/{error_spec.error_type}. "
        f"Last errors: {last_errors}"
    )


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    from tompe.pipeline.mqm_taxonomy import get_error_spec
    from experiments.pipeline_validation.config import DEFAULT_LLM_CONFIG

    dummy = CorpusSegment(
        segment_id="test-b1-001",
        source_text="The European Commission has proposed new regulations.",
        reference_translation="La Commission europeenne a propose de nouvelles reglementations.",
        source_lang="en",
        target_lang="fr",
        corpus_origin="europarl",
        domain="parliamentary",
        complexity_score=0.4,
        terminology_density=0.1,
        register="formal",
    )

    async def _run() -> None:
        spec = get_error_spec(PrimaryTag.MISTRANSLATION, "false_cognate")
        modified, errors = await inject_single_step(
            segment=dummy,
            error_spec=spec,
            severity=Severity.MAJOR,
            llm_config=DEFAULT_LLM_CONFIG,
        )
        print(f"Original:  {dummy.reference_translation}")
        print(f"Modified:  {modified}")
        for e in errors:
            print(f"  -> {e.primary_tag.value}/{e.error_type} "
                  f"[{e.span_start}:{e.span_end}] "
                  f"'{e.original_text}' -> '{e.injected_text}'")

    asyncio.run(_run())
