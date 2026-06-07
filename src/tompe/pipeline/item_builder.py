"""Canonical item-assembly orchestrator (pipeline package entry point).

Glues the per-stage pipeline pieces together into ``AssessmentItem``
instances ready for the student / annotation / scoring stages:

  segment → (error injection | authentic detection) → explanations
          → AssessmentItem (with ItemMetadata + clean_spans)

Two pathways are supported:

  - ``ItemPathway.CONTROLLED``: errors are injected into the human
    reference via ``inject_errors_reference_based`` (paper's primary
    mode).
  - ``ItemPathway.AUTHENTIC``: errors are detected in a real MT output
    via ``authentic_detector.detect_authentic_errors`` (xCOMET deferred;
    GEMBA-only v1).

``build_item`` returns one item; ``build_batch`` iterates over a list of
segments and collects the results. The experiments folder's
``generate_batch.py`` keeps its current segment-stratification logic and
is expected to migrate to ``build_batch`` over time — both coexist for
now so the camera-ready batch can be reproduced from the existing path.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Union

from tompe.pipeline.authentic_detector import detect_authentic_errors
from tompe.pipeline.codebook import Codebook, load_default_codebook
from tompe.pipeline.error_injector import (
    ErrorProfile,
    inject_errors_reference_based,
)
from tompe.pipeline.explanation_generator import (
    generate_layer2a_explanation,
    generate_layer2b_explanation,
    generate_contrastive_explanation,
)
from tompe.pipeline.tag_formats import TagFormat
from tompe.schemas.annotation import AnnotationConfig
from tompe.schemas.corpus import CorpusSegment, MTOutput
from tompe.schemas.enums import (
    AnnotationLevel,
    ItemPathway,
    MQMCategory,
    TOMLevel,
)
from tompe.schemas.error import (
    ContrastiveExplanation,
    DetectedError,
    InjectedError,
    SystemBehaviorExplanation,
    TechnicalExplanation,
)
from tompe.schemas.item import AssessmentItem, ItemMetadata

logger = logging.getLogger(__name__)


# ── Metadata + assembly helpers ─────────────────────────────────────────────


def _build_metadata(
    errors: list[Union[InjectedError, DetectedError]],
    pathway: ItemPathway,
    scaffolding_level: AnnotationLevel,
    direction: str,
    estimated_time_minutes: float = 2.0,
    has_clean_segments: bool = False,
) -> ItemMetadata:
    """Construct ItemMetadata, populating tom_profile / mqm_profile counts."""
    tom_profile: dict[TOMLevel, int] = {level: 0 for level in TOMLevel}
    mqm_profile: dict[MQMCategory, int] = {cat: 0 for cat in MQMCategory}

    for err in errors:
        tom_profile[err.tom_level] = tom_profile.get(err.tom_level, 0) + 1
        # mqm_profile is keyed by the legacy 5-category dimension; map from
        # primary_tag heuristically.
        primary_tag = err.primary_tag
        tag_val = primary_tag.value if hasattr(primary_tag, "value") else str(primary_tag)
        dimension = _PRIMARY_TO_MQM.get(tag_val, MQMCategory.ACCURACY)
        mqm_profile[dimension] = mqm_profile.get(dimension, 0) + 1

    return ItemMetadata(
        tom_profile=tom_profile,
        mqm_profile=mqm_profile,
        estimated_time_minutes=estimated_time_minutes,
        has_clean_segments=has_clean_segments,
        scaffolding_level=scaffolding_level,
        pathway=pathway,
        translation_direction=direction,
    )


# Mapping from PrimaryTag (string) to the legacy MQMCategory dimension.
# Used by _build_metadata to populate ItemMetadata.mqm_profile.
_PRIMARY_TO_MQM: dict[str, MQMCategory] = {
    "MISTRANSLATION": MQMCategory.ACCURACY,
    "OMISSION": MQMCategory.ACCURACY,
    "ADDITION": MQMCategory.ACCURACY,
    "UNTRANSLATED": MQMCategory.ACCURACY,
    "GRAMMAR": MQMCategory.FLUENCY,
    "SPELLING": MQMCategory.FLUENCY,
    "PUNCTUATION": MQMCategory.FLUENCY,
    "TERMINOLOGY": MQMCategory.TERMINOLOGY,
    "STYLE": MQMCategory.STYLE,
    "LOCALE": MQMCategory.LOCALE,
}


def _compute_clean_spans(
    text: str,
    errors: list[Union[InjectedError, DetectedError]],
) -> list[tuple[int, int]]:
    """Return character spans (start, end) of `text` that contain NO errors.

    Used by L3 ("Expert") views where students can mark spans as clean.
    Returns an empty list if there are no errors (the whole text is clean
    by definition; callers can synthesise a single full-span entry if
    they want to surface that explicitly).
    """
    if not errors:
        return []

    sorted_errs = sorted(errors, key=lambda e: e.span_start)
    clean: list[tuple[int, int]] = []
    cursor = 0
    for err in sorted_errs:
        if err.span_start > cursor:
            clean.append((cursor, err.span_start))
        cursor = max(cursor, err.span_end)
    if cursor < len(text):
        clean.append((cursor, len(text)))
    return clean


def _make_item_id(segment_id: str, pathway: ItemPathway) -> str:
    """Build a stable-prefix item_id."""
    suffix = uuid.uuid4().hex[:8]
    return f"item_{pathway.value}_{segment_id}_{suffix}"


# ── Single-item builder ─────────────────────────────────────────────────────


async def build_item(
    segment: CorpusSegment,
    llm_config: dict,
    pathway: ItemPathway = ItemPathway.CONTROLLED,
    mt_system: str = "reference_perturbed",
    error_profile: Optional[ErrorProfile] = None,
    mt_output: Optional[MTOutput] = None,
    codebook: Optional[Codebook] = None,
    tag_format: TagFormat = TagFormat.C4_FULL,
    scaffolding_level: AnnotationLevel = AnnotationLevel.ANALYST,
    difficulty_level: int = 3,
    estimated_time_minutes: float = 2.0,
    generate_layer1_explanations: bool = False,
    generate_layer2a_explanations: bool = False,
    generate_layer2b_explanations: bool = False,
    item_id: Optional[str] = None,
) -> AssessmentItem:
    """Build one ``AssessmentItem`` end-to-end.

    Args:
        segment: Corpus segment supplying source + reference + metadata.
        llm_config: LLM client config (provider, model, …) used by the
            injection / detection / explanation calls.
        pathway: ``CONTROLLED`` (default) injects errors into the
            reference; ``AUTHENTIC`` runs the detector on ``mt_output``.
        mt_system: Free-form label stored on the item. Defaults to
            ``"reference_perturbed"`` for the controlled pathway; pass
            e.g. ``"google_translate"`` or ``"deepseek_v3"`` when the
            authentic pathway is used.
        error_profile: Required for ``CONTROLLED``. Selects the error
            types, severities, and ToM levels to inject.
        mt_output: Required for ``AUTHENTIC``. The real MT output whose
            errors will be discovered by ``detect_authentic_errors``.
        codebook: Optional codebook override. Defaults to the bundled
            ``error_codebook_fr_en.json``.
        tag_format: One of the four C1–C4 formats from spec §5.5.
            Production callers should stick with C4_FULL; the C1–C3
            options are for the tagging ablation runner.
        scaffolding_level: Annotation level baked into the item's
            ``AnnotationConfig`` (Navigator / Scout / Analyst / Expert).
        difficulty_level: 1–5; surfaced to the teacher UI for filtering.
        estimated_time_minutes: Surfaced on item card and used for
            exercise sizing; not auto-computed yet.
        generate_layer1_explanations / generate_layer2a_explanations /
        generate_layer2b_explanations:
            When True, run the corresponding per-error LLM call (Layer 2a
            and 2b also consult the committed cache first). Default False to
            keep build_item cheap; Layer 2b (technical NLP depth) is opt-in
            for advanced/progressive-disclosure items.
        item_id: Optional override; auto-generated when None.

    Returns:
        Fully-populated ``AssessmentItem`` with ``ItemMetadata``,
        ``clean_spans``, and the requested explanation layers.
    """
    if pathway == ItemPathway.CONTROLLED and error_profile is None:
        raise ValueError("error_profile is required for the CONTROLLED pathway")
    if pathway == ItemPathway.AUTHENTIC and mt_output is None:
        raise ValueError("mt_output is required for the AUTHENTIC pathway")

    if codebook is None:
        codebook = load_default_codebook()

    errors: list[Union[InjectedError, DetectedError]] = []
    presented_text: str

    if pathway == ItemPathway.CONTROLLED:
        presented_text, injected = await inject_errors_reference_based(
            segment=segment,
            error_profile=error_profile,
            llm_config=llm_config,
            codebook=codebook,
            tag_format=tag_format,
        )
        errors = list(injected)
    else:  # ItemPathway.AUTHENTIC
        detection = await detect_authentic_errors(
            segment=segment,
            mt_output=mt_output,
            llm_config=llm_config,
        )
        presented_text = mt_output.mt_text
        errors = list(detection.detected_errors)
        # Bring the mt_system label in from the MTOutput if the caller
        # didn't override it.
        if mt_system == "reference_perturbed":
            mt_system = mt_output.mt_system

    # Optional explanation enrichment (only for errors that don't already
    # carry one — InjectedError always does; DetectedError might).
    layer1_list: list[ContrastiveExplanation] = []
    layer2a_list: list[SystemBehaviorExplanation] = []
    layer2b_list: list[TechnicalExplanation] = []
    for err in errors:
        if generate_layer1_explanations:
            existing = getattr(err, "explanation", None)
            if existing is None or _is_placeholder_explanation(existing):
                try:
                    explanation = await generate_contrastive_explanation(
                        source_text=segment.source_text,
                        reference=segment.reference_translation,
                        error=err,
                        llm_config=llm_config,
                    )
                    err.explanation = explanation
                except Exception:
                    logger.exception(
                        "Layer 1 generation failed for %s/%s",
                        err.primary_tag, err.error_type,
                    )
        if getattr(err, "explanation", None) is not None:
            layer1_list.append(err.explanation)

        if generate_layer2a_explanations:
            existing_2a = getattr(err, "system_behavior", None)
            if existing_2a is None:
                try:
                    layer2a = await generate_layer2a_explanation(
                        error=err,
                        mt_system=mt_system,
                        llm_config=llm_config,
                    )
                    err.system_behavior = layer2a
                except Exception:
                    logger.exception(
                        "Layer 2a generation failed for %s/%s",
                        err.primary_tag, err.error_type,
                    )
        if getattr(err, "system_behavior", None) is not None:
            layer2a_list.append(err.system_behavior)

        if generate_layer2b_explanations:
            existing_2b = getattr(err, "technical_explanation", None)
            if existing_2b is None:
                try:
                    layer2b = await generate_layer2b_explanation(
                        error=err,
                        mt_system=mt_system,
                        llm_config=llm_config,
                    )
                    err.technical_explanation = layer2b
                except Exception:
                    logger.exception(
                        "Layer 2b generation failed for %s/%s",
                        err.primary_tag, err.error_type,
                    )
        if getattr(err, "technical_explanation", None) is not None:
            layer2b_list.append(err.technical_explanation)

    direction = f"{segment.source_lang}->{segment.target_lang}"
    is_clean = not errors
    metadata = _build_metadata(
        errors=errors,
        pathway=pathway,
        scaffolding_level=scaffolding_level,
        direction=direction,
        estimated_time_minutes=estimated_time_minutes,
        has_clean_segments=is_clean,
    )

    annotation_config = AnnotationConfig(level=scaffolding_level)

    return AssessmentItem(
        item_id=item_id or _make_item_id(segment.segment_id, pathway),
        segment_id=segment.segment_id,
        source_text=segment.source_text,
        source_lang=segment.source_lang,
        target_lang=segment.target_lang,
        presented_text=presented_text,
        reference_translation=segment.reference_translation,
        mt_system=mt_system,
        pathway=pathway,
        errors=errors,
        clean_spans=_compute_clean_spans(presented_text, errors),
        annotations=[],
        annotation_config=annotation_config,
        difficulty_level=difficulty_level,
        domain=segment.domain,
        explanations_layer1=layer1_list,
        explanations_layer2=layer2a_list,
        explanations_layer2b=layer2b_list,
        metadata=metadata,
    )


def _is_placeholder_explanation(explanation: ContrastiveExplanation) -> bool:
    """Heuristic: was this explanation synthesised from a stub rather
    than generated by an LLM? Used to avoid re-running Layer 1 when
    inject_errors_reference_based already produced a real explanation.
    """
    return all(
        len((getattr(explanation, field, "") or "").split()) < 4
        for field in ("mt_interpretation", "actual_meaning",
                      "reader_impact", "correction_rationale")
    )


# ── Batch builder ───────────────────────────────────────────────────────────


async def build_batch(
    segments: list[CorpusSegment],
    llm_config: dict,
    pathway: ItemPathway = ItemPathway.CONTROLLED,
    error_profile: Optional[ErrorProfile] = None,
    mt_outputs: Optional[dict[str, MTOutput]] = None,
    mt_system: str = "reference_perturbed",
    codebook: Optional[Codebook] = None,
    tag_format: TagFormat = TagFormat.C4_FULL,
    scaffolding_level: AnnotationLevel = AnnotationLevel.ANALYST,
    difficulty_level: int = 3,
    estimated_time_minutes: float = 2.0,
    generate_layer1_explanations: bool = False,
    generate_layer2a_explanations: bool = False,
    generate_layer2b_explanations: bool = False,
    on_failure: str = "skip",
) -> list[AssessmentItem]:
    """Build a batch of ``AssessmentItem``\\ s by iterating over ``segments``.

    Segment selection (length filtering, ToM stratification, clean ratio)
    is the caller's responsibility — this builder only assembles items
    one-by-one over whatever list of segments it receives. That keeps
    the canonical pipeline package free of research-specific stratification
    while still giving callers a single entry point that exercises all
    four pipeline stages.

    Args:
        segments: The segments to turn into items, in the order to
            process them. Stratification and shuffling happen upstream.
        llm_config: Shared LLM config (forwarded to every stage).
        pathway: Applied uniformly to all segments in this batch. Mixing
            controlled + authentic in one batch requires two calls.
        error_profile: Required for ``CONTROLLED``.
        mt_outputs: Required for ``AUTHENTIC``: dict keyed by
            ``segment_id`` whose value is the corresponding
            ``MTOutput``. Segments without a matching MT output are
            skipped with a warning.
        mt_system, codebook, tag_format, scaffolding_level,
        difficulty_level, estimated_time_minutes,
        generate_layer1_explanations, generate_layer2a_explanations,
        generate_layer2b_explanations:
            Forwarded to each ``build_item`` call.
        on_failure: ``"skip"`` (default) logs the exception and moves
            on; ``"raise"`` re-raises the first failure.

    Returns:
        List of successfully-built items, in input order minus skipped
        failures.
    """
    if pathway == ItemPathway.CONTROLLED and error_profile is None:
        raise ValueError("error_profile is required for the CONTROLLED pathway")
    if pathway == ItemPathway.AUTHENTIC and not mt_outputs:
        raise ValueError("mt_outputs (dict keyed by segment_id) is required for AUTHENTIC")
    if on_failure not in ("skip", "raise"):
        raise ValueError(f"on_failure must be 'skip' or 'raise', got {on_failure!r}")

    if codebook is None:
        codebook = load_default_codebook()

    items: list[AssessmentItem] = []
    for i, segment in enumerate(segments):
        mt_out: Optional[MTOutput] = None
        if pathway == ItemPathway.AUTHENTIC:
            mt_out = (mt_outputs or {}).get(segment.segment_id)
            if mt_out is None:
                logger.warning(
                    "build_batch: no MTOutput for segment %s; skipping",
                    segment.segment_id,
                )
                continue

        try:
            item = await build_item(
                segment=segment,
                llm_config=llm_config,
                pathway=pathway,
                mt_system=mt_system,
                error_profile=error_profile,
                mt_output=mt_out,
                codebook=codebook,
                tag_format=tag_format,
                scaffolding_level=scaffolding_level,
                difficulty_level=difficulty_level,
                estimated_time_minutes=estimated_time_minutes,
                generate_layer1_explanations=generate_layer1_explanations,
                generate_layer2a_explanations=generate_layer2a_explanations,
                generate_layer2b_explanations=generate_layer2b_explanations,
            )
            items.append(item)
        except Exception:
            logger.exception(
                "build_batch: failed to build item %d/%d (segment %s)",
                i + 1, len(segments), segment.segment_id,
            )
            if on_failure == "raise":
                raise

    logger.info(
        "build_batch: assembled %d / %d items (pathway=%s)",
        len(items), len(segments), pathway.value,
    )
    return items
