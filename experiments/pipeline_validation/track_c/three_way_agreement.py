"""Track C2: Three-way agreement analysis (Pipeline x Human x GEMBA).

Aligns error spans across three annotation sources using IoU matching,
then computes pairwise Cohen's kappa, three-way overlap statistics,
and a Cochran-Armitage trend test for human-GEMBA agreement across
ToM levels.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel
from tompe.schemas.error import InjectedError
from tompe.schemas.expert_annotation import (
    AnnotatedError,
    ExpertAnnotation,
    GEMBAAnnotatedError,
    GEMBAAnnotation,
    AnnotationSetItem,
)
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    IOU_THRESHOLD,
    RESULTS_DIR,
    TOM_LEVELS,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpanMatch:
    """A matched error location across annotators."""

    pipeline_detected: bool
    human_detected: bool
    gemba_detected: bool
    pipeline_category: str | None
    human_category: str | None
    gemba_category: str | None
    pipeline_severity: str | None
    human_severity: str | None
    gemba_severity: str | None
    tom_level: str | None


# ---------------------------------------------------------------------------
# Span IoU
# ---------------------------------------------------------------------------

def _span_iou(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    """Compute Intersection over Union for two character spans."""
    inter_start = max(a_start, b_start)
    inter_end = min(a_end, b_end)
    intersection = max(0, inter_end - inter_start)

    union = (a_end - a_start) + (b_end - b_start) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------

def _cohens_kappa(y1: list[bool], y2: list[bool]) -> float:
    """Compute Cohen's kappa between two binary label lists.

    Falls back to sklearn if available; otherwise uses manual computation.
    """
    if len(y1) != len(y2) or not y1:
        return 0.0

    try:
        from sklearn.metrics import cohen_kappa_score
        return float(cohen_kappa_score(y1, y2))
    except ImportError:
        pass

    # Manual computation
    n = len(y1)
    a_and_b = sum(a and b for a, b in zip(y1, y2))
    not_a_and_not_b = sum(not a and not b for a, b in zip(y1, y2))
    a_not_b = sum(a and not b for a, b in zip(y1, y2))
    not_a_b = sum(not a and b for a, b in zip(y1, y2))

    po = (a_and_b + not_a_and_not_b) / n
    p_yes = ((a_and_b + a_not_b) / n) * ((a_and_b + not_a_b) / n)
    p_no = ((not_a_b + not_a_and_not_b) / n) * ((a_not_b + not_a_and_not_b) / n)
    pe = p_yes + p_no

    if abs(1.0 - pe) < 1e-10:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


# ---------------------------------------------------------------------------
# Cochran-Armitage trend test
# ---------------------------------------------------------------------------

def _cochran_armitage_trend(
    successes: list[int],
    totals: list[int],
    scores: list[float] | None = None,
) -> dict:
    """Run a Cochran-Armitage test for trend in proportions.

    Uses scipy if available; otherwise returns a manual z-statistic.

    Args:
        successes: Number of "successes" per group.
        totals: Total observations per group.
        scores: Numeric scores for each group (default: 0, 1, 2, ...).

    Returns:
        Dict with ``z_statistic``, ``p_value``, and ``trend_direction``.
    """
    k = len(successes)
    if scores is None:
        scores = list(range(k))

    n = sum(totals)
    if n == 0:
        return {"z_statistic": 0.0, "p_value": 1.0, "trend_direction": "none"}

    p_hat = sum(successes) / n

    # Weighted numerator and denominator
    n_arr = totals
    t_arr = scores
    r_arr = successes

    numerator = sum(t_arr[i] * (r_arr[i] - n_arr[i] * p_hat) for i in range(k))
    t_bar = sum(t_arr[i] * n_arr[i] for i in range(k)) / n
    denominator_sq = p_hat * (1 - p_hat) * sum(
        n_arr[i] * (t_arr[i] - t_bar) ** 2 for i in range(k)
    )

    if denominator_sq <= 0:
        return {"z_statistic": 0.0, "p_value": 1.0, "trend_direction": "none"}

    z = numerator / math.sqrt(denominator_sq)

    # p-value from normal distribution
    try:
        from scipy.stats import norm
        p_value = float(2 * norm.sf(abs(z)))
    except ImportError:
        # Approximate two-tailed p-value using error function
        p_value = math.erfc(abs(z) / math.sqrt(2))

    direction = "increasing" if z > 0 else ("decreasing" if z < 0 else "none")

    return {
        "z_statistic": round(z, 4),
        "p_value": round(p_value, 6),
        "trend_direction": direction,
    }


# ---------------------------------------------------------------------------
# Core alignment
# ---------------------------------------------------------------------------

def align_annotations(
    item: AssessmentItem,
    human: ExpertAnnotation,
    gemba: GEMBAAnnotation,
    iou_threshold: float = IOU_THRESHOLD,
) -> list[SpanMatch]:
    """Align error spans across three sources using IoU matching.

    For each pipeline error span, find the best-matching human and GEMBA
    spans (IoU >= threshold).  Also pick up unmatched human/GEMBA spans
    as separate entries.

    Args:
        item: The assessment item with pipeline ground-truth errors.
        human: Expert annotation for this item.
        gemba: GEMBA-MQM annotation for this item.
        iou_threshold: Minimum IoU to consider a span match.

    Returns:
        List of SpanMatch objects.
    """
    # Extract pipeline error spans
    pipeline_spans = []
    for err in item.errors:
        cat = err.primary_tag if isinstance(err.primary_tag, str) else err.primary_tag.value
        sev = err.severity if isinstance(err.severity, str) else err.severity.value
        tom = err.tom_level if isinstance(err.tom_level, str) else err.tom_level.value
        pipeline_spans.append({
            "start": err.span_start,
            "end": err.span_end,
            "category": cat,
            "severity": sev,
            "tom_level": tom,
        })

    human_spans = [
        {
            "start": e.span_start,
            "end": e.span_end,
            "category": e.category if isinstance(e.category, str) else e.category.value,
            "severity": e.severity if isinstance(e.severity, str) else e.severity.value,
        }
        for e in human.errors
    ]

    gemba_spans = [
        {
            "start": e.span_start,
            "end": e.span_end,
            "category": e.category,
            "severity": e.severity,
        }
        for e in gemba.errors
    ]

    matched_human: set[int] = set()
    matched_gemba: set[int] = set()
    matches: list[SpanMatch] = []

    # Match pipeline spans to human and GEMBA
    for p_span in pipeline_spans:
        best_h_idx, best_h_iou = -1, 0.0
        for h_idx, h_span in enumerate(human_spans):
            if h_idx in matched_human:
                continue
            iou = _span_iou(p_span["start"], p_span["end"], h_span["start"], h_span["end"])
            if iou >= iou_threshold and iou > best_h_iou:
                best_h_idx, best_h_iou = h_idx, iou

        best_g_idx, best_g_iou = -1, 0.0
        for g_idx, g_span in enumerate(gemba_spans):
            if g_idx in matched_gemba:
                continue
            iou = _span_iou(p_span["start"], p_span["end"], g_span["start"], g_span["end"])
            if iou >= iou_threshold and iou > best_g_iou:
                best_g_idx, best_g_iou = g_idx, iou

        h_detected = best_h_idx >= 0
        g_detected = best_g_idx >= 0

        if h_detected:
            matched_human.add(best_h_idx)
        if g_detected:
            matched_gemba.add(best_g_idx)

        matches.append(SpanMatch(
            pipeline_detected=True,
            human_detected=h_detected,
            gemba_detected=g_detected,
            pipeline_category=p_span["category"],
            human_category=human_spans[best_h_idx]["category"] if h_detected else None,
            gemba_category=gemba_spans[best_g_idx]["category"] if g_detected else None,
            pipeline_severity=p_span["severity"],
            human_severity=human_spans[best_h_idx]["severity"] if h_detected else None,
            gemba_severity=gemba_spans[best_g_idx]["severity"] if g_detected else None,
            tom_level=p_span["tom_level"],
        ))

    # Unmatched human spans (false positives or errors not in pipeline)
    for h_idx, h_span in enumerate(human_spans):
        if h_idx in matched_human:
            continue
        # Check if any GEMBA span matches
        best_g_idx, best_g_iou = -1, 0.0
        for g_idx, g_span in enumerate(gemba_spans):
            if g_idx in matched_gemba:
                continue
            iou = _span_iou(h_span["start"], h_span["end"], g_span["start"], g_span["end"])
            if iou >= iou_threshold and iou > best_g_iou:
                best_g_idx, best_g_iou = g_idx, iou

        if best_g_idx >= 0:
            matched_gemba.add(best_g_idx)

        matches.append(SpanMatch(
            pipeline_detected=False,
            human_detected=True,
            gemba_detected=best_g_idx >= 0,
            pipeline_category=None,
            human_category=h_span["category"],
            gemba_category=(
                gemba_spans[best_g_idx]["category"] if best_g_idx >= 0 else None
            ),
            pipeline_severity=None,
            human_severity=h_span["severity"],
            gemba_severity=(
                gemba_spans[best_g_idx]["severity"] if best_g_idx >= 0 else None
            ),
            tom_level=None,
        ))

    # Unmatched GEMBA spans
    for g_idx, g_span in enumerate(gemba_spans):
        if g_idx in matched_gemba:
            continue
        matches.append(SpanMatch(
            pipeline_detected=False,
            human_detected=False,
            gemba_detected=True,
            pipeline_category=None,
            human_category=None,
            gemba_category=g_span["category"],
            pipeline_severity=None,
            human_severity=None,
            gemba_severity=g_span["severity"],
            tom_level=None,
        ))

    return matches


# ---------------------------------------------------------------------------
# Agreement metrics
# ---------------------------------------------------------------------------

def compute_pairwise_agreement(matches: list[SpanMatch]) -> dict:
    """Compute detection rates and Cohen's kappa for each annotator pair.

    Returns a dict with keys:
      - pipeline_human_kappa, pipeline_gemba_kappa, human_gemba_kappa
      - pipeline_human_detection, pipeline_gemba_detection, human_gemba_detection
      - human_recall (vs pipeline), gemba_recall (vs pipeline)
    """
    if not matches:
        return {
            "pipeline_human_kappa": 0.0,
            "pipeline_gemba_kappa": 0.0,
            "human_gemba_kappa": 0.0,
            "human_recall": 0.0,
            "gemba_recall": 0.0,
            "n_matches": 0,
        }

    p = [m.pipeline_detected for m in matches]
    h = [m.human_detected for m in matches]
    g = [m.gemba_detected for m in matches]

    # Pipeline ground-truth count
    n_pipeline = sum(p)
    human_on_pipeline = sum(m.human_detected for m in matches if m.pipeline_detected)
    gemba_on_pipeline = sum(m.gemba_detected for m in matches if m.pipeline_detected)

    return {
        "pipeline_human_kappa": round(_cohens_kappa(p, h), 4),
        "pipeline_gemba_kappa": round(_cohens_kappa(p, g), 4),
        "human_gemba_kappa": round(_cohens_kappa(h, g), 4),
        "human_recall": round(human_on_pipeline / n_pipeline, 4) if n_pipeline else 0.0,
        "gemba_recall": round(gemba_on_pipeline / n_pipeline, 4) if n_pipeline else 0.0,
        "n_matches": len(matches),
    }


def compute_agreement_by_tom(
    all_matches: list[SpanMatch],
) -> dict[str, dict]:
    """Break down agreement metrics by ToM level.

    Returns a dict keyed by ToM level string, each containing the
    pairwise agreement metrics for that subset.
    """
    by_level: dict[str, list[SpanMatch]] = {lvl: [] for lvl in TOM_LEVELS}
    unassigned: list[SpanMatch] = []

    for m in all_matches:
        if m.tom_level and m.tom_level in by_level:
            by_level[m.tom_level].append(m)
        else:
            unassigned.append(m)

    results: dict[str, dict] = {}
    for lvl in TOM_LEVELS:
        subset = by_level[lvl]
        if subset:
            results[lvl] = compute_pairwise_agreement(subset)
            results[lvl]["n_spans"] = len(subset)
        else:
            results[lvl] = {"n_spans": 0, "note": "no spans at this level"}

    if unassigned:
        results["unassigned"] = {
            "n_spans": len(unassigned),
            "note": "spans without ToM level (human/GEMBA only)",
        }

    return results


def compute_three_way_overlap(matches: list[SpanMatch]) -> dict:
    """Compute overlap statistics for three-way detection.

    Returns percentages for:
      - all_three: detected by pipeline, human, and GEMBA
      - human_only: detected by human but not pipeline or GEMBA
      - gemba_only: detected by GEMBA but not pipeline or human
      - pipeline_only: in pipeline but missed by both human and GEMBA
      - human_and_gemba_not_pipeline: both annotators found it, but not in GT
      - missed_by_both: in pipeline but neither human nor GEMBA found it
    """
    if not matches:
        return {
            "all_three": 0.0,
            "human_only": 0.0,
            "gemba_only": 0.0,
            "pipeline_only": 0.0,
            "human_and_gemba_not_pipeline": 0.0,
            "missed_by_both": 0.0,
            "total_spans": 0,
        }

    n = len(matches)
    all_three = sum(m.pipeline_detected and m.human_detected and m.gemba_detected for m in matches)
    human_only = sum(m.human_detected and not m.pipeline_detected and not m.gemba_detected for m in matches)
    gemba_only = sum(m.gemba_detected and not m.pipeline_detected and not m.human_detected for m in matches)
    pipeline_only = sum(m.pipeline_detected and not m.human_detected and not m.gemba_detected for m in matches)
    h_and_g = sum(m.human_detected and m.gemba_detected and not m.pipeline_detected for m in matches)
    missed = sum(m.pipeline_detected and not m.human_detected and not m.gemba_detected for m in matches)

    return {
        "all_three": round(all_three / n, 4),
        "human_only": round(human_only / n, 4),
        "gemba_only": round(gemba_only / n, 4),
        "pipeline_only": round(pipeline_only / n, 4),
        "human_and_gemba_not_pipeline": round(h_and_g / n, 4),
        "missed_by_both": round(missed / n, 4),
        "total_spans": n,
        "counts": {
            "all_three": all_three,
            "human_only": human_only,
            "gemba_only": gemba_only,
            "pipeline_only": pipeline_only,
            "human_and_gemba_not_pipeline": h_and_g,
            "missed_by_both": missed,
        },
    }


def compute_trend_test(
    all_matches: list[SpanMatch],
) -> dict:
    """Cochran-Armitage trend test for human-GEMBA agreement across ToM levels.

    Tests whether the proportion of spans where both human and GEMBA agree
    on detection changes systematically across ToM levels (ordered L0..L3).
    """
    successes: list[int] = []
    totals: list[int] = []

    for lvl in TOM_LEVELS:
        subset = [m for m in all_matches if m.tom_level == lvl]
        total = len(subset)
        # "Success" = both human and GEMBA agree on detection status
        agreed = sum(
            1 for m in subset if m.human_detected == m.gemba_detected
        )
        totals.append(total)
        successes.append(agreed)

    result = _cochran_armitage_trend(successes, totals)
    result["per_level"] = {
        lvl: {
            "agreement_rate": round(s / t, 4) if t > 0 else None,
            "n": t,
        }
        for lvl, s, t in zip(TOM_LEVELS, successes, totals)
    }
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_three_way_analysis(
    items: list[AssessmentItem],
    human_annotations: dict[str, ExpertAnnotation],  # keyed by item_id
    gemba_annotations: dict[str, GEMBAAnnotation],  # keyed by item_id
    iou_threshold: float = IOU_THRESHOLD,
) -> dict:
    """Run the full three-way agreement analysis.

    Args:
        items: Assessment items with pipeline ground truth.
        human_annotations: Expert annotations keyed by item_id.
        gemba_annotations: GEMBA annotations keyed by item_id.
        iou_threshold: IoU threshold for span matching.

    Returns:
        Complete analysis results dict.
    """
    all_matches: list[SpanMatch] = []
    skipped = 0

    for item in items:
        human = human_annotations.get(item.item_id)
        gemba = gemba_annotations.get(item.item_id)

        if human is None or gemba is None:
            skipped += 1
            logger.debug(
                "Skipping item %s: human=%s, gemba=%s",
                item.item_id,
                "present" if human else "missing",
                "present" if gemba else "missing",
            )
            continue

        matches = align_annotations(item, human, gemba, iou_threshold)
        all_matches.extend(matches)

    if skipped:
        logger.warning("Skipped %d items due to missing annotations", skipped)

    pairwise = compute_pairwise_agreement(all_matches)
    by_tom = compute_agreement_by_tom(all_matches)
    overlap = compute_three_way_overlap(all_matches)
    trend = compute_trend_test(all_matches)

    return {
        "pairwise_agreement": pairwise,
        "agreement_by_tom": by_tom,
        "three_way_overlap": overlap,
        "cochran_armitage_trend": trend,
        "n_items_analysed": len(items) - skipped,
        "n_items_skipped": skipped,
        "n_total_spans": len(all_matches),
        "iou_threshold": iou_threshold,
    }


def save_results(analysis: dict, output_dir: Path | None = None) -> Path:
    """Save three-way agreement results to JSON."""
    ensure_dirs()
    out = (output_dir or RESULTS_DIR / "track_c") / "three_way_agreement.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Three-way agreement results saved to %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Track C2: three-way agreement analysis")
    parser.add_argument("--items-file", type=Path, required=True, help="Pipeline items JSON")
    parser.add_argument("--human-file", type=Path, required=True, help="Expert annotations JSON")
    parser.add_argument("--gemba-file", type=Path, required=True, help="GEMBA annotations JSON")
    parser.add_argument("--iou-threshold", type=float, default=IOU_THRESHOLD)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    # Load data
    items_raw = json.loads(args.items_file.read_text(encoding="utf-8"))
    items = [AssessmentItem.model_validate(r) for r in items_raw]

    human_raw = json.loads(args.human_file.read_text(encoding="utf-8"))
    human_annotations = {
        r["item_id"]: ExpertAnnotation.model_validate(r) for r in human_raw
    }

    gemba_raw = json.loads(args.gemba_file.read_text(encoding="utf-8"))
    gemba_annotations = {
        r["item_id"]: GEMBAAnnotation.model_validate(r) for r in gemba_raw
    }

    analysis = run_three_way_analysis(
        items, human_annotations, gemba_annotations, args.iou_threshold,
    )
    path = save_results(analysis, args.output_dir)
    print(f"Results saved to {path}")
    print(json.dumps(analysis, indent=2))
