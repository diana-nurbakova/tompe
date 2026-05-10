"""Track B: Ablation comparison across all 4 pipeline conditions.

Runs B0 (random), B1 (single-step), B2 (unconstrained), and the full
ToM-PE pipeline on the same 60 segments, then compares structural
pass rate, GEMBA detection rate, category fidelity, xCOMET score drop,
and text preservation rate.

Reference: pipeline-validation-spec-v2 section 4.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel
from tompe.schemas.error import InjectedError
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.baselines.random_perturbation import inject_random
from experiments.pipeline_validation.baselines.single_step_inject import inject_single_step
from experiments.pipeline_validation.baselines.unconstrained_inject import inject_unconstrained
from experiments.pipeline_validation.config import (
    BASELINE_CONDITIONS,
    BASELINE_ITEMS,
    RESULTS_DIR,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConditionResult:
    """Metrics for one ablation condition."""

    condition: str  # "B0_random", "B1_single_step", "B2_unconstrained", "full_pipeline"
    items: list[AssessmentItem] = field(default_factory=list)
    structural_pass_rate: float = 0.0
    gemba_detection_rate: float = 0.0
    category_fidelity: float | None = None  # None for B0/B2
    xcomet_score_drop: float = 0.0
    text_preservation_rate: float | None = None  # None for B0


@dataclass
class AblationResults:
    """Collected results across all 4 conditions."""

    conditions: list[ConditionResult] = field(default_factory=list)
    segments_used: list[str] = field(default_factory=list)  # segment_ids


# ---------------------------------------------------------------------------
# Track A metric imports (lazy, with fallback stubs)
# ---------------------------------------------------------------------------

def _import_track_a():
    """Import Track A metric functions, returning stubs if not yet implemented."""
    try:
        from experiments.pipeline_validation.track_a.structural_check import check_item
    except ImportError:
        logger.warning("track_a.structural_check not available; using stub")
        check_item = None

    try:
        from experiments.pipeline_validation.track_a.gemba_detection import run_gemba_detection
    except ImportError:
        logger.warning("track_a.gemba_detection not available; using stub")
        run_gemba_detection = None

    try:
        from experiments.pipeline_validation.track_a.xcomet_scoring import score_items
    except ImportError:
        logger.warning("track_a.xcomet_scoring not available; using stub")
        score_items = None

    return check_item, run_gemba_detection, score_items


# ---------------------------------------------------------------------------
# Text preservation
# ---------------------------------------------------------------------------

def _text_preservation_ratio(
    reference: str,
    presented: str,
    errors: list,
) -> float:
    """Compute SequenceMatcher ratio on text *outside* injected error spans.

    Both the presented text and the reference are masked: error spans are
    removed from the presented text, and the corresponding original-text
    spans are removed from the reference, so the comparison covers only the
    surrounding (non-error) regions.

    Returns a float in [0, 1].  Items pass if ratio >= 0.95.
    """
    from tompe.schemas.error import InjectedError

    if not errors:
        # No errors — compare the full texts
        if not reference and not presented:
            return 1.0
        return difflib.SequenceMatcher(None, reference, presented).ratio()

    # Remove error spans from the presented text
    p_chars = list(presented)
    for err in sorted(errors, key=lambda e: e.span_start, reverse=True):
        s = max(0, err.span_start)
        e = min(len(p_chars), err.span_end)
        p_chars[s:e] = []
    presented_clean = "".join(p_chars)

    # Remove the original-text regions from the reference.
    # We locate each original_text in the reference and remove it.
    ref_clean = reference
    for err in errors:
        if not isinstance(err, InjectedError):
            continue
        orig = err.original_text
        if orig:
            pos = ref_clean.find(orig)
            if pos >= 0:
                ref_clean = ref_clean[:pos] + ref_clean[pos + len(orig):]

    if not ref_clean and not presented_clean:
        return 1.0

    return difflib.SequenceMatcher(None, ref_clean, presented_clean).ratio()


def compute_text_preservation(items: list[AssessmentItem]) -> float:
    """Fraction of items whose non-error text is >= 95 % similar to reference."""
    if not items:
        return 0.0

    passed = 0
    for item in items:
        ratio = _text_preservation_ratio(
            item.reference_translation,
            item.presented_text,
            item.errors,
        )
        if ratio >= 0.95:
            passed += 1

    return passed / len(items)


# ---------------------------------------------------------------------------
# Per-condition runners
# ---------------------------------------------------------------------------

async def _run_condition_b0(
    segments: list[CorpusSegment],
) -> list[AssessmentItem]:
    """Run B0 (random perturbation) on segments."""
    items: list[AssessmentItem] = []
    for seg in segments:
        try:
            modified_text, errors = await inject_random(seg)
            item = _segment_to_item(seg, modified_text, errors, "B0_random")
            items.append(item)
        except Exception:
            logger.exception("B0 failed for segment %s", seg.segment_id)
    return items


async def _run_condition_b1(
    segments: list[CorpusSegment],
    llm_config: dict,
) -> list[AssessmentItem]:
    """Run B1 (single-step injection) on segments."""
    import random as _rng
    from tompe.pipeline.mqm_taxonomy import ERROR_TYPE_SPECS

    items: list[AssessmentItem] = []
    for seg in segments:
        try:
            # Pick a random error spec and severity for this segment
            spec = _rng.choice(ERROR_TYPE_SPECS)
            severity = _rng.choice(spec.severity_range)
            modified_text, errors = await inject_single_step(
                seg, error_spec=spec, severity=severity, llm_config=llm_config,
            )
            item = _segment_to_item(seg, modified_text, errors, "B1_single_step")
            items.append(item)
        except Exception:
            logger.exception("B1 failed for segment %s", seg.segment_id)
    return items


async def _run_condition_b2(
    segments: list[CorpusSegment],
    llm_config: dict,
) -> list[AssessmentItem]:
    """Run B2 (unconstrained injection) on segments."""
    items: list[AssessmentItem] = []
    for seg in segments:
        try:
            modified_text, errors = await inject_unconstrained(seg, llm_config=llm_config)
            item = _segment_to_item(seg, modified_text, errors, "B2_unconstrained")
            items.append(item)
        except Exception:
            logger.exception("B2 failed for segment %s", seg.segment_id)
    return items


def _segment_to_item(
    seg: CorpusSegment,
    presented_text: str,
    errors: list[InjectedError],
    condition: str,
) -> AssessmentItem:
    """Wrap a perturbed segment into an AssessmentItem for metric evaluation."""
    from tompe.schemas.enums import AnnotationLevel, ItemPathway, MQMCategory

    tom_profile: dict[TOMLevel, int] = {level: 0 for level in TOMLevel}
    mqm_profile: dict[MQMCategory, int] = {cat: 0 for cat in MQMCategory}
    for err in errors:
        tom_profile[err.tom_level] = tom_profile.get(err.tom_level, 0) + 1

    metadata = {
        "tom_profile": {k.value: v for k, v in tom_profile.items()},
        "mqm_profile": {k.value: v for k, v in mqm_profile.items()},
        "estimated_time_minutes": 2.0,
        "has_clean_segments": False,
        "scaffolding_level": AnnotationLevel.ANALYST.value,
        "pathway": ItemPathway.CONTROLLED.value,
        "translation_direction": f"{seg.source_lang}->{seg.target_lang}",
    }

    return AssessmentItem.model_validate({
        "item_id": f"{condition}_{seg.segment_id}",
        "segment_id": seg.segment_id,
        "source_text": seg.source_text,
        "source_lang": seg.source_lang,
        "target_lang": seg.target_lang,
        "presented_text": presented_text,
        "reference_translation": seg.reference_translation,
        "mt_system": "reference_perturbed",
        "pathway": ItemPathway.CONTROLLED.value,
        "errors": [e.model_dump() for e in errors],
        "clean_spans": [],
        "annotations": [],
        "annotation_config": {"level": AnnotationLevel.ANALYST.value},
        "difficulty_level": 3,
        "domain": seg.domain,
        "metadata": metadata,
    })


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

async def _compute_metrics(
    condition: str,
    items: list[AssessmentItem],
    llm_config: dict | None = None,
) -> ConditionResult:
    """Compute all metrics for one condition's items."""
    check_item, run_gemba_detection, score_items = _import_track_a()

    result = ConditionResult(condition=condition, items=items)

    # Structural pass rate
    if check_item is not None and items:
        passes = sum(1 for item in items if check_item(item).passed)
        result.structural_pass_rate = passes / len(items)
    else:
        logger.info("Skipping structural check for %s (no checker or no items)", condition)

    # GEMBA detection rate — run per-item, requires llm_config
    if run_gemba_detection is not None and items and llm_config:
        try:
            detected = 0
            for item in items:
                try:
                    det_result = await run_gemba_detection(item, llm_config)
                    if det_result.detected > 0:
                        detected += 1
                except Exception:
                    pass
            result.gemba_detection_rate = detected / len(items)
        except Exception:
            logger.exception("GEMBA detection failed for %s", condition)

    # Category fidelity: only meaningful for B1 and full_pipeline (codebook-guided)
    if condition in ("B1_single_step", "full_pipeline"):
        result.category_fidelity = _category_fidelity(items)
    else:
        result.category_fidelity = None

    # xCOMET score drop
    if score_items is not None and items:
        try:
            scores = await score_items(items)
            result.xcomet_score_drop = scores.get("mean_score_drop", 0.0)
        except Exception:
            logger.exception("xCOMET scoring failed for %s", condition)

    # Text preservation rate: not meaningful for B0 (word-level corruption)
    if condition != "B0_random":
        result.text_preservation_rate = compute_text_preservation(items)
    else:
        result.text_preservation_rate = None

    return result


