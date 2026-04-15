"""B2 — Unconstrained LLM injection baseline (no codebook guidance).

Same LLM as the full pipeline but with a FAVA-adapted open-ended prompt.
No codebook definitions, no few-shot examples, no explicit error-type
targeting.  The LLM is simply asked to introduce a "subtle translation
error" and mark it with ``<ERROR>`` tags.

This isolates the contribution of codebook-guided, taxonomy-constrained
injection.
"""

from __future__ import annotations

import logging
import re
import uuid
from difflib import SequenceMatcher

from tompe.pipeline.llm_client import make_client_from_config
from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel
from tompe.schemas.error import ContrastiveExplanation, InjectedError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

_ERROR_TAG_RE = re.compile(r"<ERROR>(.*?)</ERROR>", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are an expert in translation quality assessment.  You will receive "
    "a source sentence and its correct human reference translation.  Your task "
    "is to introduce a subtle translation error into the reference.\n\n"
    "Guidelines:\n"
    "- The error should be plausible — a native reader should not immediately "
    "notice it.\n"
    "- Do NOT introduce surface-level errors like typos or grammar mistakes.\n"
    "- Focus on meaning-level errors: wrong word sense, subtle mistranslation, "
    "shifted nuance, omitted qualifier, etc.\n"
    "- Keep ALL other text IDENTICAL to the original translation.\n"
    "- Mark the error span with <ERROR>...</ERROR> tags.\n"
    "- Return ONLY the modified translation with the <ERROR> tags.  "
    "No preamble, no explanation."
)


def _build_user_prompt(source: str, reference: str) -> str:
    parts = [
        "Introduce a subtle translation error into this text.",
        "",
        f"Source: {source}",
        f"Translation: {reference}",
        "",
        "Output the modified translation. Mark the error span with <ERROR> tags.",
    ]
    return "\n".join(parts)


def _guess_primary_tag(original_span: str, injected_span: str) -> PrimaryTag:
    """Best-guess PrimaryTag based on what changed between original and injected spans."""
    if not injected_span.strip():
        return PrimaryTag.OMISSION
    if not original_span.strip():
        return PrimaryTag.ADDITION

    # Check token-level overlap
    orig_tokens = set(original_span.lower().split())
    inj_tokens = set(injected_span.lower().split())

    if orig_tokens == inj_tokens:
        # Same tokens, different order
        return PrimaryTag.GRAMMAR

    overlap = orig_tokens & inj_tokens
    if not overlap:
        # Completely different words — likely a mistranslation
        return PrimaryTag.MISTRANSLATION

    # Partial overlap — could be style or mistranslation
    ratio = len(overlap) / max(len(orig_tokens), len(inj_tokens))
    if ratio > 0.5:
        return PrimaryTag.STYLE
    return PrimaryTag.MISTRANSLATION


def _guess_tom_level(tag: PrimaryTag) -> TOMLevel:
    """Assign a plausible ToM level based on error category."""
    if tag in (PrimaryTag.GRAMMAR, PrimaryTag.SPELLING, PrimaryTag.PUNCTUATION):
        return TOMLevel.FIRST_ORDER_MACHINE
    if tag in (PrimaryTag.OMISSION, PrimaryTag.ADDITION):
        return TOMLevel.FIRST_ORDER_AUTHOR
    if tag in (PrimaryTag.STYLE, PrimaryTag.TERMINOLOGY, PrimaryTag.LOCALE):
        return TOMLevel.SECOND_ORDER_READER
    return TOMLevel.FIRST_ORDER_MACHINE


def _guess_skill(tag: PrimaryTag) -> SkillID:
    """Map primary tag to most likely primary skill."""
    mapping = {
        PrimaryTag.MISTRANSLATION: SkillID.S3,
        PrimaryTag.OMISSION: SkillID.S4,
        PrimaryTag.ADDITION: SkillID.S4,
        PrimaryTag.UNTRANSLATED: SkillID.S4,
        PrimaryTag.GRAMMAR: SkillID.S2,
        PrimaryTag.TERMINOLOGY: SkillID.S5,
        PrimaryTag.STYLE: SkillID.S6,
        PrimaryTag.LOCALE: SkillID.S6,
        PrimaryTag.SPELLING: SkillID.S1,
        PrimaryTag.PUNCTUATION: SkillID.S1,
    }
    return mapping.get(tag, SkillID.S3)


def _verify_b2(reference: str, raw_output: str) -> list[str]:
    """Verify the unconstrained injection output.

    Returns a list of failure messages (empty means valid).
    """
    errors: list[str] = []

    matches = list(_ERROR_TAG_RE.finditer(raw_output))
    if not matches:
        errors.append("No <ERROR>...</ERROR> tag found in LLM output")
        return errors

    if len(matches) > 2:
        errors.append(f"Too many <ERROR> tags: found {len(matches)}, expected 1")

    # Strip tags and check text preservation
    clean = _ERROR_TAG_RE.sub(r"\1", raw_output).strip()
    # The clean text should be similar length to reference
    len_ratio = len(clean) / max(len(reference), 1)
    if len_ratio < 0.5 or len_ratio > 2.0:
        errors.append(
            f"Output length ratio suspicious: {len_ratio:.2f} "
            f"(clean={len(clean)}, ref={len(reference)})"
        )

    # Token overlap check
    ref_tokens = set(reference.split())
    out_tokens = set(clean.split())
    if ref_tokens:
        overlap = len(ref_tokens & out_tokens) / len(ref_tokens)
        if overlap < 0.60:
            errors.append(
                f"Too much text changed (token overlap {overlap:.0%}, need >= 60%)"
            )

    return errors


