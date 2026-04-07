"""§5.2–5.3 — Jonckheere-Terpstra trend test and Kruskal-Wallis with post-hoc.

V1: Tests monotonic decrease in detection rate across ToM levels.
V2: Non-parametric ANOVA with Dunn's pairwise comparisons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import TOM_LABELS


# ── V1: Jonckheere-Terpstra ─────────────────────────────────────────

def _jonckheere_terpstra(groups: list[np.ndarray]) -> tuple[float, float]:
    """Jonckheere-Terpstra test for ordered alternatives.

    Tests H0: all groups are from the same distribution
    vs H1: groups are ordered (decreasing in our case).

    Args:
        groups: List of arrays, one per ordered group.

    Returns:
        (J statistic, one-sided p-value for decreasing trend)
    """
    k = len(groups)
    J = 0.0

    # Count concordant pairs between all ordered group pairs
    for i in range(k):
        for j in range(i + 1, k):
            for xi in groups[i]:
                for xj in groups[j]:
                    if xi > xj:
                        J += 1
                    elif xi == xj:
                        J += 0.5

    # Expected value and variance under H0
    ns = [len(g) for g in groups]
    N = sum(ns)

    E_J = (N**2 - sum(n**2 for n in ns)) / 4

    # Variance (no ties correction for simplicity — detection rate has ties)
    # Use the full formula accounting for ties
    all_vals = np.concatenate(groups)
    _, tie_counts = np.unique(all_vals, return_counts=True)

    var_numer = (
        N * (N - 1) * (2 * N + 5)
        - sum(n * (n - 1) * (2 * n + 5) for n in ns)
        - sum(t * (t - 1) * (2 * t + 5) for t in tie_counts)
    )
    var_denom = 72

    # Additional tie correction terms
    term2_num = sum(n * (n - 1) * (n - 2) for n in ns) * sum(
        t * (t - 1) * (t - 2) for t in tie_counts
    )
    term2_den = 36 * N * (N - 1) * (N - 2) if N > 2 else 1

    term3_num = sum(n * (n - 1) for n in ns) * sum(t * (t - 1) for t in tie_counts)
    term3_den = 8 * N * (N - 1) if N > 1 else 1

    Var_J = var_numer / var_denom + term2_num / term2_den + term3_num / term3_den

    if Var_J <= 0:
        return J, 1.0

    Z = (J - E_J) / np.sqrt(Var_J)

    # One-sided p-value: we expect HIGHER J (more concordant pairs where
    # higher-level groups have LOWER detection → reversed)
    # Since we test for DECREASING trend, we want detection_rate in group i > group j
    # which means J should be high → one-sided p = P(Z > observed)
    p_value = 1 - stats.norm.cdf(Z)

    return float(J), float(p_value)


def run_v1(tom_df: pd.DataFrame) -> dict:
    """Experiment V1: Jonckheere-Terpstra monotonic trend test (§5.2).

    Tests whether detection rate decreases monotonically with ToM level.
    """
    # Build groups in ToM level order
    levels = sorted(tom_df["tom_level"].unique())
    groups = [tom_df[tom_df["tom_level"] == lv]["detection_rate"].values for lv in levels]

    J, p_value = _jonckheere_terpstra(groups)

    # Effect size: Kendall's tau-b between ToM level and detection rate
    tau_b, tau_p = stats.kendalltau(
        tom_df["tom_level"].values,
        tom_df["detection_rate"].values,
    )

    # Group means for reporting
    group_means = {
        TOM_LABELS[lv]: float(tom_df[tom_df["tom_level"] == lv]["detection_rate"].mean())
        for lv in levels
    }

    result = {
        "experiment": "V1_Jonckheere_Terpstra",
        "hypothesis": "H1: Detection rate decreases monotonically with ToM level",
        "J_statistic": round(J, 2),
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
        "kendall_tau_b": round(tau_b, 4),
        "kendall_p": round(tau_p, 6),
        "group_means": group_means,
        "group_sizes": {TOM_LABELS[lv]: len(g) for lv, g in zip(levels, groups)},
        "direction": "decreasing" if tau_b < 0 else "increasing" if tau_b > 0 else "none",
    }

    result["interpretation"] = _interpret_v1(result)
    return result


def _interpret_v1(result: dict) -> str:
    tau = result["kendall_tau_b"]
    p = result["p_value"]
    if result["significant"] and tau < 0:
        return (f"CONFIRMED: Significant monotonic decrease (J={result['J_statistic']}, "
                f"p={p:.4f}, tau_b={tau:.4f})")
    elif tau < 0:
        return (f"TREND: Decreasing but not significant (J={result['J_statistic']}, "
                f"p={p:.4f}, tau_b={tau:.4f})")
    else:
        return (f"DISCONFIRMED: No decreasing trend (tau_b={tau:.4f}, p={p:.4f})")


# ── V2: Kruskal-Wallis + Dunn's ─────────────────────────────────────

def run_v2(tom_df: pd.DataFrame) -> dict:
    """Experiment V2: Kruskal-Wallis with Dunn's post-hoc (§5.3)."""
    levels = sorted(tom_df["tom_level"].unique())
    groups = [tom_df[tom_df["tom_level"] == lv]["detection_rate"].values for lv in levels]

    # Kruskal-Wallis
    H, kw_p = stats.kruskal(*groups)

    # Dunn's post-hoc with Holm-Bonferroni correction
    posthoc = _dunns_test(tom_df, levels)

    result = {
        "experiment": "V2_Kruskal_Wallis",
        "H_statistic": round(float(H), 4),
        "p_value": round(float(kw_p), 6),
        "significant": float(kw_p) < 0.05,
        "df": len(levels) - 1,
        "posthoc_dunn": posthoc,
    }

    result["interpretation"] = _interpret_v2(result, levels)
    return result


