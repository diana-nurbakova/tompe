"""Track B statistical analyses B1–B7 with ground metric sweep.

Implements all analyses from spec §5.1–5.7.
"""

from __future__ import annotations

import logging
from itertools import combinations

import numpy as np
from scipy import stats

from .config import ARCHETYPES, N_SKILLS, REG_M_VALUES, SKILL_LABELS, TARGET_PROFILE
from .ground_metrics import build_all_metrics
from .metrics import (
    cosine_distance,
    euclidean_distance,
    mastery_gap,
    pairwise_distances,
    profile_to_array,
    trajectory_efficiency,
    w1_balanced,
    w1_unbalanced,
    wasserstein_barycenter,
)
from .synthetic_trajectories import StudentTrajectory, generate_all_students

logger = logging.getLogger(__name__)


# =============================================================================
# B1: Archetype Discrimination — spec §5.1
# =============================================================================

def analysis_b1_archetype_discrimination(
    students: list[StudentTrajectory],
    ground_metrics: dict[str, np.ndarray],
    session_idx: int = 9,
) -> dict[str, dict]:
    """Fisher discriminant ratio for W₁ (all metrics) vs Euclidean vs cosine.

    Compares between-archetype vs within-archetype variance at a given session.
    """
    # Group students by archetype
    archetype_groups: dict[str, list[dict[str, float]]] = {}
    for student in students:
        profiles = archetype_groups.setdefault(student.archetype, [])
        profiles.append(student.profiles[session_idx])

    archetype_keys = sorted(archetype_groups.keys())
    results = {}

    # Compute Fisher ratio for each distance function
    def fisher_ratio(dist_fn_name: str, dist_fn) -> dict:
        between_dists = []
        within_dists = []

        for ai, aj in combinations(archetype_keys, 2):
            for pi in archetype_groups[ai]:
                for pj in archetype_groups[aj]:
                    between_dists.append(dist_fn(pi, pj))

        for ak in archetype_keys:
            group = archetype_groups[ak]
            for pi, pj in combinations(group, 2):
                within_dists.append(dist_fn(pi, pj))

        between_var = np.var(between_dists) if between_dists else 0.0
        within_var = np.var(within_dists) if within_dists else 1e-10
        return {
            "fisher_ratio": float(between_var / max(within_var, 1e-10)),
            "between_mean": float(np.mean(between_dists)) if between_dists else 0.0,
            "within_mean": float(np.mean(within_dists)) if within_dists else 0.0,
            "between_std": float(np.std(between_dists)) if between_dists else 0.0,
            "within_std": float(np.std(within_dists)) if within_dists else 0.0,
        }

    # W₁ with each ground metric
    for metric_name, cost_matrix in ground_metrics.items():
        results[metric_name] = fisher_ratio(
            metric_name,
            lambda a, b, cm=cost_matrix: w1_balanced(a, b, cm),
        )

    # Baselines
    results["euclidean"] = fisher_ratio("euclidean", euclidean_distance)
    results["cosine"] = fisher_ratio("cosine", cosine_distance)

    return results


# =============================================================================
# B2: MasteryGap Trajectory Comparison — spec §5.2
# =============================================================================

def analysis_b2_mastery_gap_trajectories(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
    balanced: bool = True,
) -> dict[str, dict]:
    """Compute MasteryGap trajectories and AUC-MG for each student.

    Returns per-student trajectories + Kruskal-Wallis test across archetypes.
    """
    target = profile_to_array(TARGET_PROFILE)
    student_results = {}

    for student in students:
        gaps = []
        for profile in student.profiles:
            gap = mastery_gap(profile, cost_matrix, target, balanced=balanced)
            gaps.append(gap)
        auc_mg = float(np.trapz(gaps))
        student_results[student.student_id] = {
            "archetype": student.archetype,
            "mastery_gaps": gaps,
            "auc_mg": auc_mg,
        }

    # Kruskal-Wallis test: AUC-MG differs across archetypes?
    archetype_aucs: dict[str, list[float]] = {}
    for sid, res in student_results.items():
        archetype_aucs.setdefault(res["archetype"], []).append(res["auc_mg"])

    groups = [aucs for aucs in archetype_aucs.values() if len(aucs) >= 2]
    if len(groups) >= 2:
        h_stat, p_val = stats.kruskal(*groups)
    else:
        h_stat, p_val = 0.0, 1.0

    return {
        "students": student_results,
        "kruskal_wallis": {"H": float(h_stat), "p_value": float(p_val)},
        "archetype_auc_means": {
            k: float(np.mean(v)) for k, v in archetype_aucs.items()
        },
    }


