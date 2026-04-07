"""§5.1 — Descriptive statistics by ToM level (Table 1)."""

from __future__ import annotations

import pandas as pd
import numpy as np

from .config import TOM_LABELS


def compute_descriptive_stats(tom_df: pd.DataFrame) -> dict:
    """Compute Table 1: descriptive statistics by ToM level.

    Returns dict with per-level stats and a summary DataFrame.
    """
    results = {"per_level": {}, "mapping_table": {}}

    for level in sorted(tom_df["tom_level"].unique()):
        subset = tom_df[tom_df["tom_level"] == level]
        label = TOM_LABELS.get(level, f"L{level}")

        det_rates = subset["detection_rate"]
        det_counts = subset["detection_count"]

        # Detection count distribution
        count_dist = det_counts.value_counts().to_dict()
        n = len(subset)

        stats = {
            "label": label,
            "n_errors": n,
            "mean_detection_rate": round(det_rates.mean(), 4),
            "sd_detection_rate": round(det_rates.std(), 4),
            "median_detection_rate": round(det_rates.median(), 4),
            "count_1_of_3": count_dist.get(1, 0),
            "count_2_of_3": count_dist.get(2, 0),
            "count_3_of_3": count_dist.get(3, 0),
            "pct_1_of_3": round(count_dist.get(1, 0) / n * 100, 1) if n else 0,
            "pct_2_of_3": round(count_dist.get(2, 0) / n * 100, 1) if n else 0,
            "pct_3_of_3": round(count_dist.get(3, 0) / n * 100, 1) if n else 0,
        }

        # Severity breakdown
        for sev in ["Major", "Minor", "Neutral"]:
            sev_subset = subset[subset["severity"] == sev]
            stats[f"n_{sev.lower()}"] = len(sev_subset)
            if len(sev_subset) > 0:
                stats[f"mean_det_{sev.lower()}"] = round(
                    sev_subset["detection_rate"].mean(), 4
                )
            else:
                stats[f"mean_det_{sev.lower()}"] = None

        results["per_level"][label] = stats

    # Category-level mapping table (Table 4)
    cat_stats = tom_df.groupby(["category", "tom_level"]).agg(
        n=("error_id", "count"),
        mean_det=("detection_rate", "mean"),
    ).reset_index()
    cat_stats["tom_label"] = cat_stats["tom_level"].map(TOM_LABELS)
    results["mapping_table"] = cat_stats.to_dict("records")

    return results


def print_table1(stats: dict) -> None:
    """Print Table 1 to console."""
    print("\n" + "=" * 80)
    print("TABLE 1: Descriptive Statistics by ToM Level")
    print("=" * 80)

    header = (
        f"{'Level':<6} {'N':>6} {'Mean Det':>9} {'SD':>7} {'Med':>7} "
        f"{'1/3':>6} {'2/3':>6} {'3/3':>6} "
        f"{'Major':>6} {'Minor':>6}"
    )
    print(header)
    print("-" * 80)

    for label in ["L0", "L1", "L2", "L3"]:
        s = stats["per_level"].get(label)
        if not s:
            continue
        print(
            f"{label:<6} {s['n_errors']:>6} {s['mean_detection_rate']:>9.4f} "
            f"{s['sd_detection_rate']:>7.4f} {s['median_detection_rate']:>7.4f} "
            f"{s['pct_1_of_3']:>5.1f}% {s['pct_2_of_3']:>5.1f}% {s['pct_3_of_3']:>5.1f}% "
            f"{s['n_major']:>6} {s['n_minor']:>6}"
        )
    print()
