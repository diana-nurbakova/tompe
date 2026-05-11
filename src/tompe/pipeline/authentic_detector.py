"""Authentic error detection pipeline stage.

For the authentic pathway: detects real errors in MT output by running
GEMBA-MQM over (source, mt_output) and mapping each detected error to
the ToM-PE taxonomy (primary tag, error type, ToM level, skill).

Spec v1.1 §7.2 calls for xCOMET-XL + GEMBA-MQM cross-validation.
xCOMET is GPU-deferred (see Deliberate scope decisions in the audit),
so this v1 uses GEMBA-MQM alone. When xCOMET becomes available, run a
second pass and intersect the spans before mapping.

Layer 1 contrastive explanations are synthesised from GEMBA's per-error
fields (span + free-text explanation) to avoid an additional per-error
LLM call. Layer 2a is consulted from the cached templates committed at
``data/codebook/layer2a_explanations.json`` (cache hit only — no LLM
fallback inside this detector).
"""

from __future__ import annotations

import logging

from tompe.pipeline.explanation_generator import (
    _LAYER2A_CACHE_PATH,
    _load_explanation_cache,
    _lookup_explanation,
)
from tompe.pipeline.mqm_taxonomy import get_error_spec, get_types_for_tag
from tompe.pipeline.qe_validator import GEMBAError, QEValidationResult, validate_item_gemba
from tompe.schemas.corpus import CorpusSegment, MTOutput
from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel
from tompe.schemas.error import (
    AuthenticErrorDetection,
    ContrastiveExplanation,
    DetectedError,
    SystemBehaviorExplanation,
)

logger = logging.getLogger(__name__)


# ── GEMBA → taxonomy mapping tables ─────────────────────────────────────────

# Subcategory text (case-insensitive substring match) → PrimaryTag. Order
# matters because we take the first hit; put longer / more-specific keys
# first when they could collide.
_SUBCATEGORY_TO_TAG: list[tuple[str, PrimaryTag]] = [
    ("mistranslation", PrimaryTag.MISTRANSLATION),
    ("untranslated", PrimaryTag.UNTRANSLATED),
    ("source language", PrimaryTag.UNTRANSLATED),
    ("omission", PrimaryTag.OMISSION),
    ("addition", PrimaryTag.ADDITION),
    ("hallucination", PrimaryTag.ADDITION),
    ("punctuation", PrimaryTag.PUNCTUATION),
    ("spelling", PrimaryTag.SPELLING),
    ("typo", PrimaryTag.SPELLING),
    ("grammar", PrimaryTag.GRAMMAR),
    ("agreement", PrimaryTag.GRAMMAR),
    ("tense", PrimaryTag.GRAMMAR),
    ("word order", PrimaryTag.GRAMMAR),
    ("wrong term", PrimaryTag.TERMINOLOGY),
    ("terminology", PrimaryTag.TERMINOLOGY),
    ("inconsistent", PrimaryTag.TERMINOLOGY),
    ("register", PrimaryTag.STYLE),
    ("awkward", PrimaryTag.STYLE),
    ("unidiomatic", PrimaryTag.STYLE),
    ("style", PrimaryTag.STYLE),
    ("locale", PrimaryTag.LOCALE),
    ("format", PrimaryTag.LOCALE),
    ("date", PrimaryTag.LOCALE),
    ("number format", PrimaryTag.LOCALE),
]

# Fallback: dimension-level category → PrimaryTag (default per dimension).
_CATEGORY_TO_TAG: dict[str, PrimaryTag] = {
    "accuracy": PrimaryTag.MISTRANSLATION,
    "fluency": PrimaryTag.GRAMMAR,
    "terminology": PrimaryTag.TERMINOLOGY,
    "style": PrimaryTag.STYLE,
    "locale": PrimaryTag.LOCALE,
    "linguistic conventions": PrimaryTag.GRAMMAR,
}