# =============================================================================
# B3: Trajectory Efficiency — spec §5.3
# =============================================================================

def analysis_b3_trajectory_efficiency(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
) -> dict[str, dict]:
    """Compute trajectory efficiency for each student."""
    student_results = {}
    archetype_effs: dict[str, list[float]] = {}

    for student in students:
        eff = trajectory_efficiency(student.profiles, cost_matrix)
        student_results[student.student_id] = {
            "archetype": student.archetype,
            "efficiency": eff,
        }
        archetype_effs.setdefault(student.archetype, []).append(eff)

    # One-way ANOVA across archetypes
    groups = [effs for effs in archetype_effs.values() if len(effs) >= 2]
    if len(groups) >= 2:
        f_stat, p_val = stats.f_oneway(*groups)
    else:
        f_stat, p_val = 0.0, 1.0

    return {
        "students": student_results,
        "anova": {"F": float(f_stat), "p_value": float(p_val)},
        "archetype_means": {
            k: float(np.mean(v)) for k, v in archetype_effs.items()
        },
        "archetype_stds": {
            k: float(np.std(v)) for k, v in archetype_effs.items()
        },
    }


# =============================================================================
# B4: Peer Comparison (Class Barycenter) — spec §5.4
# =============================================================================

def analysis_b4_barycenter(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
    session_idx: int = 9,
) -> dict:
    """Compare Wasserstein barycenter vs arithmetic mean as class average."""
    profiles = [s.profiles[session_idx] for s in students]
    target = profile_to_array(TARGET_PROFILE)

    # Arithmetic mean
    arrays = np.array([profile_to_array(p) for p in profiles])
    arith_mean = arrays.mean(axis=0)

    # Wasserstein barycenter
    bary = wasserstein_barycenter(profiles, cost_matrix)

    # Distance from each student to both averages
    w1_to_bary = []
    w1_to_mean = []
    euc_to_bary = []
    euc_to_mean = []

    for p in profiles:
        arr = profile_to_array(p)
        w1_to_bary.append(w1_balanced(arr, bary, cost_matrix))
        w1_to_mean.append(w1_balanced(arr, arith_mean, cost_matrix))
        euc_to_bary.append(euclidean_distance(arr, bary))
        euc_to_mean.append(euclidean_distance(arr, arith_mean))

    # Readiness: student is "ready" if MasteryGap < median
    gaps = [mastery_gap(p, cost_matrix, target) for p in profiles]
    median_gap = float(np.median(gaps))
    readiness = [1 if g < median_gap else 0 for g in gaps]

    # Correlate distance-to-average with readiness
    if sum(readiness) > 0 and sum(readiness) < len(readiness):
        r_bary, p_bary = stats.pointbiserialr(readiness, w1_to_bary)
        r_mean, p_mean = stats.pointbiserialr(readiness, w1_to_mean)
    else:
        r_bary, p_bary, r_mean, p_mean = 0.0, 1.0, 0.0, 1.0

    return {
        "arithmetic_mean": arith_mean.tolist(),
        "wasserstein_barycenter": bary.tolist(),
        "w1_to_bary_mean": float(np.mean(w1_to_bary)),
        "w1_to_mean_mean": float(np.mean(w1_to_mean)),
        "readiness_corr_bary": {"r": float(r_bary), "p": float(p_bary)},
        "readiness_corr_mean": {"r": float(r_mean), "p": float(p_mean)},
    }


# =============================================================================
# B5: Ground Metric Sensitivity — spec §5.5
# =============================================================================

