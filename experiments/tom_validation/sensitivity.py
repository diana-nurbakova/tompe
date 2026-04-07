"""§6 — Sensitivity analyses.

Runs V1 (Jonckheere-Terpstra) under 8 different data configurations.
"""

from __future__ import annotations

import pandas as pd

from .config import IOU_THRESHOLD_LENIENT, IOU_THRESHOLD_STRICT
from .test_trend import run_v1


def _filter_s1(df: pd.DataFrame) -> pd.DataFrame:
    """S1: Exclude Accuracy/Mistranslation."""
    return df[df["category"] != "Accuracy/Mistranslation"].copy()


def _filter_s2(df: pd.DataFrame) -> pd.DataFrame:
    """S2: Binary ToM (L0–L1 vs L2–L3)."""
    df = df.copy()
    df["tom_level"] = df["tom_level"].apply(lambda x: 0 if x <= 1 else 1)
    return df


def _filter_s3(df: pd.DataFrame) -> pd.DataFrame:
    """S3: Exclude Neutral severity."""
    return df[df["severity"] != "Neutral"].copy()


def _filter_s4(df: pd.DataFrame) -> pd.DataFrame:
    """S4: Restrict to Major errors only."""
    return df[df["severity"] == "Major"].copy()


def _filter_s7(df: pd.DataFrame) -> pd.DataFrame:
    """S7: Exclude human references."""
    return df[~df["system"].str.startswith("Human")].copy()


SENSITIVITY_FILTERS = {
    "S1_no_mistranslation": _filter_s1,
    "S2_binary_tom": _filter_s2,
    "S3_no_neutral": _filter_s3,
    "S4_major_only": _filter_s4,
    "S7_no_human_ref": _filter_s7,
}


def run_all_sensitivity(
    tom_df: pd.DataFrame,
    aligned_dfs_by_iou: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """Run all 8 sensitivity analyses.

    Args:
        tom_df: Primary analysis DataFrame (IoU=0.5).
        aligned_dfs_by_iou: Optional dict with keys 'lenient' and 'strict'
            containing DataFrames aligned with different IoU thresholds.
            If None, S5/S6 are skipped.

    Returns:
        Dict mapping sensitivity ID to V1 result + metadata.
    """
    results = {}

    # S1–S4, S7: filter-based
    for sid, filter_fn in SENSITIVITY_FILTERS.items():
        filtered = filter_fn(tom_df)
        if len(filtered) < 10:
            results[sid] = {
                "skipped": True,
                "reason": f"Too few errors after filtering ({len(filtered)})",
            }
            continue

        v1 = run_v1(filtered)
        results[sid] = {
            "v1": v1,
            "n_errors": len(filtered),
            "significant": v1["significant"],
            "tau_b": v1["kendall_tau_b"],
        }

    # S5: Lenient IoU (0.3)
    if aligned_dfs_by_iou and "lenient" in aligned_dfs_by_iou:
        df_lenient = aligned_dfs_by_iou["lenient"]
        v1 = run_v1(df_lenient)
        results["S5_iou_lenient"] = {
            "v1": v1,
            "n_errors": len(df_lenient),
            "significant": v1["significant"],
            "tau_b": v1["kendall_tau_b"],
            "iou_threshold": IOU_THRESHOLD_LENIENT,
        }
    else:
        results["S5_iou_lenient"] = {"skipped": True, "reason": "No lenient IoU data"}

    # S6: Strict IoU (0.7)
    if aligned_dfs_by_iou and "strict" in aligned_dfs_by_iou:
        df_strict = aligned_dfs_by_iou["strict"]
        v1 = run_v1(df_strict)
        results["S6_iou_strict"] = {
            "v1": v1,
            "n_errors": len(df_strict),
            "significant": v1["significant"],
            "tau_b": v1["kendall_tau_b"],
            "iou_threshold": IOU_THRESHOLD_STRICT,
        }
    else:
        results["S6_iou_strict"] = {"skipped": True, "reason": "No strict IoU data"}

    # S8: Per-system analysis
    systems = tom_df["system"].unique()
    s8_results = {}
    for sys_name in systems:
        sys_df = tom_df[tom_df["system"] == sys_name]
        if len(sys_df) < 10:
            continue
        v1 = run_v1(sys_df)
        s8_results[sys_name] = {
            "significant": v1["significant"],
            "tau_b": v1["kendall_tau_b"],
            "p_value": v1["p_value"],
            "n_errors": len(sys_df),
        }

    n_sig_systems = sum(1 for r in s8_results.values() if r["significant"])
    results["S8_per_system"] = {
        "per_system": s8_results,
        "n_systems": len(s8_results),
        "n_significant": n_sig_systems,
        "significant": n_sig_systems > len(s8_results) / 2,
    }

    # Summary
    n_testable = sum(1 for r in results.values() if not r.get("skipped", False))
    n_significant = sum(
        1 for r in results.values()
        if not r.get("skipped", False) and r.get("significant", False)
    )
    results["_summary"] = {
        "n_testable": n_testable,
        "n_significant": n_significant,
        "convergence_met": n_significant >= 5,
        "criterion": "V1 significant in primary + at least 5 of 8 sensitivity analyses",
    }

    return results


def print_sensitivity_summary(results: dict) -> None:
    """Print sensitivity analysis summary."""
    print("\n" + "=" * 80)
    print("SENSITIVITY ANALYSES (§6)")
    print("=" * 80)

    for sid in ["S1_no_mistranslation", "S2_binary_tom", "S3_no_neutral",
                "S4_major_only", "S5_iou_lenient", "S6_iou_strict",
                "S7_no_human_ref", "S8_per_system"]:
        r = results.get(sid, {})
        if r.get("skipped"):
            print(f"  {sid}: SKIPPED ({r['reason']})")
        elif sid == "S8_per_system":
            print(f"  {sid}: {r['n_significant']}/{r['n_systems']} systems significant")
        else:
            sig = "SIG" if r.get("significant") else "n.s."
            print(f"  {sid}: tau_b={r['tau_b']:.4f}, [{sig}], N={r['n_errors']}")

    summary = results.get("_summary", {})
    print(f"\n  Convergence: {summary.get('n_significant', 0)}/{summary.get('n_testable', 0)} "
          f"significant -> {'MET' if summary.get('convergence_met') else 'NOT MET'}")