def _dunns_test(tom_df: pd.DataFrame, levels: list[int]) -> list[dict]:
    """Dunn's test with Holm-Bonferroni correction for pairwise comparisons."""
    from itertools import combinations

    N = len(tom_df)
    # Assign ranks
    ranked = tom_df["detection_rate"].rank()

    pairs = list(combinations(levels, 2))
    raw_results = []

    for li, lj in pairs:
        ni = (tom_df["tom_level"] == li).sum()
        nj = (tom_df["tom_level"] == lj).sum()

        mean_rank_i = ranked[tom_df["tom_level"] == li].mean()
        mean_rank_j = ranked[tom_df["tom_level"] == lj].mean()

        # Z statistic
        se = np.sqrt((N * (N + 1) / 12) * (1 / ni + 1 / nj))
        z = (mean_rank_i - mean_rank_j) / se if se > 0 else 0
        p = 2 * (1 - stats.norm.cdf(abs(z)))

        raw_results.append({
            "comparison": f"{TOM_LABELS[li]} vs {TOM_LABELS[lj]}",
            "z": round(float(z), 4),
            "p_raw": round(float(p), 6),
            "mean_rank_diff": round(float(mean_rank_i - mean_rank_j), 2),
        })

    # Holm-Bonferroni correction
    raw_results.sort(key=lambda x: x["p_raw"])
    m = len(raw_results)
    for i, r in enumerate(raw_results):
        r["p_adjusted"] = round(min(r["p_raw"] * (m - i), 1.0), 6)
        r["significant"] = r["p_adjusted"] < 0.05

    return raw_results


def _interpret_v2(result: dict, levels: list[int]) -> str:
    if result["significant"]:
        sig_pairs = [p["comparison"] for p in result["posthoc_dunn"] if p["significant"]]
        return (f"SIGNIFICANT: H={result['H_statistic']}, p={result['p_value']:.4f}. "
                f"Significant pairwise differences: {', '.join(sig_pairs) or 'none after correction'}")
    else:
        return f"NOT SIGNIFICANT: H={result['H_statistic']}, p={result['p_value']:.4f}"


def print_results(v1: dict, v2: dict) -> None:
    """Print V1 and V2 results to console."""
    print("\n" + "=" * 80)
    print("V1: JONCKHEERE-TERPSTRA TREND TEST")
    print("=" * 80)
    print(f"  J = {v1['J_statistic']}, p = {v1['p_value']:.6f}")
    print(f"  Kendall tau_b = {v1['kendall_tau_b']:.4f} (p = {v1['kendall_p']:.6f})")
    print(f"  Direction: {v1['direction']}")
    print(f"  Group means: {v1['group_means']}")
    print(f"  >> {v1['interpretation']}")

    print("\n" + "=" * 80)
    print("V2: KRUSKAL-WALLIS + DUNN'S POST-HOC")
    print("=" * 80)
    print(f"  H({v2['df']}) = {v2['H_statistic']}, p = {v2['p_value']:.6f}")
    print("\n  Pairwise comparisons (Holm-Bonferroni corrected):")
    for p in v2["posthoc_dunn"]:
        sig = "*" if p["significant"] else ""
        print(f"    {p['comparison']:<12}  z={p['z']:>7.4f}  "
              f"p_adj={p['p_adjusted']:.6f} {sig}")
    print(f"\n  >> {v2['interpretation']}")