def analysis_b5_ground_metric_sensitivity(
    students: list[StudentTrajectory],
    ground_metrics: dict[str, np.ndarray],
) -> dict[str, dict]:
    """Run B1–B3 with all ground metrics, compile effect sizes.

    6 planned comparisons tested via paired Wilcoxon.
    """
    # Run B1 (Fisher ratios) — already returns per-metric results
    b1_results = analysis_b1_archetype_discrimination(students, ground_metrics)

    # Run B2 (MasteryGap AUC) for each metric
    b2_by_metric = {}
    for metric_name, cost_matrix in ground_metrics.items():
        b2 = analysis_b2_mastery_gap_trajectories(students, cost_matrix)
        b2_by_metric[metric_name] = b2["kruskal_wallis"]["H"]

    # Run B3 (Efficiency) for each metric
    b3_by_metric = {}
    for metric_name, cost_matrix in ground_metrics.items():
        b3 = analysis_b3_trajectory_efficiency(students, cost_matrix)
        b3_by_metric[metric_name] = b3["anova"]["F"]

    # Compile effect size matrix: metrics × analyses
    metric_names = sorted(ground_metrics.keys())
    effect_matrix = {}
    for mn in metric_names:
        effect_matrix[mn] = {
            "B1_fisher": b1_results.get(mn, {}).get("fisher_ratio", 0.0),
            "B2_kruskal_H": b2_by_metric.get(mn, 0.0),
            "B3_anova_F": b3_by_metric.get(mn, 0.0),
        }

    # 6 planned comparisons (spec §5.5)
    planned_comparisons = _run_planned_comparisons(effect_matrix)

    return {
        "effect_matrix": effect_matrix,
        "planned_comparisons": planned_comparisons,
    }


def _run_planned_comparisons(
    effect_matrix: dict[str, dict[str, float]],
) -> dict[str, dict]:
    """Execute the 6 planned metric comparisons via Wilcoxon."""
    analyses = ["B1_fisher", "B2_kruskal_H", "B3_anova_F"]

    def _get_effects(prefix: str) -> list[float]:
        """Collect effect sizes for metrics matching prefix."""
        return [
            np.mean([effect_matrix[mn][a] for a in analyses])
            for mn in effect_matrix
            if mn.startswith(prefix)
        ]

    def _compare(name: str, group_a_prefix: str, group_b_prefix: str) -> dict:
        """Wilcoxon signed-rank or Mann-Whitney comparison."""
        a_vals = _get_effects(group_a_prefix)
        b_vals = _get_effects(group_b_prefix)

        if not a_vals or not b_vals:
            return {"test": name, "error": "insufficient data"}

        # Use Mann-Whitney U for unpaired groups
        if len(a_vals) >= 2 and len(b_vals) >= 2:
            u_stat, p_val = stats.mannwhitneyu(
                a_vals, b_vals, alternative="greater"
            )
            return {
                "test": name,
                "a_mean": float(np.mean(a_vals)),
                "b_mean": float(np.mean(b_vals)),
                "U": float(u_stat),
                "p_value": float(p_val),
            }
        return {
            "test": name,
            "a_mean": float(np.mean(a_vals)),
            "b_mean": float(np.mean(b_vals)),
        }

    comparisons = {}

    # 1. Structure vs. none: M2 vs M1
    m2_effects = [effect_matrix.get("M2_graph", {}).get(a, 0) for a in analyses]
    m1_effects = [effect_matrix.get("M1_trivial", {}).get(a, 0) for a in analyses]
    comparisons["structure_vs_none"] = {
        "M2_mean": float(np.mean(m2_effects)),
        "M1_mean": float(np.mean(m1_effects)),
        "M2_wins": sum(1 for a, b in zip(m2_effects, m1_effects) if a > b),
    }

    # 2. Specific vs random: M2 vs M_rand
    comparisons["specific_vs_random"] = _compare(
        "M2 vs M_rand", "M2_", "M_rand_"
    )

    # 3. Calibrated vs uniform: M3 vs M2
    m3_effects = [effect_matrix.get("M3_weighted", {}).get(a, 0) for a in analyses]
    comparisons["calibrated_vs_uniform"] = {
        "M3_mean": float(np.mean(m3_effects)),
        "M2_mean": float(np.mean(m2_effects)),
        "M3_wins": sum(1 for a, b in zip(m3_effects, m2_effects) if a > b),
    }

    # 4. 2D vs 1D: M4 vs M2
    m4_effects = [effect_matrix.get("M4_2d", {}).get(a, 0) for a in analyses]
    comparisons["2d_vs_1d"] = {
        "M4_mean": float(np.mean(m4_effects)),
        "M2_mean": float(np.mean(m2_effects)),
        "M4_wins": sum(1 for a, b in zip(m4_effects, m2_effects) if a > b),
    }

    # 5. Structure vs ordering: M2 vs M5
    m5_effects = [effect_matrix.get("M5_linear", {}).get(a, 0) for a in analyses]
    comparisons["structure_vs_ordering"] = {
        "M2_mean": float(np.mean(m2_effects)),
        "M5_mean": float(np.mean(m5_effects)),
        "M2_wins": sum(1 for a, b in zip(m2_effects, m5_effects) if a > b),
    }

    # 6. Best ToM vs best baseline
    tom_best = max(np.mean(m2_effects), np.mean(m3_effects), np.mean(m4_effects))
    baseline_best = max(np.mean(m1_effects), np.mean(m5_effects))
    comparisons["best_tom_vs_best_baseline"] = {
        "tom_best": float(tom_best),
        "baseline_best": float(baseline_best),
        "tom_advantage": float(tom_best - baseline_best),
    }

    return comparisons