def _category_fidelity(items: list[AssessmentItem]) -> float:
    """Fraction of errors whose primary_tag is a valid PrimaryTag value."""
    if not items:
        return 0.0

    valid_tags = {t.value for t in PrimaryTag}
    total = 0
    valid = 0
    for item in items:
        for err in item.errors:
            total += 1
            tag = err.primary_tag if isinstance(err.primary_tag, str) else err.primary_tag.value
            if tag in valid_tags:
                valid += 1

    return valid / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

async def run_ablation(
    segments: list[CorpusSegment],
    llm_config: dict,
    full_pipeline_items: list[AssessmentItem] | None = None,
    skip_gemba: bool = False,
) -> AblationResults:
    """Run all 4 conditions on the same segments and compute metrics.

    Args:
        segments: The shared set of corpus segments (typically 60).
        llm_config: LLM configuration dict for B1, B2, and full pipeline.
        full_pipeline_items: Pre-generated full pipeline items for the same
            segments.  If None, the full_pipeline condition is skipped.
        skip_gemba: If True, skip GEMBA detection (saves API calls).

    Returns:
        AblationResults with per-condition metrics.
    """
    logger.info("Starting ablation study on %d segments", len(segments))

    segment_ids = [seg.segment_id for seg in segments]

    # Run baseline conditions
    b0_items = await _run_condition_b0(segments)
    b1_items = await _run_condition_b1(segments, llm_config)
    b2_items = await _run_condition_b2(segments, llm_config)

    # Full pipeline: use pre-generated items if available
    full_items = full_pipeline_items or []
    if not full_items:
        logger.warning(
            "No full pipeline items provided; full_pipeline condition will be empty. "
            "Pass full_pipeline_items from the generated batch."
        )

    # Compute metrics for each condition
    gemba_config = llm_config if not skip_gemba else None
    conditions_data = [
        ("B0_random", b0_items),
        ("B1_single_step", b1_items),
        ("B2_unconstrained", b2_items),
        ("full_pipeline", full_items),
    ]

    condition_results = []
    for cond_name, items in conditions_data:
        result = await _compute_metrics(cond_name, items, llm_config=gemba_config)
        condition_results.append(result)
        logger.info(
            "Condition %s: %d items, structural=%.2f, gemba=%.2f",
            cond_name, len(items),
            result.structural_pass_rate, result.gemba_detection_rate,
        )

    return AblationResults(conditions=condition_results, segments_used=segment_ids)


