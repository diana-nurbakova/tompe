"""ToM Hierarchy Validation — Full Pipeline Orchestrator.

Runs the complete experiment pipeline:
  1. Parse MQM TSV and extract error spans
  2. Align errors across raters (IoU-based)
  3. Assign ToM levels
  4. Descriptive statistics (Table 1)
  5. V1: Jonckheere-Terpstra trend test
  6. V2: Kruskal-Wallis + Dunn's post-hoc
  7. V3: Ordinal regression
  8. V4: Rater-level logistic regression
  9. Sensitivity analyses (S1–S8)
  10. Generate figures

Usage:
    python -m experiments.tom_validation.run_all
    python -m experiments.tom_validation.run_all --skip-iou-variants  # faster
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows so unicode chars (β, χ², τ, etc.) work
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.tom_validation.config import (
    MQM_TSV, OUTPUT_DIR, IOU_THRESHOLD, IOU_THRESHOLD_LENIENT, IOU_THRESHOLD_STRICT,
)
from experiments.tom_validation import parse_mqm
from experiments.tom_validation import align_errors
from experiments.tom_validation import assign_tom
from experiments.tom_validation import descriptive
from experiments.tom_validation import test_trend
from experiments.tom_validation import mixed_models
from experiments.tom_validation import sensitivity
from experiments.tom_validation import figures


def run(skip_iou_variants: bool = False, output_dir: Path | None = None) -> dict:
    """Run the full validation pipeline.

    Args:
        skip_iou_variants: Skip S5/S6 (lenient/strict IoU) for faster runs.
        output_dir: Override output directory.

    Returns:
        Dict with all results.
    """
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    sep = "=" * 70
    print(f"\n{sep}")
    print("ToM HIERARCHY VALIDATION -- WMT 2020 MQM EN->DE")
    print(sep)

    # ── Step 1: Parse ────────────────────────────────────────────────
    print("\n[1/10] Parsing MQM TSV...")
    errors = parse_mqm.parse_all()
    error_df = parse_mqm.errors_to_dataframe(errors)
    print(f"  Parsed {len(error_df)} error spans from {MQM_TSV.name}")
    print(f"  Categories: {error_df['category'].nunique()}")
    print(f"  Systems: {error_df['system'].nunique()}")

    # ── Step 2: Align (primary IoU) ──────────────────────────────────
    print("\n[2/10] Aligning errors across raters (IoU={:.1f})...".format(IOU_THRESHOLD))
    aligned_df = align_errors.align_all(error_df, iou_threshold=IOU_THRESHOLD)

    # IoU variants for sensitivity S5/S6
    aligned_by_iou = {}
    if not skip_iou_variants:
        print("\n  Aligning with lenient IoU ({:.1f})...".format(IOU_THRESHOLD_LENIENT))
        aligned_lenient = align_errors.align_all(error_df, iou_threshold=IOU_THRESHOLD_LENIENT)
        print("  Aligning with strict IoU ({:.1f})...".format(IOU_THRESHOLD_STRICT))
        aligned_strict = align_errors.align_all(error_df, iou_threshold=IOU_THRESHOLD_STRICT)

    # ── Step 3: Assign ToM levels ────────────────────────────────────
    print("\n[3/10] Assigning ToM levels...")
    tom_df = assign_tom.assign_tom_levels(aligned_df)
    tom_df = assign_tom.compute_covariates(tom_df)

    # Save intermediate data
    tom_df.to_csv(output_dir / "tom_errors.csv", index=False)
    print(f"  Saved: {output_dir / 'tom_errors.csv'}")

    # IoU variants: assign ToM levels
    if not skip_iou_variants:
        tom_lenient = assign_tom.assign_tom_levels(aligned_lenient)
        tom_lenient = assign_tom.compute_covariates(tom_lenient)
        tom_strict = assign_tom.assign_tom_levels(aligned_strict)
        tom_strict = assign_tom.compute_covariates(tom_strict)
        aligned_by_iou = {"lenient": tom_lenient, "strict": tom_strict}

    # ── Step 4: Descriptive statistics ───────────────────────────────
    print("\n[4/10] Computing descriptive statistics...")
    desc_stats = descriptive.compute_descriptive_stats(tom_df)
    descriptive.print_table1(desc_stats)

    # ── Step 5: V1 — Jonckheere-Terpstra ─────────────────────────────
    print("\n[5/10] Running V1: Jonckheere-Terpstra trend test...")
    v1_results = test_trend.run_v1(tom_df)

    # ── Step 6: V2 — Kruskal-Wallis ──────────────────────────────────
    print("\n[6/10] Running V2: Kruskal-Wallis + Dunn's post-hoc...")
    v2_results = test_trend.run_v2(tom_df)

    test_trend.print_results(v1_results, v2_results)

    # ── Step 7: V3 — Ordinal regression ──────────────────────────────
    print("\n[7/10] Running V3: Ordinal regression...")
    v3_results = mixed_models.run_v3(tom_df)
    mixed_models.print_v3(v3_results)

    # ── Step 8: V4 — Rater-level logistic ────────────────────────────
    print("\n[8/10] Running V4: Rater-level logistic regression...")
    rater_df = assign_tom.build_rater_level_data(tom_df)
    rater_df.to_csv(output_dir / "rater_level_data.csv", index=False)
    v4_results = mixed_models.run_v4(rater_df)
    mixed_models.print_v4(v4_results)

    # ── Step 9: Sensitivity analyses ─────────────────────────────────
    print("\n[9/10] Running sensitivity analyses...")
    sens_results = sensitivity.run_all_sensitivity(
        tom_df,
        aligned_dfs_by_iou=aligned_by_iou if not skip_iou_variants else None,
    )
    sensitivity.print_sensitivity_summary(sens_results)

    # ── Step 10: Figures ─────────────────────────────────────────────
    print("\n[10/10] Generating figures...")
    fig_paths = {}

    f1 = figures.figure_v1_detection_boxplot(tom_df, output_dir)
    fig_paths["V1_boxplot"] = str(f1)
    print(f"  {f1}")

    f2 = figures.figure_v2_category_heatmap(tom_df, output_dir)
    fig_paths["V2_heatmap"] = str(f2)
    print(f"  {f2}")

    f3 = figures.figure_v3_rater_slopes(v4_results, output_dir)
    if f3:
        fig_paths["V3_rater_slopes"] = str(f3)
        print(f"  {f3}")

    f_sens = figures.figure_sensitivity_summary(sens_results, output_dir)
    if f_sens:
        fig_paths["sensitivity"] = str(f_sens)
        print(f"  {f_sens}")

    # ── Assemble results ─────────────────────────────────────────────
    all_results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "spec_version": "tom_validation_v1",
            "dataset": "WMT 2020 MQM EN->DE",
            "iou_threshold": IOU_THRESHOLD,
            "n_raw_errors": len(error_df),
            "n_aligned_errors": len(aligned_df),
            "n_tom_errors": len(tom_df),
            "skip_iou_variants": skip_iou_variants,
        },
        "descriptive": desc_stats,
        "v1_jonckheere_terpstra": v1_results,
        "v2_kruskal_wallis": v2_results,
        "v3_ordinal_regression": v3_results,
        "v4_rater_logistic": v4_results,
        "sensitivity": sens_results,
        "figures": fig_paths,
    }

    # Save JSON
    results_path = output_dir / "all_results.json"
    results_path.write_text(
        json.dumps(all_results, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nResults saved to {results_path}")

    # ── Final summary ────────────────────────────────────────────────
    _print_summary(all_results)

    return all_results


def _print_summary(results: dict) -> None:
    """Print concise final summary."""
    sep = "=" * 70
    print(f"\n{sep}")
    print("SUMMARY")
    print(sep)

    v1 = results["v1_jonckheere_terpstra"]
    v2 = results["v2_kruskal_wallis"]
    v3 = results["v3_ordinal_regression"]
    v4 = results["v4_rater_logistic"]
    sens = results["sensitivity"]

    print(f"\n  H1 (monotonic decrease): {v1['interpretation']}")
    print(f"  H2 (controlling covariates): {v3.get('interpretation', 'SKIPPED')}")
    print(f"  H3 (rater variation): {v4.get('interpretation', 'SKIPPED')}")

    summary = sens.get("_summary", {})
    print(f"\n  Sensitivity convergence: {summary.get('n_significant', '?')}/"
          f"{summary.get('n_testable', '?')} -> "
          f"{'MET' if summary.get('convergence_met') else 'NOT MET'}")

    # Key statistics for paper
    print(f"\n  Key statistics for paper:")
    print(f"    Jonckheere-Terpstra J = {v1['J_statistic']}, p = {v1['p_value']}")
    print(f"    Kendall tau_b = {v1['kendall_tau_b']}")
    if not v3.get("skipped"):
        tom_coef = v3["coefficients"].get("tom_linear", {})
        print(f"    Ordinal regression β(ToM) = {tom_coef.get('coef', 'N/A')}, "
              f"p = {tom_coef.get('p', 'N/A')}")
        lr = v3["lr_test"]
        print(f"    LR test: χ² = {lr['chi2']}, p = {lr['p_value']}")

    print(f"\n{sep}\n")


def main():
    parser = argparse.ArgumentParser(
        description="ToM hierarchy validation using WMT 2020 MQM data"
    )
    parser.add_argument(
        "--skip-iou-variants", action="store_true",
        help="Skip lenient/strict IoU alignment (faster run)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Override output directory",
    )
    args = parser.parse_args()
    run(skip_iou_variants=args.skip_iou_variants, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