# =============================================================================
# B6: Robustness to BKT Smoothing — spec §5.6
# =============================================================================

def analysis_b6_bkt_robustness(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
) -> dict:
    """Compare W₁ results on raw vs BKT-smoothed profiles."""
    # B1 with raw profiles
    raw_b1 = analysis_b1_archetype_discrimination(
        students, {"M2_graph": cost_matrix}
    )
    raw_fisher = raw_b1.get("M2_graph", {}).get("fisher_ratio", 0.0)

    # B1 with BKT profiles (swap profiles temporarily)
    bkt_students = []
    for s in students:
        bkt_s = StudentTrajectory(
            student_id=s.student_id,
            archetype=s.archetype,
            profiles=s.bkt_profiles,
            bkt_profiles=s.bkt_profiles,
            over_editing_rates=s.over_editing_rates,
        )
        bkt_students.append(bkt_s)

    bkt_b1 = analysis_b1_archetype_discrimination(
        bkt_students, {"M2_graph": cost_matrix}
    )
    bkt_fisher = bkt_b1.get("M2_graph", {}).get("fisher_ratio", 0.0)

    # B3 comparison
    raw_b3 = analysis_b3_trajectory_efficiency(students, cost_matrix)
    bkt_b3 = analysis_b3_trajectory_efficiency(bkt_students, cost_matrix)

    return {
        "raw_fisher": raw_fisher,
        "bkt_fisher": bkt_fisher,
        "fisher_preserved": abs(raw_fisher - bkt_fisher) / max(raw_fisher, 1e-10) < 0.5,
        "raw_efficiency_means": raw_b3["archetype_means"],
        "bkt_efficiency_means": bkt_b3["archetype_means"],
    }


# =============================================================================
# B7: Balanced vs Unbalanced OT — spec §5.7
# =============================================================================

def analysis_b7_balanced_vs_unbalanced(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
) -> dict:
    """Compare balanced W₁ vs unbalanced UW₁ at multiple reg_m values."""
    target = profile_to_array(TARGET_PROFILE)
    results_by_reg_m = {}

    for reg_m in REG_M_VALUES:
        student_data = {}
        for student in students:
            balanced_gaps = []
            unbalanced_gaps = []
            for profile in student.profiles:
                bg = mastery_gap(profile, cost_matrix, target, balanced=True)
                ug = mastery_gap(
                    profile, cost_matrix, target, balanced=False, reg_m=reg_m
                )
                balanced_gaps.append(bg)
                unbalanced_gaps.append(ug)
            student_data[student.student_id] = {
                "archetype": student.archetype,
                "balanced_gaps": balanced_gaps,
                "unbalanced_gaps": unbalanced_gaps,
            }

        # Correlation between balanced and unbalanced final gaps
        final_balanced = [
            d["balanced_gaps"][-1] for d in student_data.values()
        ]
        final_unbalanced = [
            d["unbalanced_gaps"][-1] for d in student_data.values()
        ]
        r, p_val = stats.pearsonr(final_balanced, final_unbalanced)

        # Fisher ratio for both (archetype discrimination at final session)
        bal_by_arch: dict[str, list[float]] = {}
        unbal_by_arch: dict[str, list[float]] = {}
        for d in student_data.values():
            bal_by_arch.setdefault(d["archetype"], []).append(d["balanced_gaps"][-1])
            unbal_by_arch.setdefault(d["archetype"], []).append(
                d["unbalanced_gaps"][-1]
            )

        bal_fisher = _compute_fisher(bal_by_arch)
        unbal_fisher = _compute_fisher(unbal_by_arch)

        # Key divergence: Archetype 4 (slow_steady) — uniform improvement
        slow_steady_bal = student_data.get("slow_steady_0", {}).get(
            "balanced_gaps", []
        )
        slow_steady_unbal = student_data.get("slow_steady_0", {}).get(
            "unbalanced_gaps", []
        )

        results_by_reg_m[f"reg_m={reg_m}"] = {
            "correlation": {"r": float(r), "p": float(p_val)},
            "balanced_fisher": bal_fisher,
            "unbalanced_fisher": unbal_fisher,
            "slow_steady_divergence": {
                "balanced_delta": (
                    float(slow_steady_bal[0] - slow_steady_bal[-1])
                    if slow_steady_bal
                    else None
                ),
                "unbalanced_delta": (
                    float(slow_steady_unbal[0] - slow_steady_unbal[-1])
                    if slow_steady_unbal
                    else None
                ),
            },
            "students": student_data,
        }

    return results_by_reg_m