def compare_conditions(results: AblationResults) -> dict:
    """Generate comparison table data from ablation results.

    Returns a dict with a ``table`` key containing a list of row dicts,
    and a ``summary`` key with aggregate statistics.
    """
    rows = []
    for cond in results.conditions:
        rows.append({
            "condition": cond.condition,
            "n_items": len(cond.items),
            "structural_pass_rate": round(cond.structural_pass_rate, 3),
            "gemba_detection_rate": round(cond.gemba_detection_rate, 3),
            "category_fidelity": (
                round(cond.category_fidelity, 3)
                if cond.category_fidelity is not None
                else None
            ),
            "xcomet_score_drop": round(cond.xcomet_score_drop, 4),
            "text_preservation_rate": (
                round(cond.text_preservation_rate, 3)
                if cond.text_preservation_rate is not None
                else None
            ),
        })

    # Summary: improvement of full pipeline over each baseline
    full = next((c for c in results.conditions if c.condition == "full_pipeline"), None)
    deltas = {}
    if full is not None:
        for cond in results.conditions:
            if cond.condition == "full_pipeline":
                continue
            deltas[cond.condition] = {
                "structural_delta": round(
                    full.structural_pass_rate - cond.structural_pass_rate, 3
                ),
                "gemba_delta": round(
                    full.gemba_detection_rate - cond.gemba_detection_rate, 3
                ),
            }

    return {
        "segments_used": results.segments_used,
        "n_segments": len(results.segments_used),
        "table": rows,
        "deltas_vs_full": deltas,
    }