# Default ToM level when the (tag, type) pair is not in ERROR_TYPE_SPECS.
# Reasoning: surface errors → 1st_machine; semantic/structural → 1st_author;
# style/locale → 2nd_reader. Critical severity bumps one level up.
_TAG_TO_DEFAULT_TOM: dict[PrimaryTag, TOMLevel] = {
    PrimaryTag.SPELLING: TOMLevel.FIRST_ORDER_MACHINE,
    PrimaryTag.PUNCTUATION: TOMLevel.FIRST_ORDER_MACHINE,
    PrimaryTag.UNTRANSLATED: TOMLevel.FIRST_ORDER_MACHINE,
    PrimaryTag.GRAMMAR: TOMLevel.FIRST_ORDER_MACHINE,
    PrimaryTag.MISTRANSLATION: TOMLevel.FIRST_ORDER_AUTHOR,
    PrimaryTag.OMISSION: TOMLevel.FIRST_ORDER_AUTHOR,
    PrimaryTag.ADDITION: TOMLevel.FIRST_ORDER_AUTHOR,
    PrimaryTag.TERMINOLOGY: TOMLevel.FIRST_ORDER_AUTHOR,
    PrimaryTag.STYLE: TOMLevel.SECOND_ORDER_READER,
    PrimaryTag.LOCALE: TOMLevel.SECOND_ORDER_READER,
}

# Default primary skill per tag, used only when the (tag, type) pair is
# not in ERROR_TYPE_SPECS.
_TAG_TO_DEFAULT_SKILL: dict[PrimaryTag, SkillID] = {
    PrimaryTag.SPELLING: SkillID.S1,
    PrimaryTag.PUNCTUATION: SkillID.S1,
    PrimaryTag.GRAMMAR: SkillID.S2,
    PrimaryTag.MISTRANSLATION: SkillID.S3,
    PrimaryTag.OMISSION: SkillID.S4,
    PrimaryTag.ADDITION: SkillID.S4,
    PrimaryTag.UNTRANSLATED: SkillID.S4,
    PrimaryTag.TERMINOLOGY: SkillID.S5,
    PrimaryTag.STYLE: SkillID.S6,
    PrimaryTag.LOCALE: SkillID.S6,
}

_SEVERITY_WEIGHT: dict[str, float] = {
    "minor": 0.6,
    "major": 0.8,
    "critical": 0.95,
}


# ── Mapping helpers ─────────────────────────────────────────────────────────


def _parse_severity(raw: str | None) -> Severity:
    if not raw:
        return Severity.MAJOR
    lowered = raw.strip().lower()
    if "critical" in lowered:
        return Severity.CRITICAL
    if "major" in lowered:
        return Severity.MAJOR
    if "minor" in lowered:
        return Severity.MINOR
    return Severity.MAJOR


def _map_gemba_to_taxonomy(g_err: GEMBAError) -> tuple[PrimaryTag, str]:
    """Map a GEMBA-detected error to (PrimaryTag, error_type).

    Priority: subcategory > category. error_type is matched against the
    taxonomy's known types for that tag; falls back to the first/most-
    common type when no substring match is found.
    """
    sub = (g_err.subcategory or "").lower()
    cat = (g_err.category or "").lower()

    primary_tag: PrimaryTag | None = None
    for key, tag in _SUBCATEGORY_TO_TAG:
        if key in sub:
            primary_tag = tag
            break
    if primary_tag is None:
        for key, tag in _SUBCATEGORY_TO_TAG:
            if key in cat:
                primary_tag = tag
                break
    if primary_tag is None:
        primary_tag = _CATEGORY_TO_TAG.get(cat.split()[0] if cat else "", PrimaryTag.MISTRANSLATION)

    known = get_types_for_tag(primary_tag)
    error_type: str | None = None
    if known:
        # Try exact / substring match against sub+cat text
        haystack = f"{sub} {cat}".lower()
        for t in known:
            normalised = t.replace("_", " ").lower()
            if normalised in haystack or t.lower() in haystack:
                error_type = t
                break
    if error_type is None:
        error_type = known[0] if known else "unspecified"

    return primary_tag, error_type