def _compute_fisher(groups: dict[str, list[float]]) -> float:
    """Fisher discriminant ratio from grouped values."""
    all_vals = [v for vs in groups.values() for v in vs]
    if not all_vals:
        return 0.0
    grand_mean = np.mean(all_vals)
    between = sum(
        len(vs) * (np.mean(vs) - grand_mean) ** 2
        for vs in groups.values()
        if vs
    )
    within = sum(np.var(vs) * len(vs) for vs in groups.values() if len(vs) > 1)
    return float(between / max(within, 1e-10))


# =============================================================================
# Full Track B pipeline
# =============================================================================

def run_track_b(
    n_sessions: int = 10,
    noise_std: float = 0.03,
    base_seed: int = 42,
) -> dict:
    """Execute all Track B analyses.

    Returns a dict with all results for reporting.
    """
    logger.info("=== Track B: Synthetic Trajectory Analysis ===")

    # Generate students
    logger.info("Generating %d synthetic students...", 20)
    students = generate_all_students(n_sessions, noise_std, base_seed)

    # Build ground metrics
    ground_metrics = build_all_metrics(include_random=True)
    primary_metric = ground_metrics["M2_graph"]

    # B1: Archetype discrimination
    logger.info("Running B1: Archetype discrimination...")
    b1_results = analysis_b1_archetype_discrimination(students, ground_metrics)

    # B2: MasteryGap trajectories (primary metric)
    logger.info("Running B2: MasteryGap trajectories...")
    b2_results = analysis_b2_mastery_gap_trajectories(students, primary_metric)

    # B3: Trajectory efficiency
    logger.info("Running B3: Trajectory efficiency...")
    b3_results = analysis_b3_trajectory_efficiency(students, primary_metric)

    # B4: Barycenter
    logger.info("Running B4: Barycenter comparison...")
    b4_results = analysis_b4_barycenter(students, primary_metric)

    # B5: Ground metric sensitivity
    logger.info("Running B5: Ground metric sensitivity...")
    b5_results = analysis_b5_ground_metric_sensitivity(students, ground_metrics)

    # B6: BKT robustness
    logger.info("Running B6: BKT robustness...")
    b6_results = analysis_b6_bkt_robustness(students, primary_metric)

    # B7: Balanced vs unbalanced
    logger.info("Running B7: Balanced vs unbalanced OT...")
    b7_results = analysis_b7_balanced_vs_unbalanced(students, primary_metric)

    return {
        "metadata": {
            "n_students": len(students),
            "n_sessions": n_sessions,
            "noise_std": noise_std,
            "archetypes": {
                k: v["n_instances"] for k, v in ARCHETYPES.items()
            },
        },
        "students": [
            {
                "id": s.student_id,
                "archetype": s.archetype,
                "final_profile": s.profiles[-1],
            }
            for s in students
        ],
        "B1_archetype_discrimination": b1_results,
        "B2_mastery_gap_trajectories": b2_results,
        "B3_trajectory_efficiency": b3_results,
        "B4_barycenter": b4_results,
        "B5_ground_metric_sensitivity": b5_results,
        "B6_bkt_robustness": b6_results,
        "B7_balanced_vs_unbalanced": b7_results,
    }
