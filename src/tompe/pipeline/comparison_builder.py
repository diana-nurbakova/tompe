"""Build L3 comparison-mode items (multi-MT side-by-side + ranking + human-vs-MT).

System spec §3.6 / §5 / §7.4 + UI spec §3.5.

A comparison item presents the source segment alongside multiple MT outputs
(plus, optionally, the human reference as one of the choices). The student
either ranks the systems holistically (Skill B, COMPARATIVE_RANKING) or
evaluates each system independently (Skill A, INDEPENDENT_EVAL — wired
schema-side but spans-per-system are not yet generated automatically).

This module is intentionally lightweight: it only assembles the
``AssessmentItem`` from MTOutputs the caller has already produced. The
caller is responsible for actually running the MT systems (via
``mt_generator.translate_segment``) and for tagging the human reference.

Design notes / locked decisions:

- The human reference, when included, is an ``MTOutput`` with
  ``mt_system="human"``, ``system_type="human"``, ``is_human_reference=True``,
  and ``mt_text == segment.reference_translation``. This keeps the
  comparison_outputs list homogeneous and lets the student UI render it
  exactly like the others without revealing the source.
- The student UI is responsible for *display masking* (System A / B / C).
  The schema and the server store the real ``mt_system`` ids so scoring
  can recover them.
- For Skill B scoring, the expert ranking is derived from
  ``MTOutput.quality_score`` (descending). When all scores are None, the
  expert ranking falls back to the comparison_outputs list order — useful
  for tests but should be flagged at run time.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from tompe.schemas.annotation import AnnotationConfig
from tompe.schemas.corpus import CorpusSegment, MTOutput
from tompe.schemas.enums import (
    AnnotationLevel,
    ComparisonType,
    ItemPathway,
    MQMCategory,
    TOMLevel,
)
from tompe.schemas.item import AssessmentItem, ItemMetadata

logger = logging.getLogger(__name__)


def build_human_reference_output(segment: CorpusSegment) -> MTOutput:
    """Wrap the human reference translation as an MTOutput.

    Used as one of the choices in human-vs-MT discrimination at L3.
    """
    return MTOutput(
        mt_id=str(uuid.uuid4()),
        segment_id=segment.segment_id,
        mt_system="human",
        mt_text=segment.reference_translation,
        system_type="human",
        generation_timestamp=datetime.now(timezone.utc),
        is_human_reference=True,
    )


def build_comparison_item(
    segment: CorpusSegment,
    mt_outputs: list[MTOutput],
    *,
    comparison_type: ComparisonType = ComparisonType.COMPARATIVE_RANKING,
    include_human: bool = True,
    domain: str = "general",
    difficulty_level: int = 4,
    item_id: Optional[str] = None,
    estimated_time_minutes: float = 4.0,
) -> AssessmentItem:
    """Assemble a comparison-mode AssessmentItem.

    Args:
        segment: The source segment + human reference.
        mt_outputs: One MTOutput per machine system. Must not include the human
            reference — this function appends it when ``include_human=True``.
        comparison_type: Skill A (INDEPENDENT_EVAL) or Skill B
            (COMPARATIVE_RANKING). Skill A still requires per-system error
            spans to score; the UI surfaces a TODO until that lands.
        include_human: Whether to add the human reference as one of the
            choices. Required for the "which is human?" discrimination
            sub-task; can be False for pure machine-vs-machine ranking.
        difficulty_level: 1–5. Defaults to 4 (L3 territory).

    Returns:
        An ``AssessmentItem`` with ``comparison_outputs`` populated and
        ``comparison_type`` set. ``errors``/``annotations`` are empty;
        ``presented_text`` is the empty string (student UI uses
        comparison_outputs, not presented_text, at L3 comparison).
    """
    if not mt_outputs:
        raise ValueError("build_comparison_item: mt_outputs must be non-empty")
    if any(o.is_human_reference for o in mt_outputs):
        raise ValueError(
            "build_comparison_item: pass machine outputs only; the human "
            "reference is appended via include_human=True"
        )
    if include_human and len(mt_outputs) < 1:
        raise ValueError("Need at least 1 machine output when include_human=True")
    if not include_human and len(mt_outputs) < 2:
        raise ValueError("Need at least 2 machine outputs when include_human=False")

    # Compose the final comparison_outputs list. Order is preserved exactly
    # as supplied so callers can control display ordering; the UI is in
    # charge of masking to System A/B/C labels.
    outputs: list[MTOutput] = list(mt_outputs)
    if include_human:
        outputs.append(build_human_reference_output(segment))

    metadata = ItemMetadata(
        tom_profile={level: 0 for level in TOMLevel},
        mqm_profile={cat: 0 for cat in MQMCategory},
        estimated_time_minutes=estimated_time_minutes,
        has_clean_segments=False,
        scaffolding_level=AnnotationLevel.EXPERT,
        pathway=ItemPathway.CONTROLLED,  # arbitrary; comparison-mode doesn't inject
        translation_direction=f"{segment.source_lang}→{segment.target_lang}",
    )

    return AssessmentItem(
        item_id=item_id or str(uuid.uuid4()),
        segment_id=segment.segment_id,
        source_text=segment.source_text,
        source_lang=segment.source_lang,
        target_lang=segment.target_lang,
        # At L3 comparison the "presented_text" is intentionally empty;
        # the student reads from comparison_outputs side-by-side.
        presented_text="",
        reference_translation=segment.reference_translation,
        mt_system="comparison",  # sentinel; real systems are in comparison_outputs
        pathway=ItemPathway.CONTROLLED,
        errors=[],
        clean_spans=[],
        annotations=[],
        annotation_config=AnnotationConfig(level=AnnotationLevel.EXPERT),
        difficulty_level=difficulty_level,
        domain=domain,
        comparison_outputs=outputs,
        comparison_type=comparison_type,
        metadata=metadata,
    )


def derive_expert_ranking(outputs: list[MTOutput]) -> list[str]:
    """Compute the canonical expert ranking from MTOutput quality_score.

    Returns a list of ``mt_system`` ids sorted by quality_score (descending).
    Outputs with None ``quality_score`` keep their relative position from
    ``outputs`` after the scored systems (stable sort). Callers should warn
    if any ``quality_score`` is None — the result is then only a heuristic.
    """
    # Stable sort: scored systems descending by score; unscored keep order.
    scored = [(i, o) for i, o in enumerate(outputs) if o.quality_score is not None]
    unscored = [(i, o) for i, o in enumerate(outputs) if o.quality_score is None]
    scored.sort(key=lambda pair: pair[1].quality_score, reverse=True)
    if unscored:
        logger.warning(
            "derive_expert_ranking: %d/%d outputs have no quality_score; "
            "result is a heuristic fallback (input order preserved for unscored)",
            len(unscored), len(outputs),
        )
    return [o.mt_system for _, o in scored] + [o.mt_system for _, o in unscored]
