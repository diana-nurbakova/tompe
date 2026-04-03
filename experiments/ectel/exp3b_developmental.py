"""Experiment 3b: Developmental ToM Gradient (Spec §5b).

Prediction: PE skill acquisition follows the ToM hierarchy over time.
Low-ToM skills (S1-S2) are mastered before high-ToM skills (S3+).

Methods:
  A — First-mastery-session analysis (longitudinal)
  B — Learning curve slope analysis (longitudinal)
  C — Phase improvement ratio (longitudinal)
  D — Experience-gradient reframing (cross-sectional, from Exp 3 data)
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from scipy import stats

from .tom_mapping import SKILL_TO_TOM_RANK


def first_mastery_session(
    performance_by_session: List[float], threshold: float = 0.80
) -> int:
    """Find the first session where performance meets or exceeds threshold.

    Returns 1-indexed session number, or n_sessions + 1 if never reached.
    """
    for i, p in enumerate(performance_by_session):
        if p >= threshold:
            return i + 1
    return len(performance_by_session) + 1


def compute_learning_curve_params(
    performance_by_session: List[float],
) -> Dict[str, float]:
    """Fit a linear model and extract slope + early/late slopes."""
    perf = np.array(performance_by_session, dtype=float)
    sessions = np.arange(1, len(perf) + 1, dtype=float)
    slope, intercept = np.polyfit(sessions, perf, 1)

    # Early slope (first half) vs late slope (second half)
    mid = len(perf) // 2
    if mid >= 2:
        early_slope = np.polyfit(sessions[:mid], perf[:mid], 1)[0]
        late_slope = np.polyfit(sessions[mid:], perf[mid:], 1)[0]
    else:
        early_slope = late_slope = slope

    return {
        "overall_slope": round(float(slope), 4),
        "early_slope": round(float(early_slope), 4),
        "late_slope": round(float(late_slope), 4),
        "intercept": round(float(intercept), 4),
    }


def phase_improvement(
    performance_by_session: List[float], n_phases: int = 3
) -> Dict[str, float]:
    """Compute improvement in early, middle, late phases."""
    perf = np.array(performance_by_session, dtype=float)
    n = len(perf)
    phase_size = n // n_phases
    phases = []
    for i in range(n_phases):
        start = i * phase_size
        end = (i + 1) * phase_size if i < n_phases - 1 else n
        phases.append(float(np.mean(perf[start:end])))

    early_improvement = phases[1] - phases[0]
    late_improvement = phases[2] - phases[1]

    return {
        "phase_means": [round(p, 4) for p in phases],
        "early_improvement": round(early_improvement, 4),
        "late_improvement": round(late_improvement, 4),
        "ratio_late_to_early": (
            round(late_improvement / early_improvement, 4)
            if early_improvement > 0.001
            else float("inf")
        ),
    }


# ── Source-specific analyzers ──────────────────────────────────────────


def analyze_koponen_2015(source: dict) -> Dict:
    """Source 3b-A: Koponen (2015) — Longitudinal PE course.

    Methods A, B, C: first-mastery, learning curve slopes, phase improvement.
    """
    per_type = []
    tom_ranks = []
    mastery_sessions = []
    early_slopes = []
    late_slopes = []
    early_improvements = []
    late_improvements = []

    for m in source["measures"]:
        skill = m["skill"]
        tom_rank = SKILL_TO_TOM_RANK[skill]
        perf = m["performance_by_session"]

        ms = first_mastery_session(perf)
        curve = compute_learning_curve_params(perf)
        phases = phase_improvement(perf)

        tom_ranks.append(tom_rank)
        mastery_sessions.append(ms)
        early_slopes.append(curve["early_slope"])
        late_slopes.append(curve["late_slope"])
        early_improvements.append(phases["early_improvement"])
        late_improvements.append(phases["late_improvement"])

        per_type.append({
            "error_type": m["error_type"],
            "skill": skill,
            "tom_rank": tom_rank,
            "performance_by_session": perf,
            "mastery_session": ms,
            "curve": curve,
            "phases": phases,
        })

    # Method A: Kendall's tau between ToM rank and first-mastery session
    tau_a, p_a = stats.kendalltau(tom_ranks, mastery_sessions)

    # Method B: early slope should be steeper for low-ToM
    # (negative correlation between ToM rank and early slope)
    tau_b, p_b = stats.kendalltau(tom_ranks, early_slopes)

    # Method C: late-to-early ratio should increase with ToM rank
    ratios = [
        li / ei if ei > 0.001 else float("inf")
        for li, ei in zip(late_improvements, early_improvements)
    ]
    finite_ratios = [(tr, r) for tr, r in zip(tom_ranks, ratios) if np.isfinite(r)]
    if len(finite_ratios) >= 3:
        tau_c, p_c = stats.kendalltau(
            [x[0] for x in finite_ratios], [x[1] for x in finite_ratios]
        )
    else:
        tau_c, p_c = 0.0, 1.0

    return {
        "source": "Koponen2015",
        "n": len(per_type),
        "n_sessions": source["n_sessions"],
        "methods": {
            "A_mastery_session": {
                "description": "First session at mastery threshold (0.80)",
                "kendall_tau": round(float(tau_a), 4),
                "p_value": round(float(p_a), 4),
                "prediction_met": float(tau_a) > 0,
            },
            "B_learning_curve": {
                "description": "Early slope decreases with ToM rank (low-ToM learns faster early)",
                "kendall_tau": round(float(tau_b), 4),
                "p_value": round(float(p_b), 4),
                "prediction_met": float(tau_b) < 0,
            },
            "C_phase_improvement": {
                "description": "Late/early improvement ratio increases with ToM rank",
                "kendall_tau": round(float(tau_c), 4),
                "p_value": round(float(p_c), 4),
                "prediction_met": float(tau_c) > 0,
            },
        },
        "per_type": per_type,
        "prediction_met": float(tau_a) > 0,
        "kendall_tau": round(float(tau_a), 4),
        "p_value": round(float(p_a), 4),
    }


def analyze_cross_sectional(sources: List[dict]) -> Dict:
    """Method D: Reframe cross-sectional expert-novice data as developmental evidence.

    Uses Daems (2017) and De Almeida (2013) data already encoded for Exp 3.
    The expert/novice ratio should correlate with ToM rank: higher-ToM skills
    show larger expert advantage, suggesting they develop later with experience.
    """
    tom_ranks = []
    ratios = []
    per_type = []

    for src in sources:
        if src["source"] == "Koponen2015":
            continue  # skip longitudinal source
        for m in src["measures"]:
            if "skill" not in m:
                continue
            skill = m["skill"]
            tom_rank = SKILL_TO_TOM_RANK[skill]

            # Compute expert/novice ratio from available fields
            exp_perf = m.get("experienced_rate") or m.get("professional_effort")
            nov_perf = m.get("novice_rate") or m.get("student_effort")

            if isinstance(exp_perf, (int, float)) and isinstance(nov_perf, (int, float)):
                if nov_perf > 0:
                    ratio = exp_perf / nov_perf
                    gap = exp_perf - nov_perf
                else:
                    ratio = float("inf")
                    gap = exp_perf
                tom_ranks.append(tom_rank)
                ratios.append(ratio)
                per_type.append({
                    "source": src["source"],
                    "error_type": m["error_type"],
                    "skill": skill,
                    "tom_rank": tom_rank,
                    "expert_performance": exp_perf,
                    "novice_performance": nov_perf,
                    "expert_novice_ratio": round(ratio, 4) if np.isfinite(ratio) else None,
                    "gap": round(gap, 4),
                })

    if len(tom_ranks) >= 3:
        tau, p = stats.kendalltau(tom_ranks, ratios)
    elif len(tom_ranks) == 2:
        tau = 1.0 if (tom_ranks[1] - tom_ranks[0]) * (ratios[1] - ratios[0]) > 0 else -1.0
        p = 1.0
    else:
        tau, p = 0.0, 1.0

    return {
        "source": "CrossSectional_Reframing",
        "description": "Method D: experience-gradient analysis (Daems 2017 + De Almeida 2013)",
        "n": len(per_type),
        "kendall_tau": round(float(tau), 4) if not np.isnan(tau) else 0.0,
        "p_value": round(float(p), 4) if not np.isnan(p) else 1.0,
        "prediction_met": float(tau) > 0 if not np.isnan(tau) else False,
        "per_type": per_type,
    }


# ── Main entry point ──────────────────────────────────────────────────


def run_all(sources: List[dict]) -> Dict:
    """Run Experiment 3b across all sources."""
    per_source = []

    # Longitudinal analysis (Methods A, B, C)
    for src in sources:
        if src.get("type") == "longitudinal" and src["source"] == "Koponen2015":
            per_source.append(analyze_koponen_2015(src))

    # Cross-sectional reframing (Method D)
    cross = analyze_cross_sectional(sources)
    if cross["n"] > 0:
        per_source.append(cross)

    # Aggregate across methods
    with_tau = [r for r in per_source if r.get("kendall_tau") is not None]
    confirmed = sum(1 for r in with_tau if r.get("prediction_met"))

    # Count longitudinal methods confirmed (from Koponen2015)
    longitudinal = [r for r in per_source if r["source"] == "Koponen2015"]
    n_methods_confirmed = 0
    n_methods_total = 0
    if longitudinal:
        methods = longitudinal[0]["methods"]
        for method_key, method_result in methods.items():
            n_methods_total += 1
            if method_result["prediction_met"]:
                n_methods_confirmed += 1

    return {
        "experiment": "Exp3b_DevelopmentalGradient",
        "prediction": (
            "Low-ToM skills (S1-S2) mastered before high-ToM skills (S3+). "
            "Mastery session increases with ToM rank; early improvement steeper "
            "for low-ToM; late/early improvement ratio increases with ToM rank."
        ),
        "per_source": per_source,
        "aggregate": {
            "n_sources": len(with_tau),
            "confirmed_count": confirmed,
            "n_longitudinal_methods": n_methods_total,
            "n_longitudinal_confirmed": n_methods_confirmed,
            "mean_tau": round(float(np.mean(
                [r["kendall_tau"] for r in with_tau]
            )), 4) if with_tau else None,
        },
        "interpretation": _interpret(with_tau, confirmed, n_methods_confirmed, n_methods_total),
    }


def _interpret(
    with_tau: list, confirmed: int,
    n_methods_confirmed: int, n_methods_total: int,
) -> str:
    total = len(with_tau)
    if total == 0:
        return "INSUFFICIENT DATA: No sources with developmental trajectory data."

    parts = []
    if n_methods_total > 0:
        if n_methods_confirmed == n_methods_total:
            parts.append(
                f"All {n_methods_total} longitudinal methods confirm "
                "developmental ordering follows ToM hierarchy"
            )
        elif n_methods_confirmed > 0:
            parts.append(
                f"{n_methods_confirmed}/{n_methods_total} longitudinal methods "
                "support developmental ordering"
            )
        else:
            parts.append("Longitudinal methods do not support developmental ordering")

    if confirmed == total:
        return f"CONFIRMED: {'. '.join(parts)}. All {total} analyses show predicted pattern."
    elif confirmed > 0:
        return f"PARTIALLY CONFIRMED: {'. '.join(parts)}. {confirmed}/{total} analyses positive."
    else:
        return f"DISCONFIRMED: {'. '.join(parts)}. No analyses show predicted pattern."