def _infer_tom_level(primary_tag: PrimaryTag, severity: Severity) -> TOMLevel:
    base = _TAG_TO_DEFAULT_TOM.get(primary_tag, TOMLevel.FIRST_ORDER_AUTHOR)
    if severity == Severity.CRITICAL and base == TOMLevel.FIRST_ORDER_AUTHOR:
        return TOMLevel.SECOND_ORDER_READER
    return base


def _locate_span(translation: str, span_text: str) -> tuple[int, int]:
    """Find span_text in translation; tolerant to case differences."""
    if not span_text:
        return 0, 0
    pos = translation.find(span_text)
    if pos < 0:
        pos = translation.lower().find(span_text.lower())
    if pos < 0:
        return 0, 0
    return pos, pos + len(span_text)


def _build_contrastive_from_gemba(
    g_err: GEMBAError,
    primary_tag: PrimaryTag,
    error_type: str,
) -> ContrastiveExplanation:
    """Synthesise a Layer 1 ContrastiveExplanation from GEMBA's per-error
    fields without an extra LLM call. Used as a default; callers wanting
    higher-fidelity contrastive can re-run `generate_contrastive_explanation`
    on a DetectedError.
    """
    span = g_err.span or "(no span)"
    note = (g_err.explanation or "").strip()
    return ContrastiveExplanation(
        mt_interpretation=(
            f"The MT system produced '{span}', which GEMBA-MQM flagged as "
            f"{primary_tag.value.lower()} / {error_type.replace('_', ' ')}."
        ),
        actual_meaning=note or (
            f"GEMBA-MQM did not provide a free-text rationale; the span "
            f"'{span}' was identified as a {g_err.severity} error."
        ),
        reader_impact=(
            f"A {g_err.severity}-severity {primary_tag.value.lower()} error "
            f"in this span will mislead a reader about the source meaning."
        ),
        correction_rationale=(
            f"Replace '{span}' with a rendering that resolves the "
            f"{primary_tag.value.lower()} issue and preserves the source intent."
        ),
    )


def _confidence_for_error(qe_result: QEValidationResult, g_err: GEMBAError) -> float:
    """Per-error confidence: combines GEMBA's overall_score (lower = worse
    translation = more likely real error) with severity weighting.
    """
    overall = float(qe_result.overall_score or 100.0)
    severity_weight = _SEVERITY_WEIGHT.get(g_err.severity.lower() if g_err.severity else "", 0.7)
    score_factor = max(0.0, min(1.0, (100.0 - overall) / 100.0))
    return round(min(1.0, 0.7 * severity_weight + 0.3 * score_factor), 3)


def _aggregate_confidence(
    qe_result: QEValidationResult,
    detected_errors: list[DetectedError],
) -> float:
    """Overall confidence for the AuthenticErrorDetection record."""
    if not detected_errors:
        # No errors detected → confidence proportional to overall_score.
        return round(float(qe_result.overall_score or 80.0) / 100.0, 3)
    avg = sum(e.detection_confidence for e in detected_errors) / len(detected_errors)
    return round(avg, 3)


# ── Public API ──────────────────────────────────────────────────────────────


