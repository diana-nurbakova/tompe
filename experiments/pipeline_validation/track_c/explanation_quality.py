"""Track C v3: Explanation quality analysis -- expert ratings of generated explanations.

Analyses the expert annotator's ratings of Phase B generated explanations
across three dimensions (factual accuracy, pedagogical clarity, completeness),
broken down by aggregate, ToM level, and review time.

Pipeline-validation-spec-v3 §5.3.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tompe.schemas.expert_annotation import ExplanationRating

from experiments.pipeline_validation.config import (
    ANNOTATIONS_DIR,
    RESULTS_DIR,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExplanationQualityResults:
    """Aggregated explanation quality metrics."""

    n_ratings: int = 0

    # Aggregate rates (0.0 -- 1.0)
    accuracy_acceptable: float = 0.0   # % correct or partially_correct
    accuracy_highest: float = 0.0      # % correct only
    clarity_acceptable: float = 0.0    # % clear or somewhat_clear
    clarity_highest: float = 0.0       # % clear only
    completeness_acceptable: float = 0.0  # % thorough or adequate
    completeness_highest: float = 0.0     # % thorough only
    fully_satisfactory: float = 0.0    # % all three at highest level

    # By ToM level: tom_level -> {accuracy_acceptable, accuracy_highest, ...}
    by_tom: dict[str, dict[str, float]] = field(default_factory=dict)

    # Time analysis
    mean_review_time: float = 0.0
    median_review_time: float = 0.0
    std_review_time: float = 0.0
    time_by_tom: dict[str, float] = field(default_factory=dict)

    # Comments: list of dicts with item context
    comments: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))


def _pct(count: int, total: int) -> float:
    """Return percentage as a float in [0, 1], or 0.0 if total is 0."""
    return round(count / total, 4) if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Load ratings
# ---------------------------------------------------------------------------

def load_ratings(annotator_id: str = "annotator_1") -> list[dict]:
    """Load ExplanationRating JSON files from the annotations directory.

    Looks for files in:
        data/annotations/{annotator_id}/explanation_ratings/

    Each JSON file should contain either a single ExplanationRating object
    or a list of ExplanationRating objects.

    Returns:
        List of validated rating dicts (serialised from ExplanationRating).
    """
    ratings_dir = ANNOTATIONS_DIR / annotator_id / "explanation_ratings"
    logger.info("Loading explanation ratings from %s", ratings_dir)

    if not ratings_dir.exists():
        logger.warning("Ratings directory does not exist: %s", ratings_dir)
        return []

    all_ratings: list[dict] = []

    for path in sorted(ratings_dir.glob("*.json")):
        logger.debug("Reading %s", path.name)
        raw = json.loads(path.read_text(encoding="utf-8"))

        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            # Validate through Pydantic, then keep as dict for analysis
            rating = ExplanationRating.model_validate(item)
            all_ratings.append(rating.model_dump())

    logger.info("Loaded %d explanation ratings for annotator %s", len(all_ratings), annotator_id)
    return all_ratings


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _compute_dimension_rates(
    ratings: list[dict],
) -> dict[str, float]:
    """Compute aggregate rates for the three quality dimensions.

    Returns dict with keys: accuracy_acceptable, accuracy_highest,
    clarity_acceptable, clarity_highest, completeness_acceptable,
    completeness_highest, fully_satisfactory.
    """
    n = len(ratings)
    if n == 0:
        return {
            "accuracy_acceptable": 0.0,
            "accuracy_highest": 0.0,
            "clarity_acceptable": 0.0,
            "clarity_highest": 0.0,
            "completeness_acceptable": 0.0,
            "completeness_highest": 0.0,
            "fully_satisfactory": 0.0,
        }

    acc_acceptable = sum(
        1 for r in ratings if r["factual_accuracy"] in ("correct", "partially_correct")
    )
    acc_highest = sum(1 for r in ratings if r["factual_accuracy"] == "correct")

    clar_acceptable = sum(
        1 for r in ratings if r["pedagogical_clarity"] in ("clear", "somewhat_clear")
    )
    clar_highest = sum(1 for r in ratings if r["pedagogical_clarity"] == "clear")

    comp_acceptable = sum(
        1 for r in ratings if r["completeness"] in ("thorough", "adequate")
    )
    comp_highest = sum(1 for r in ratings if r["completeness"] == "thorough")

    fully_sat = sum(
        1
        for r in ratings
        if r["factual_accuracy"] == "correct"
        and r["pedagogical_clarity"] == "clear"
        and r["completeness"] == "thorough"
    )

    return {
        "accuracy_acceptable": _pct(acc_acceptable, n),
        "accuracy_highest": _pct(acc_highest, n),
        "clarity_acceptable": _pct(clar_acceptable, n),
        "clarity_highest": _pct(clar_highest, n),
        "completeness_acceptable": _pct(comp_acceptable, n),
        "completeness_highest": _pct(comp_highest, n),
        "fully_satisfactory": _pct(fully_sat, n),
    }


def _compute_by_tom(ratings: list[dict]) -> dict[str, dict[str, float]]:
    """Break down quality rates by ToM level.

    Returns:
        Dict mapping tom_level (str) to dimension rates.
    """
    by_level: dict[int | str, list[dict]] = {}
    for r in ratings:
        level = r.get("tom_level")
        if level is None:
            level = "unknown"
        by_level.setdefault(level, []).append(r)

    result: dict[str, dict[str, float]] = {}
    for level in sorted(by_level, key=lambda x: (isinstance(x, str), x)):
        level_ratings = by_level[level]
        rates = _compute_dimension_rates(level_ratings)
        rates["n"] = len(level_ratings)
        result[str(level)] = rates

    return result


def _compute_time_stats(ratings: list[dict]) -> dict[str, Any]:
    """Compute review time statistics overall and by ToM level."""
    times = [r["duration_seconds"] for r in ratings]

    # By ToM level
    by_level: dict[int | str, list[float]] = {}
    for r in ratings:
        level = r.get("tom_level")
        if level is None:
            level = "unknown"
        by_level.setdefault(level, []).append(r["duration_seconds"])

    time_by_tom = {
        str(k): round(_mean(v), 2)
        for k, v in sorted(by_level.items(), key=lambda x: (isinstance(x[0], str), x[0]))
    }

    return {
        "mean_review_time": round(_mean(times), 2),
        "median_review_time": round(_median(times), 2),
        "std_review_time": round(_std(times), 2),
        "time_by_tom": time_by_tom,
    }


def _extract_comments(ratings: list[dict]) -> list[dict[str, Any]]:
    """Extract all non-empty comments with context.

    Returns list sorted by rating pattern (low-rated items first) to
    facilitate qualitative review.
    """
    comments: list[dict[str, Any]] = []
    for r in ratings:
        comment = r.get("comment")
        if not comment or not comment.strip():
            continue
        comments.append({
            "item_id": r["item_id"],
            "error_index": r["error_index"],
            "tom_level": r.get("tom_level"),
            "factual_accuracy": r["factual_accuracy"],
            "pedagogical_clarity": r["pedagogical_clarity"],
            "completeness": r["completeness"],
            "comment": comment.strip(),
        })

    # Sort: items with lower ratings first (more interesting for review)
    level_order = {
        "incorrect": 0, "partially_correct": 1, "correct": 2,
        "unclear": 0, "somewhat_clear": 1, "clear": 2,
        "incomplete": 0, "adequate": 1, "thorough": 2,
    }

    def _sort_key(c: dict) -> tuple:
        return (
            level_order.get(c["factual_accuracy"], 9),
            level_order.get(c["pedagogical_clarity"], 9),
            level_order.get(c["completeness"], 9),
        )

    comments.sort(key=_sort_key)
    return comments


def analyze_explanation_quality(ratings: list[dict]) -> ExplanationQualityResults:
    """Run full explanation quality analysis on a set of ratings.

    Args:
        ratings: List of ExplanationRating dicts (e.g. from load_ratings).

    Returns:
        ExplanationQualityResults with all metrics.
    """
    if not ratings:
        logger.warning("No ratings to analyse")
        return ExplanationQualityResults()

    n = len(ratings)
    logger.info("Analysing %d explanation ratings", n)

    # Aggregate dimension rates
    agg = _compute_dimension_rates(ratings)

    # By ToM level
    by_tom = _compute_by_tom(ratings)

    # Time
    time_stats = _compute_time_stats(ratings)

    # Comments
    comments = _extract_comments(ratings)
    logger.info("Found %d non-empty comments", len(comments))

    results = ExplanationQualityResults(
        n_ratings=n,
        accuracy_acceptable=agg["accuracy_acceptable"],
        accuracy_highest=agg["accuracy_highest"],
        clarity_acceptable=agg["clarity_acceptable"],
        clarity_highest=agg["clarity_highest"],
        completeness_acceptable=agg["completeness_acceptable"],
        completeness_highest=agg["completeness_highest"],
        fully_satisfactory=agg["fully_satisfactory"],
        by_tom=by_tom,
        mean_review_time=time_stats["mean_review_time"],
        median_review_time=time_stats["median_review_time"],
        std_review_time=time_stats["std_review_time"],
        time_by_tom=time_stats["time_by_tom"],
        comments=comments,
    )

    # Log summary
    logger.info("=== Explanation Quality Summary (N=%d) ===", n)
    logger.info(
        "  Factual accuracy:     %.1f%% acceptable, %.1f%% highest",
        agg["accuracy_acceptable"] * 100, agg["accuracy_highest"] * 100,
    )
    logger.info(
        "  Pedagogical clarity:  %.1f%% acceptable, %.1f%% highest",
        agg["clarity_acceptable"] * 100, agg["clarity_highest"] * 100,
    )
    logger.info(
        "  Completeness:         %.1f%% acceptable, %.1f%% highest",
        agg["completeness_acceptable"] * 100, agg["completeness_highest"] * 100,
    )
    logger.info(
        "  Fully satisfactory:   %.1f%%",
        agg["fully_satisfactory"] * 100,
    )
    logger.info(
        "  Mean review time:     %.1fs (median %.1fs)",
        time_stats["mean_review_time"], time_stats["median_review_time"],
    )

    for level, rates in by_tom.items():
        logger.info(
            "  ToM %s (n=%d): acc=%.0f%% clar=%.0f%% comp=%.0f%%",
            level, rates["n"],
            rates["accuracy_acceptable"] * 100,
            rates["clarity_acceptable"] * 100,
            rates["completeness_acceptable"] * 100,
        )

    return results


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

def save_results(
    results: ExplanationQualityResults,
    output_dir: Path | None = None,
) -> Path:
    """Save explanation quality results as JSON.

    Writes to results/track_c/explanation_quality.json by default.
    """
    ensure_dirs()
    out = (output_dir or RESULTS_DIR / "track_c") / "explanation_quality.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(results)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Explanation quality results saved to %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Track C v3: explanation quality analysis (Phase B ratings)",
    )
    parser.add_argument(
        "--annotator-id",
        type=str,
        default="annotator_1",
        help="Annotator ID whose ratings to load (default: annotator_1)",
    )
    parser.add_argument(
        "--ratings-file",
        type=Path,
        default=None,
        help=(
            "Path to a JSON file with ExplanationRating objects. "
            "If not provided, ratings are loaded from "
            "data/annotations/{annotator_id}/explanation_ratings/"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: results/track_c/)",
    )
    args = parser.parse_args()

    # Load ratings
    if args.ratings_file is not None:
        logger.info("Loading ratings from file: %s", args.ratings_file)
        raw = json.loads(args.ratings_file.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        ratings = [ExplanationRating.model_validate(item).model_dump() for item in items]
    else:
        ratings = load_ratings(args.annotator_id)

    if not ratings:
        logger.error("No ratings found. Exiting.")
        raise SystemExit(1)

    # Analyse
    results = analyze_explanation_quality(ratings)

    # Save
    path = save_results(results, args.output_dir)
    print(f"Results saved to {path}")
    print(json.dumps(asdict(results), indent=2))