def _find_original_span(reference: str, clean_output: str, span_start: int, span_end: int) -> str:
    """Attempt to recover the original text that was replaced by the error span.

    Uses SequenceMatcher to align the reference with the clean output.
    """
    matcher = SequenceMatcher(None, reference, clean_output)
    # Find the block in the reference corresponding to the injected region
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace" and j1 <= span_start < j2:
            return reference[i1:i2]
        if tag == "equal" and j1 <= span_start and span_end <= j2:
            offset = span_start - j1
            return reference[i1 + offset : i1 + offset + (span_end - span_start)]

    # Fallback: assume same position in reference
    return reference[span_start : min(span_end, len(reference))]


async def inject_unconstrained(
    segment: CorpusSegment,
    llm_config: dict,
) -> tuple[str, list[InjectedError]]:
    """Inject one error via an unconstrained FAVA-style prompt (no codebook).

    Args:
        segment: Corpus segment with source and reference.
        llm_config: LLM configuration dict (provider, model, ...).

    Returns:
        ``(modified_text, [InjectedError])``
    """
    llm = make_client_from_config(llm_config)
    reference = segment.reference_translation
    user_prompt = _build_user_prompt(segment.source_text, reference)

    last_errors: list[str] = []

    for attempt in range(_MAX_RETRIES):
        temp = 0.3 + (attempt * 0.1)
        prompt = user_prompt
        if attempt > 0 and last_errors:
            prompt += (
                "\n\nPREVIOUS ATTEMPT FAILED:\n"
                + "\n".join(f"- {e}" for e in last_errors)
                + "\nFix these issues. Return ONLY the modified translation "
                "with <ERROR> tags."
            )

        try:
            raw = await llm.complete_text(
                system=_SYSTEM_PROMPT,
                user=prompt,
                temperature=temp,
            )
        except Exception as exc:
            logger.warning(
                "B2 LLM call failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
            last_errors = [str(exc)]
            continue

        raw = raw.strip()
        verification_errors = _verify_b2(reference, raw)

        if verification_errors:
            logger.warning(
                "B2 verification failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES, verification_errors,
            )
            last_errors = verification_errors
            continue

        # Parse the first <ERROR> tag
        m = _ERROR_TAG_RE.search(raw)
        assert m is not None  # verified above

        span_text = m.group(1)
        clean_text = _ERROR_TAG_RE.sub(r"\1", raw).strip()

        # Compute span position in clean text
        before_tag = raw[: m.start()]
        clean_before = _ERROR_TAG_RE.sub(r"\1", before_tag)
        span_start = len(clean_before)
        span_end = span_start + len(span_text)

        # Recover original span from reference
        original_text = _find_original_span(reference, clean_text, span_start, span_end)

        # Classify the error
        primary_tag = _guess_primary_tag(original_text, span_text)
        tom_level = _guess_tom_level(primary_tag)
        skill = _guess_skill(primary_tag)

        error = InjectedError(
            error_id=str(uuid.uuid4()),
            span_start=span_start,
            span_end=span_end,
            original_text=original_text,
            injected_text=span_text,
            primary_tag=primary_tag,
            error_type=f"unconstrained_{primary_tag.value.lower()}",
            severity=Severity.MAJOR,  # Default; unknown without codebook
            tom_level=tom_level,
            primary_skill=skill,
            secondary_skills=[],
            severity_range=[Severity.MINOR, Severity.MAJOR],
            direction="both",
            explanation=ContrastiveExplanation(
                mt_interpretation=(
                    "Unconstrained injection — the LLM chose this error freely "
                    "without codebook guidance."
                ),
                actual_meaning=f"Original reference text: '{original_text}'",
                reader_impact=f"Reader sees '{span_text}' instead of '{original_text}'.",
                correction_rationale=f"Restore the original text: '{original_text}'.",
            ),
            xml_tag=raw,
            brief_explanation=f"B2 unconstrained: '{original_text}' -> '{span_text}'",
        )

        logger.info(
            "B2 injected %s (guessed) at [%d:%d]: '%s' -> '%s'",
            primary_tag.value, span_start, span_end,
            original_text, span_text,
        )

        return clean_text, [error]

    raise ValueError(
        f"B2 unconstrained injection failed after {_MAX_RETRIES} attempts. "
        f"Last errors: {last_errors}"
    )


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    from experiments.pipeline_validation.config import DEFAULT_LLM_CONFIG

    dummy = CorpusSegment(
        segment_id="test-b2-001",
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
        modified, errors = await inject_unconstrained(
            segment=dummy,
            llm_config=DEFAULT_LLM_CONFIG,
        )
        print(f"Original:  {dummy.reference_translation}")
        print(f"Modified:  {modified}")
        for e in errors:
            print(f"  -> {e.primary_tag.value}/{e.error_type} "
                  f"[{e.span_start}:{e.span_end}] "
                  f"'{e.original_text}' -> '{e.injected_text}'")

    asyncio.run(_run())