async def detect_authentic_errors(
    segment: CorpusSegment,
    mt_output: MTOutput,
    llm_config: dict,
    confidence_threshold: float = 0.8,
    enrich_layer2a: bool = True,
) -> AuthenticErrorDetection:
    """Detect and categorize errors in authentic MT output.

    Pipeline (v1 — GEMBA only; xCOMET deferred until GPU is available):

    1. Run GEMBA-MQM over (source, mt_output) to discover errors.
    2. Map each GEMBA error to (primary_tag, error_type) via the
       taxonomy; pick severity, tom_level, and skills from
       `ERROR_TYPE_SPECS` when the pair is known, otherwise fall back to
       per-tag defaults with severity-aware ToM-level inference.
    3. Synthesise a Layer 1 contrastive explanation from GEMBA's
       per-error span + free-text note (no extra LLM call).
    4. Optionally enrich with cached Layer 2a (no LLM call — cache-only).
    5. Compute per-error and aggregate confidence.

    Items whose ``confidence_score`` falls below ``confidence_threshold``
    should be flagged for human expert validation by the caller.

    Args:
        segment: Corpus segment with source + reference.
        mt_output: Authentic MT output to evaluate.
        llm_config: LLM configuration for the GEMBA-MQM call.
        confidence_threshold: Threshold below which the detection should
            be flagged for human review. Returned in the result; not
            enforced internally.
        enrich_layer2a: If True, consult the Layer 2a cache and attach
            the cached explanation to each detected error. Cache-only —
            never triggers an LLM call here.

    Returns:
        ``AuthenticErrorDetection`` with detected errors and a confidence
        score. ``detection_method`` is set to ``"gemba_mqm"``.
    """
    qe_result = await validate_item_gemba(
        source_text=segment.source_text,
        reference=segment.reference_translation,
        injected_text=mt_output.mt_text,
        injected_errors=[],  # no manifest; we're discovering, not validating
        llm_config=llm_config,
        source_lang=segment.source_lang,
        target_lang=segment.target_lang,
    )

    layer2a_entries = (
        _load_explanation_cache(str(_LAYER2A_CACHE_PATH)) if enrich_layer2a else []
    )

    detected_errors: list[DetectedError] = []
    for g_err in qe_result.gemba_errors:
        primary_tag, error_type = _map_gemba_to_taxonomy(g_err)
        severity = _parse_severity(g_err.severity)

        try:
            spec = get_error_spec(primary_tag, error_type)
            tom_level = spec.tom_level
            primary_skill = spec.primary_skill
            secondary_skills = list(spec.secondary_skills)
        except KeyError:
            tom_level = _infer_tom_level(primary_tag, severity)
            primary_skill = _TAG_TO_DEFAULT_SKILL.get(primary_tag, SkillID.S3)
            secondary_skills = []

        span_start, span_end = _locate_span(mt_output.mt_text, g_err.span)

        explanation = _build_contrastive_from_gemba(g_err, primary_tag, error_type)

        system_behavior: SystemBehaviorExplanation | None = None
        if enrich_layer2a:
            cached = _lookup_explanation(
                layer2a_entries,
                primary_tag.value,
                error_type,
                mt_output.mt_system,
            )
            if cached is not None:
                try:
                    system_behavior = SystemBehaviorExplanation(
                        error_mechanism=cached["error_mechanism"],
                        architectural_cause=cached["architectural_cause"],
                        pattern_generalization=cached["pattern_generalization"],
                        mt_system_specific=cached["mt_system_specific"],
                    )
                except (KeyError, TypeError) as exc:
                    logger.warning(
                        "Layer 2a cache entry malformed for %s/%s: %s",
                        primary_tag.value, error_type, exc,
                    )

        detected_errors.append(DetectedError(
            span_start=span_start,
            span_end=span_end,
            primary_tag=primary_tag,
            error_type=error_type,
            severity=severity,
            tom_level=tom_level,
            primary_skill=primary_skill,
            secondary_skills=secondary_skills,
            detection_confidence=_confidence_for_error(qe_result, g_err),
            explanation=explanation,
            system_behavior=system_behavior,
            human_validated=False,
        ))

    confidence = _aggregate_confidence(qe_result, detected_errors)

    if confidence < confidence_threshold:
        logger.info(
            "Authentic detection for segment %s flagged for review "
            "(confidence=%.2f < threshold=%.2f, n_errors=%d)",
            segment.segment_id, confidence, confidence_threshold, len(detected_errors),
        )

    return AuthenticErrorDetection(
        detection_method="gemba_mqm",
        mt_output=mt_output.mt_text,
        reference=segment.reference_translation,
        detected_errors=detected_errors,
        confidence_score=confidence,
    )
