"""Track C3: Naturalness test -- pipeline-generated vs. authentic MT items.

Compares annotator behaviour on pipeline-generated items against authentic
MT items to check whether the injected errors are indistinguishable from
real MT errors.  Uses Mann-Whitney U for continuous variables and
Fisher's exact / chi-squared for categorical variables.
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel
from tompe.schemas.expert_annotation import (
    AnnotatedError,
    ExpertAnnotation,
    AnnotationSetItem,
)
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    RESULTS_DIR,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class NaturalnessComparison:
    """Comparison of annotator behaviour on pipeline vs. authentic items."""

    pipeline_stats: dict = field(default_factory=dict)
    authentic_stats: dict = field(default_factory=dict)
    p_values: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _mann_whitney_u(x: list[float], y: list[float]) -> dict:
    """Mann-Whitney U test for two independent samples.

    Returns dict with U statistic and p-value.
    """
    if not x or not y:
        return {"U": None, "p_value": None, "note": "insufficient data"}

    try:
        from scipy.stats import mannwhitneyu
        stat, p = mannwhitneyu(x, y, alternative="two-sided")
        return {"U": round(float(stat), 4), "p_value": round(float(p), 6)}
    except ImportError:
        logger.warning("scipy not available; Mann-Whitney U skipped")
        return {"U": None, "p_value": None, "note": "scipy not installed"}


def _fisher_exact_2x2(table: list[list[int]]) -> dict:
    """Fisher's exact test for a 2x2 contingency table.

    Args:
        table: [[a, b], [c, d]] counts.

    Returns:
        Dict with odds_ratio and p_value.
    """
    try:
        from scipy.stats import fisher_exact
        odds, p = fisher_exact(table)
        return {"odds_ratio": round(float(odds), 4), "p_value": round(float(p), 6)}
    except ImportError:
        logger.warning("scipy not available; Fisher's exact test skipped")
        return {"odds_ratio": None, "p_value": None, "note": "scipy not installed"}


def _chi2_contingency(table: list[list[int]]) -> dict:
    """Chi-squared test for a contingency table larger than 2x2.

    Args:
        table: List of rows, each a list of counts.

    Returns:
        Dict with chi2, p_value, and degrees of freedom.
    """
    try:
        from scipy.stats import chi2_contingency
        chi2, p, dof, _ = chi2_contingency(table)
        return {
            "chi2": round(float(chi2), 4),
            "p_value": round(float(p), 6),
            "dof": int(dof),
        }
    except ImportError:
        logger.warning("scipy not available; chi2 test skipped")
        return {"chi2": None, "p_value": None, "dof": None, "note": "scipy not installed"}


# ---------------------------------------------------------------------------
# Annotation statistics
# ---------------------------------------------------------------------------

def _compute_group_stats(annotations: list[ExpertAnnotation]) -> dict:
    """Compute descriptive statistics for a group of annotations.

    Returns:
        Dict with errors_per_item, time_per_item, false_positive_rate,
        confidence_dist, and raw lists for statistical tests.
    """
    if not annotations:
        return {
            "errors_per_item": {"mean": 0.0, "median": 0.0, "values": []},
            "time_per_item": {"mean": 0.0, "median": 0.0, "values": []},
            "false_positive_rate": 0.0,
            "confidence_dist": {},
            "n": 0,
        }

    errors_counts = [len(a.errors) for a in annotations]
    times = [a.duration_seconds for a in annotations]
    confidences = Counter(a.confidence for a in annotations)

    # False positive rate: items where annotator found errors but item was clean
    # We approximate: items where no_errors_found is False but the source is "clean"
    clean_annotations = [a for a in annotations if a.item_source == "clean"]
    if clean_annotations:
        false_positives = sum(1 for a in clean_annotations if not a.no_errors_found)
        fp_rate = false_positives / len(clean_annotations)
    else:
        fp_rate = 0.0

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _median(vals: list[float]) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        n = len(s)
        if n % 2 == 0:
            return (s[n // 2 - 1] + s[n // 2]) / 2
        return s[n // 2]

    return {
        "errors_per_item": {
            "mean": round(_mean(errors_counts), 3),
            "median": _median(errors_counts),
            "std": round(
                math.sqrt(sum((x - _mean(errors_counts)) ** 2 for x in errors_counts) / max(len(errors_counts), 1)),
                3,
            ),
            "values": errors_counts,
        },
        "time_per_item": {
            "mean": round(_mean(times), 2),
            "median": round(_median(times), 2),
            "std": round(
                math.sqrt(sum((x - _mean(times)) ** 2 for x in times) / max(len(times), 1)),
                2,
            ),
            "values": times,
        },
        "false_positive_rate": round(fp_rate, 4),
        "confidence_dist": dict(confidences),
        "n": len(annotations),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_naturalness(
    pipeline_annotations: list[ExpertAnnotation],
    authentic_annotations: list[ExpertAnnotation],
) -> NaturalnessComparison:
    """Compare annotator behaviour on pipeline vs. authentic items.

    Tests whether annotators behave differently when annotating
    pipeline-generated items compared to authentic MT items.  If the
    differences are not statistically significant, pipeline items are
    considered natural.

    Args:
        pipeline_annotations: Annotations for pipeline-generated items.
        authentic_annotations: Annotations for authentic MT items.

    Returns:
        NaturalnessComparison with statistics and p-values.
    """
    p_stats = _compute_group_stats(pipeline_annotations)
    a_stats = _compute_group_stats(authentic_annotations)

    p_values: dict = {}

    # 1. Errors per item (continuous) -- Mann-Whitney U
    p_values["errors_per_item"] = _mann_whitney_u(
        p_stats["errors_per_item"]["values"],
        a_stats["errors_per_item"]["values"],
    )

    # 2. Time per item (continuous) -- Mann-Whitney U
    p_values["time_per_item"] = _mann_whitney_u(
        p_stats["time_per_item"]["values"],
        a_stats["time_per_item"]["values"],
    )

    # 3. False positive rate (2x2 table: found_errors vs no_errors x pipeline vs authentic)
    # Build from the annotations directly
    p_found = sum(1 for a in pipeline_annotations if not a.no_errors_found)
    p_clean = len(pipeline_annotations) - p_found
    a_found = sum(1 for a in authentic_annotations if not a.no_errors_found)
    a_clean = len(authentic_annotations) - a_found

    if (p_found + p_clean) > 0 and (a_found + a_clean) > 0:
        p_values["error_detection_rate"] = _fisher_exact_2x2([
            [p_found, p_clean],
            [a_found, a_clean],
        ])
    else:
        p_values["error_detection_rate"] = {"note": "insufficient data"}

    # 4. Confidence distribution (categorical) -- chi-squared
    conf_levels = sorted(
        set(p_stats["confidence_dist"].keys()) | set(a_stats["confidence_dist"].keys())
    )
    if len(conf_levels) >= 2:
        row_pipeline = [p_stats["confidence_dist"].get(c, 0) for c in conf_levels]
        row_authentic = [a_stats["confidence_dist"].get(c, 0) for c in conf_levels]
        # Only run if we have enough data
        if sum(row_pipeline) > 0 and sum(row_authentic) > 0:
            p_values["confidence_dist"] = _chi2_contingency([row_pipeline, row_authentic])
            p_values["confidence_dist"]["categories"] = conf_levels
        else:
            p_values["confidence_dist"] = {"note": "insufficient data"}
    else:
        p_values["confidence_dist"] = {"note": "fewer than 2 confidence levels"}

    # 5. Category distribution -- chi-squared on error categories
    p_cats = Counter(
        (e.category if isinstance(e.category, str) else e.category.value)
        for a in pipeline_annotations
        for e in a.errors
    )
    a_cats = Counter(
        (e.category if isinstance(e.category, str) else e.category.value)
        for a in authentic_annotations
        for e in a.errors
    )
    all_cats = sorted(set(p_cats.keys()) | set(a_cats.keys()))
    if len(all_cats) >= 2:
        row_p = [p_cats.get(c, 0) for c in all_cats]
        row_a = [a_cats.get(c, 0) for c in all_cats]
        if sum(row_p) > 0 and sum(row_a) > 0:
            p_values["category_dist"] = _chi2_contingency([row_p, row_a])
            p_values["category_dist"]["categories"] = all_cats
        else:
            p_values["category_dist"] = {"note": "insufficient data"}
    else:
        p_values["category_dist"] = {"note": "fewer than 2 categories found"}

    # 6. Severity distribution -- chi-squared
    p_sevs = Counter(
        (e.severity if isinstance(e.severity, str) else e.severity.value)
        for a in pipeline_annotations
        for e in a.errors
    )
    a_sevs = Counter(
        (e.severity if isinstance(e.severity, str) else e.severity.value)
        for a in authentic_annotations
        for e in a.errors
    )
    all_sevs = sorted(set(p_sevs.keys()) | set(a_sevs.keys()))
    if len(all_sevs) >= 2:
        row_p = [p_sevs.get(s, 0) for s in all_sevs]
        row_a = [a_sevs.get(s, 0) for s in all_sevs]
        if sum(row_p) > 0 and sum(row_a) > 0:
            p_values["severity_dist"] = _chi2_contingency([row_p, row_a])
            p_values["severity_dist"]["categories"] = all_sevs
        else:
            p_values["severity_dist"] = {"note": "insufficient data"}
    else:
        p_values["severity_dist"] = {"note": "fewer than 2 severity levels found"}

    # Remove raw value lists from stats before returning (keep summary only)
    for key in ("errors_per_item", "time_per_item"):
        for group in (p_stats, a_stats):
            group[key].pop("values", None)

    result = NaturalnessComparison(
        pipeline_stats=p_stats,
        authentic_stats=a_stats,
        p_values=p_values,
    )

    # Log summary
    logger.info(
        "Naturalness comparison: pipeline=%d items, authentic=%d items",
        p_stats["n"], a_stats["n"],
    )
    for test_name, test_result in p_values.items():
        pv = test_result.get("p_value")
        if pv is not None:
            sig = "significant" if pv < 0.05 else "not significant"
            logger.info("  %s: p=%.4f (%s)", test_name, pv, sig)

    return result


def save_results(
    comparison: NaturalnessComparison,
    output_dir: Path | None = None,
) -> Path:
    """Save naturalness comparison results to JSON."""
    ensure_dirs()
    out = (output_dir or RESULTS_DIR / "track_c") / "naturalness_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(comparison)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Naturalness test results saved to %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Track C3: naturalness test")
    parser.add_argument(
        "--pipeline-annotations", type=Path, required=True,
        help="JSON file with ExpertAnnotation objects for pipeline items",
    )
    parser.add_argument(
        "--authentic-annotations", type=Path, required=True,
        help="JSON file with ExpertAnnotation objects for authentic items",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    # Load annotations
    p_raw = json.loads(args.pipeline_annotations.read_text(encoding="utf-8"))
    pipeline_annots = [ExpertAnnotation.model_validate(r) for r in p_raw]

    a_raw = json.loads(args.authentic_annotations.read_text(encoding="utf-8"))
    authentic_annots = [ExpertAnnotation.model_validate(r) for r in a_raw]

    comparison = compare_naturalness(pipeline_annots, authentic_annots)
    path = save_results(comparison, args.output_dir)
    print(f"Results saved to {path}")
    print(json.dumps(asdict(comparison), indent=2))
