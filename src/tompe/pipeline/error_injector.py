"""MQM-guided error injection pipeline — two-step architecture.

From spec v1.1 §2: Step 1 (planning/reasoning) then Step 2 (XML-tagged execution).
Each error is injected via two sequential LLM calls for reliable span tracking.

Verification uses XML parsing + diff checking instead of raw span offsets.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from typing import Optional

from tompe.pipeline._injection_prompts import (
    STEP1_RESPONSE_SCHEMA,
    STEP2_RESPONSE_SCHEMA,
    SYSTEM_PROMPT_STEP1,
    SYSTEM_PROMPT_STEP2,
    build_step1_prompt,
    build_step2_prompt,
)
from tompe.pipeline.codebook import Codebook, load_default_codebook
from tompe.pipeline.llm_client import LLMClient, make_client_from_config
from tompe.pipeline.mqm_taxonomy import (
    ERROR_TYPE_SPECS,
    ErrorTypeSpec,
    get_error_spec,
    get_types_for_tag,
    validate_tag_type,
)
from tompe.schemas.corpus import CorpusSegment, MTOutput
from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel
from tompe.schemas.error import ContrastiveExplanation, InjectedError

logger = logging.getLogger(__name__)

# Maximum retries per single error injection on verification failure
_MAX_INJECTION_RETRIES = 3

# Regex to match our XML error tags
_TAG_PATTERN = re.compile(
    r'<(\w+)\s+type="([^"]+)"\s+severity="([^"]+)"\s+tom="([^"]+)"\s+desc="([^"]*)">'
    r'(.*?)'
    r'</\1>',
    re.DOTALL,
)


class ErrorProfile:
    """Target error profile for injection."""

    def __init__(
        self,
        primary_tags: list[PrimaryTag],
        severity_distribution: dict[Severity, int],
        tom_levels: list[TOMLevel] | None = None,
        direction: str = "both",
        include_clean_spans: bool = True,
        use_few_shot: bool = True,
    ):
        self.primary_tags = primary_tags
        self.severity_distribution = severity_distribution
        self.tom_levels = tom_levels
        self.direction = direction
        self.include_clean_spans = include_clean_spans
        self.use_few_shot = use_few_shot


def _plan_errors(profile: ErrorProfile) -> list[ErrorTypeSpec]:
    """Expand an ErrorProfile into a list of error type specs to inject.

    Uses the full taxonomy mapping matrix to select appropriate types.
    """
    # Filter specs by profile constraints
    candidates = [
        s for s in ERROR_TYPE_SPECS
        if s.primary_tag in profile.primary_tags
        and (s.direction == profile.direction or s.direction == "both"
             or profile.direction == "both")
    ]
    if profile.tom_levels:
        # Prefer types matching the requested ToM levels
        constrained = [s for s in candidates if s.tom_level in profile.tom_levels]
        if constrained:
            candidates = constrained

    if not candidates:
        logger.warning("No error types match profile constraints")
        return []

    error_specs = []
    for severity, count in profile.severity_distribution.items():
        for _ in range(count):
            # Filter candidates that allow this severity
            valid = [s for s in candidates if severity in s.severity_range]
            if not valid:
                # Fall back to any candidate (severity is context-dependent)
                valid = candidates
            spec = random.choice(valid)
            error_specs.append(spec)

    # Sort: omissions first (they remove text, so other errors must operate
    # on the post-omission text), then additions, then the rest shuffled.
    omissions = [s for s in error_specs if s.primary_tag == PrimaryTag.OMISSION]
    additions = [s for s in error_specs if s.primary_tag == PrimaryTag.ADDITION]
    others = [s for s in error_specs
              if s.primary_tag not in (PrimaryTag.OMISSION, PrimaryTag.ADDITION)]
    random.shuffle(others)
    return omissions + others + additions


# ============================================================================
# XML Verification (spec v1.1 §2.4)
# ============================================================================

def _parse_xml_tags(injected_text: str) -> list[dict]:
    """Parse XML error tags from injected translation text.

    Returns list of dicts with: tag_name, type, severity, tom, desc,
    span_text, span_start, span_end (in the clean text without tags).
    """
    results = []
    for match in _TAG_PATTERN.finditer(injected_text):
        results.append({
            "tag_name": match.group(1),
            "type": match.group(2),
            "severity": match.group(3),
            "tom": match.group(4),
            "desc": match.group(5),
            "span_text": match.group(6),
            "match_start": match.start(),
            "match_end": match.end(),
        })
    return results


def _strip_xml_tags(injected_text: str) -> str:
    """Remove XML error tags, keeping only the error span content."""
    return _TAG_PATTERN.sub(r'\6', injected_text)


def _get_span_positions(injected_text: str, parsed_tag: dict) -> tuple[int, int]:
    """Compute character offsets of the error span in the clean (tag-stripped) text.

    The span_start/end are relative to the text with tags removed.
    """
    # Text before the tag match
    before_tag = injected_text[:parsed_tag["match_start"]]
    # Strip any earlier tags from the before text
    clean_before = _TAG_PATTERN.sub(r'\6', before_tag)
    span_start = len(clean_before)
    span_end = span_start + len(parsed_tag["span_text"])
    return span_start, span_end


def _verify_injection(
    reference: str,
    response: dict,
) -> list[str]:
    """Verify an injection response per spec v1.1 §2.4.

    Checks:
    1. XML tag parsing — valid tag found
    2. Diff check — non-tagged text identical to reference
    3. Tag validation — tag name, type, severity, tom in allowed inventory
    4. Explanation completeness — all 4 fields non-empty, >10 words each

    Returns list of error messages (empty = valid).
    """
    errors = []
    injected_translation = response.get("injected_translation", "")

    # 1. Parse XML tags
    parsed_tags = _parse_xml_tags(injected_translation)
    if not parsed_tags:
        errors.append("No valid XML error tag found in injected_translation")
        return errors

    if len(parsed_tags) > 1:
        errors.append(f"Expected 1 error tag, found {len(parsed_tags)}")

    tag = parsed_tags[0]

    # 2. Diff check — text outside the tag should match reference
    clean_text = _strip_xml_tags(injected_translation)
    # Reconstruct what the reference should look like
    span_start, span_end = _get_span_positions(injected_translation, tag)
    original_span = response.get("original_span_text", "")

    import unicodedata
    reconstructed = clean_text[:span_start] + original_span + clean_text[span_end:]

    # Fuzzy comparison: normalize whitespace, ligatures, and minor punctuation
    def _normalize_for_diff(s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        # Collapse whitespace around punctuation
        import re
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'\s+([.,;:!?\)])', r'\1', s)
        return s.strip()

    reconstructed_norm = _normalize_for_diff(reconstructed)
    reference_norm = _normalize_for_diff(reference)

    # Use similarity ratio instead of exact match — allow small LLM drift
    from difflib import SequenceMatcher
    similarity = SequenceMatcher(None, reconstructed_norm, reference_norm).ratio()
    if similarity < 0.95:  # Allow up to 5% drift in non-error text
        # Find first difference for the error message
        min_len = min(len(reconstructed_norm), len(reference_norm))
        for i in range(min_len):
            if reconstructed_norm[i] != reference_norm[i]:
                errors.append(
                    f"Text outside error span differs at pos {i}: "
                    f"got '{reconstructed_norm[max(0,i-10):i+10]}' vs "
                    f"expected '{reference_norm[max(0,i-10):i+10]}' "
                    f"(similarity: {similarity:.1%})"
                )
                break
        else:
            if len(reconstructed_norm) != len(reference_norm):
                errors.append(
                    f"Reconstructed text length ({len(reconstructed_norm)}) != "
                    f"reference length ({len(reference_norm)})"
                )

    # 3. Tag validation
    if not validate_tag_type(tag["tag_name"], tag["type"]):
        errors.append(
            f"Invalid tag/type pair: {tag['tag_name']}/{tag['type']}"
        )

    if tag["severity"] not in ("minor", "major", "critical"):
        errors.append(f"Invalid severity: {tag['severity']}")

    if tag["tom"] not in ("1st_machine", "1st_author", "2nd_reader", "recursive"):
        errors.append(f"Invalid tom level: {tag['tom']}")

    # 4. Desc attribute check
    desc_words = len(tag["desc"].split())
    if desc_words < 3:
        errors.append(f"desc attribute too short ({desc_words} words, need ≥5)")

    # 5. Explanation completeness
    explanation = response.get("explanation", {})
    for field in ("mt_interpretation", "actual_meaning", "reader_impact", "correction_rationale"):
        value = explanation.get(field, "")
        if not value or len(value.split()) < 5:
            errors.append(f"Explanation field '{field}' too short or empty")

    # 6. Non-trivial change
    error_span = response.get("error_span_text", "")
    if error_span == original_span:
        errors.append("No actual change: error_span_text == original_span_text")

    return errors


# ============================================================================
# Two-Step Injection
# ============================================================================

async def _inject_single_error(
    current_text: str,
    source_text: str,
    error_spec: ErrorTypeSpec,
    domain: str,
    llm_client: LLMClient,
    codebook: Optional[Codebook] = None,
    use_few_shot: bool = True,
    direction: str = "both",
) -> tuple[str, InjectedError]:
    """Inject a single error using the two-step architecture.

    Step 1: LLM plans the error (NL reasoning)
    Step 2: LLM executes the injection (XML tagged output)
    """
    primary_tag = error_spec.primary_tag
    error_type = error_spec.error_type
    severity = random.choice(error_spec.severity_range)
    tom_level = error_spec.tom_level

    # Get codebook info for this error type
    definition = ""
    boundary_not = ""
    few_shot_examples = None
    if codebook:
        definition = codebook.get_definition(primary_tag.value, error_type)
        boundary_not = codebook.get_boundary_not(primary_tag.value, error_type)
        if use_few_shot:
            dir_filter = direction if direction != "both" else None
            few_shot_examples = codebook.get_few_shot_examples(
                primary_tag.value, error_type, direction=dir_filter, n=3
            )

    last_verification_errors: list[str] = []

    for attempt in range(_MAX_INJECTION_RETRIES + 1):
        # --- Step 1: Planning ---
        step1_prompt = build_step1_prompt(
            source_text=source_text,
            reference=current_text,
            primary_tag=primary_tag,
            error_type=error_type,
            severity=severity,
            tom_level=tom_level,
            domain=domain,
            definition=definition,
            boundary_not=boundary_not,
        )

        try:
            step1_output = await llm_client.complete_json(
                system=SYSTEM_PROMPT_STEP1,
                user=step1_prompt,
                schema=STEP1_RESPONSE_SCHEMA,
                temperature=0.4 + (attempt * 0.1),
            )
        except Exception as e:
            logger.warning("Step 1 failed for %s/%s (attempt %d): %s",
                           primary_tag.value, error_type, attempt + 1, e)
            if attempt == _MAX_INJECTION_RETRIES:
                raise ValueError(f"Step 1 failed after {_MAX_INJECTION_RETRIES + 1} attempts") from e
            continue

        # --- Step 2: Execution ---
        step2_prompt = build_step2_prompt(
            reference=current_text,
            primary_tag=primary_tag,
            error_type=error_type,
            severity=severity,
            tom_level=tom_level,
            step1_output=step1_output,
            few_shot_examples=few_shot_examples if use_few_shot else None,
        )

        # Add correction guidance if retrying
        if attempt > 0 and last_verification_errors:
            correction = (
                "\n\nPREVIOUS ATTEMPT FAILED VERIFICATION:\n"
                + "\n".join(f"- {e}" for e in last_verification_errors)
                + "\nFix these issues. Pay attention to keeping non-error text identical."
            )
            step2_prompt += correction

        try:
            step2_output = await llm_client.complete_json(
                system=SYSTEM_PROMPT_STEP2,
                user=step2_prompt,
                schema=STEP2_RESPONSE_SCHEMA,
                temperature=0.3 + (attempt * 0.1),
            )
        except Exception as e:
            logger.warning("Step 2 failed for %s/%s (attempt %d): %s",
                           primary_tag.value, error_type, attempt + 1, e)
            if attempt == _MAX_INJECTION_RETRIES:
                raise ValueError(f"Step 2 failed after {_MAX_INJECTION_RETRIES + 1} attempts") from e
            continue

        # --- Verify ---
        verification_errors = _verify_injection(current_text, step2_output)
        if not verification_errors:
            # Success — extract span info and build InjectedError
            injected_translation = step2_output["injected_translation"]
            parsed_tags = _parse_xml_tags(injected_translation)
            tag = parsed_tags[0]
            clean_text = _strip_xml_tags(injected_translation)
            span_start, span_end = _get_span_positions(injected_translation, tag)

            explanation_data = step2_output.get("explanation", {})

            error = InjectedError(
                error_id=str(uuid.uuid4()),
                span_start=span_start,
                span_end=span_end,
                original_text=step2_output.get("original_span_text", ""),
                injected_text=tag["span_text"],
                primary_tag=primary_tag,
                error_type=error_type,
                severity=severity,
                tom_level=tom_level,
                primary_skill=error_spec.primary_skill,
                secondary_skills=list(error_spec.secondary_skills),
                severity_range=list(error_spec.severity_range),
                direction=error_spec.direction,
                explanation=ContrastiveExplanation(
                    mt_interpretation=explanation_data.get("mt_interpretation", ""),
                    actual_meaning=explanation_data.get("actual_meaning", ""),
                    reader_impact=explanation_data.get("reader_impact", ""),
                    correction_rationale=explanation_data.get("correction_rationale", ""),
                ),
                xml_tag=injected_translation,
                brief_explanation=tag["desc"],
            )

            logger.info(
                "Injected %s/%s (%s) at [%d:%d]: '%s' → '%s'",
                primary_tag.value, error_type, severity.value,
                span_start, span_end,
                step2_output.get("original_span_text", ""),
                tag["span_text"],
            )

            return clean_text, error

        # Verification failed
        last_verification_errors = verification_errors
        logger.warning(
            "Verification failed (attempt %d/%d) for %s/%s: %s",
            attempt + 1, _MAX_INJECTION_RETRIES + 1,
            primary_tag.value, error_type, verification_errors,
        )

    raise ValueError(
        f"Error injection failed verification after {_MAX_INJECTION_RETRIES + 1} "
        f"attempts for {primary_tag.value}/{error_type}. "
        f"Last errors: {last_verification_errors}"
    )


# ============================================================================
# Span recalculation for multi-error items
# ============================================================================


def _realign_spans(
    final_text: str,
    errors: list[InjectedError],
) -> None:
    """Realign every error's span to point into *final_text*.

    After sequential injection, spans may be stale because:
    - Later injections shifted character positions (offset drift).
    - The LLM made minor whitespace/punctuation changes outside the
      error span (allowed up to 5% by verification).
    - A later error overwrote part of an earlier error's text.

    Strategy (single pass, last-injected first):
    1. ``find()`` each error's ``injected_text`` in *final_text*.
    2. Pick the match closest to the current (possibly stale) offset.
    3. If not found, the text was overwritten by a later error — read
       the actual content at the approximate position and update
       ``injected_text``.
    """
    text_len = len(final_text)
    claimed: set[tuple[int, int]] = set()

    # Process in reverse: last error's spans are most likely correct
    for error in reversed(errors):
        target = error.injected_text
        if not target:
            error.span_start = min(error.span_start, text_len)
            error.span_end = error.span_start
            continue

        # Find all unclaimed occurrences
        candidates: list[tuple[int, int]] = []
        search_pos = 0
        while True:
            pos = final_text.find(target, search_pos)
            if pos == -1:
                break
            span = (pos, pos + len(target))
            if span not in claimed:
                candidates.append(span)
            search_pos = pos + 1

        if candidates:
            best = min(candidates, key=lambda c: abs(c[0] - error.span_start))
            error.span_start = best[0]
            error.span_end = best[1]
            claimed.add(best)
        else:
            # Text was overwritten by a later error — read actual content
            # at the approximate position and update injected_text.
            s = max(0, min(error.span_start, text_len))
            e = max(s, min(error.span_end, text_len))
            actual = final_text[s:e]
            if actual:
                logger.debug(
                    "Span overwritten for error %s: '%s' → '%s'",
                    error.error_id, target[:30], actual[:30],
                )
                error.span_start = s
                error.span_end = e
                error.injected_text = actual
                claimed.add((s, e))
            else:
                logger.warning(
                    "Could not realign error %s ('%s') in final text",
                    error.error_id, target[:30],
                )


# ============================================================================
# Public API
# ============================================================================

async def inject_errors_reference_based(
    segment: CorpusSegment,
    error_profile: ErrorProfile,
    llm_config: dict,
    codebook: Optional[Codebook] = None,
    verify_gemba: bool = False,
    gemba_llm_config: dict | None = None,
    gemba_min_detection_rate: float = 0.5,
) -> tuple[str, list[InjectedError]]:
    """Inject errors into the human reference translation.

    This is the primary injection mode (controlled pathway). Uses the two-step
    prompt architecture for each error.

    Args:
        segment: Corpus segment with source and reference.
        error_profile: Target error profile.
        llm_config: Config for the injection LLM (provider, model, etc.).
        codebook: Optional codebook for few-shot examples. If None, loads default.
        verify_gemba: If True, run a single GEMBA-MQM detection pass after
            all errors are injected and raise ValueError when fewer than
            `gemba_min_detection_rate` of injected errors are independently
            detected. Spec v1.1 §2.4 calls for QE-gated injection; with
            xCOMET deferred (GPU), GEMBA is the available gate.
        gemba_llm_config: LLM config for the GEMBA pass (defaults to
            `llm_config`). Has no effect unless `verify_gemba=True`.
        gemba_min_detection_rate: Minimum fraction of injected errors that
            GEMBA must detect for the item to pass (default 0.5, matching
            `QEValidationResult.passes_validation`).

    Returns:
        Tuple of (modified_text_with_errors, list_of_InjectedError).
    """
    llm_client = make_client_from_config(llm_config)
    if codebook is None:
        codebook = load_default_codebook()

    error_specs = _plan_errors(error_profile)
    if not error_specs:
        return segment.reference_translation, []

    current_text = segment.reference_translation
    injected_errors: list[InjectedError] = []

    for i, spec in enumerate(error_specs):
        logger.info(
            "Injecting error %d/%d for segment %s: %s/%s",
            i + 1, len(error_specs), segment.segment_id,
            spec.primary_tag.value, spec.error_type,
        )

        current_text, error = await _inject_single_error(
            current_text=current_text,
            source_text=segment.source_text,
            error_spec=spec,
            domain=segment.domain,
            llm_client=llm_client,
            codebook=codebook,
            use_few_shot=error_profile.use_few_shot,
            direction=error_profile.direction,
        )
        # Adjust prior errors' spans for the character delta this injection caused
        injected_errors.append(error)

    # Realign all spans to the final text
    if len(injected_errors) > 1:
        _realign_spans(current_text, injected_errors)

    if verify_gemba and injected_errors:
        # Imported here to avoid a circular import at module load time.
        from tompe.pipeline.qe_validator import validate_item_gemba

        gemba_cfg = gemba_llm_config or llm_config
        qe_result = await validate_item_gemba(
            source_text=segment.source_text,
            reference=segment.reference_translation,
            injected_text=current_text,
            injected_errors=injected_errors,
            llm_config=gemba_cfg,
            source_lang=segment.source_lang,
            target_lang=segment.target_lang,
        )
        if qe_result.detection_rate < gemba_min_detection_rate:
            raise ValueError(
                f"GEMBA-MQM gating failed for segment {segment.segment_id}: "
                f"detection_rate={qe_result.detection_rate:.2f} < "
                f"{gemba_min_detection_rate:.2f} "
                f"({qe_result.gemba_detected}/{qe_result.total_injected} detected)"
            )

    return current_text, injected_errors


async def inject_errors_mt_based(
    segment: CorpusSegment,
    mt_output: MTOutput,
    error_profile: ErrorProfile,
    llm_config: dict,
    codebook: Optional[Codebook] = None,
) -> tuple[str, list[InjectedError]]:
    """Augment real MT output with additional controlled errors.

    Same two-step architecture but starts from MT output instead of reference.
    """
    llm_client = make_client_from_config(llm_config)
    if codebook is None:
        codebook = load_default_codebook()

    error_specs = _plan_errors(error_profile)
    if not error_specs:
        return mt_output.mt_text, []

    current_text = mt_output.mt_text
    injected_errors: list[InjectedError] = []

    for i, spec in enumerate(error_specs):
        logger.info(
            "Injecting error %d/%d into MT output for segment %s: %s/%s",
            i + 1, len(error_specs), segment.segment_id,
            spec.primary_tag.value, spec.error_type,
        )

        current_text, error = await _inject_single_error(
            current_text=current_text,
            source_text=segment.source_text,
            error_spec=spec,
            domain=segment.domain,
            llm_client=llm_client,
            codebook=codebook,
            use_few_shot=error_profile.use_few_shot,
            direction=error_profile.direction,
        )
        injected_errors.append(error)

    if len(injected_errors) > 1:
        _realign_spans(current_text, injected_errors)

    return current_text, injected_errors