def save_results(results: AblationResults, output_dir: Path | None = None) -> Path:
    """Serialise ablation results to JSON.

    Args:
        results: The ablation results to save.
        output_dir: Directory to write to (default: RESULTS_DIR / track_b).

    Returns:
        Path to the saved JSON file.
    """
    ensure_dirs()
    out = (output_dir or RESULTS_DIR / "track_b") / "ablation_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Save both the comparison table and the per-condition items (for recomputation)
    comparison = compare_conditions(results)
    # Include serialised items so metrics can be recomputed without re-running
    conditions_data = []
    for cond in results.conditions:
        conditions_data.append({
            "condition": cond.condition,
            "items": [item.model_dump(mode="json") for item in cond.items],
        })
    comparison["conditions"] = conditions_data
    out.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Ablation results saved to %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    from experiments.pipeline_validation.config import (
        BASELINE_ITEMS,
        DEFAULT_LLM_CONFIG,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Track B: ablation comparison")
    parser.add_argument(
        "--segments-file",
        type=Path,
        help="JSON file containing CorpusSegment objects",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=BASELINE_ITEMS,
        help=f"Number of segments to use (default: {BASELINE_ITEMS})",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    async def _main() -> None:
        # Load segments
        if args.segments_file and args.segments_file.exists():
            raw = json.loads(args.segments_file.read_text(encoding="utf-8"))
            segments = [CorpusSegment.model_validate(s) for s in raw[: args.max_segments]]
        else:
            logger.warning("No segments file provided; using dummy segment for smoke test")
            segments = [
                CorpusSegment(
                    segment_id="demo-001",
                    source_text="The European Commission has proposed new regulations.",
                    reference_translation=(
                        "La Commission europeenne a propose de nouvelles reglementations."
                    ),
                    source_lang="en",
                    target_lang="fr",
                    corpus_origin="europarl",
                    domain="parliamentary",
                    complexity_score=0.4,
                    terminology_density=0.1,
                    register="formal",
                ),
            ]

        results = await run_ablation(segments, DEFAULT_LLM_CONFIG)
        path = save_results(results, args.output_dir)
        print(f"Results saved to {path}")

        comparison = compare_conditions(results)
        print(json.dumps(comparison, indent=2))

    asyncio.run(_main())
