"""Experiment 5: Integrative Convergence Table (Spec §7).

Synthesises findings from Experiments 1-4 into a convergence table.
Each cell: aligns (V), partially aligns (~), contradicts (X), or no data (-).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from .tom_mapping import SKILL_ORDER, SKILL_TO_TOM_RANK


# Cell verdicts
ALIGN = "V"      # ✓
PARTIAL = "~"    # ~
CONTRADICT = "X" # ✗
NO_DATA = "-"    # —


def _judge_exp1_skill(results: Dict, skill: str) -> List[Tuple[str, str]]:
    """Judge Exp1 alignment for a specific skill across sources."""
    cells = []
    for src in results["per_source"]:
        # Check if this source has data for this skill
        if skill in src["skills"]:
            idx = src["skills"].index(skill)
            tom_r = src["tom_ranks"][idx]
            obs_r = src["observed_ranks"][idx]
            # For this skill: does observed rank direction match ToM rank?
            # Higher ToM rank should have higher difficulty
            if src["kendall_tau"] > 0.3:
                cells.append((src["source"][:3], ALIGN))
            elif src["kendall_tau"] > 0:
                cells.append((src["source"][:3], PARTIAL))
            else:
                cells.append((src["source"][:3], CONTRADICT))
        else:
            cells.append((src["source"][:3], NO_DATA))
    return cells


def _judge_exp2_skill(results: Dict, skill: str) -> List[Tuple[str, str]]:
    """Judge Exp2: does NMT improvement differ by ToM level for this skill?"""
    from .tom_mapping import tom_group
    cells = []
    group = tom_group(skill)

    for src in results["per_source"]:
        has_skill = any(
            m.get("skill") == skill
            for m in src.get("per_type", [])
        )
        if not has_skill:
            cells.append((src["source"][:3], NO_DATA))
            continue

        if src.get("prediction_met", False):
            cells.append((src["source"][:3], ALIGN))
        else:
            cells.append((src["source"][:3], CONTRADICT))
    return cells


def _judge_exp3_skill(results: Dict, skill: str) -> List[Tuple[str, str]]:
    """Judge Exp3: does expert-novice gap widen at this ToM level?"""
    cells = []
    for src in results["per_source"]:
        has_skill = any(
            m.get("skill") == skill
            for m in src.get("per_type", [])
        )
        if not has_skill:
            if src.get("kendall_tau") is None:
                cells.append((src["source"][:3], NO_DATA))
            else:
                cells.append((src["source"][:3], NO_DATA))
            continue

        if src.get("prediction_met"):
            cells.append((src["source"][:3], ALIGN))
        elif src.get("prediction_met") is None:
            cells.append((src["source"][:3], PARTIAL))
        else:
            cells.append((src["source"][:3], CONTRADICT))
    return cells


def _judge_exp4_skill(results: Dict, skill: str) -> List[Tuple[str, str]]:
    """Judge Exp4: do unnecessary edits decrease at this ToM level?"""
    cells = []
    for src in results["per_source"]:
        has_skill = any(
            m.get("skill") == skill
            for m in src.get("per_type", [])
        )
        if not has_skill:
            if src.get("prediction_met") is not None:
                # Qualitative source
                cells.append((src["source"][:3], PARTIAL))
            else:
                cells.append((src["source"][:3], NO_DATA))
            continue

        if src.get("prediction_met"):
            cells.append((src["source"][:3], ALIGN))
        else:
            cells.append((src["source"][:3], CONTRADICT))
    return cells


def build_convergence_table(
    exp1: Dict, exp2: Dict, exp3: Dict, exp4: Dict
) -> Dict:
    """Build the convergence table (Spec §7.2).

    Returns a structured dict with the table data and aggregate statistics.
    """
    table = {}
    all_verdicts = []

    for skill in SKILL_ORDER:
        tom_rank = SKILL_TO_TOM_RANK[skill]
        row = {
            "skill": skill,
            "tom_rank": tom_rank,
            "exp1": _judge_exp1_skill(exp1, skill),
            "exp2": _judge_exp2_skill(exp2, skill),
            "exp3": _judge_exp3_skill(exp3, skill),
            "exp4": _judge_exp4_skill(exp4, skill),
        }
        table[skill] = row

        # Collect all verdicts for aggregate stats
        for exp_key in ["exp1", "exp2", "exp3", "exp4"]:
            for _, verdict in row[exp_key]:
                if verdict != NO_DATA:
                    all_verdicts.append(verdict)

    # Aggregate statistics (Spec §7.3)
    n_align = all_verdicts.count(ALIGN)
    n_partial = all_verdicts.count(PARTIAL)
    n_contradict = all_verdicts.count(CONTRADICT)
    n_total = len(all_verdicts)

    denom = n_align + n_contradict
    convergence_ratio = n_align / denom if denom > 0 else 0

    # Binomial test: is convergence ratio > 0.5 (chance)?
    if denom > 0:
        binom_p = stats.binom_test(n_align, denom, 0.5, alternative="greater")
    else:
        binom_p = 1.0

    return {
        "table": {
            skill: {
                "tom_rank": row["tom_rank"],
                "exp1_cells": [{"src": s, "verdict": v} for s, v in row["exp1"]],
                "exp2_cells": [{"src": s, "verdict": v} for s, v in row["exp2"]],
                "exp3_cells": [{"src": s, "verdict": v} for s, v in row["exp3"]],
                "exp4_cells": [{"src": s, "verdict": v} for s, v in row["exp4"]],
            }
            for skill, row in table.items()
        },
        "aggregate": {
            "n_align": n_align,
            "n_partial": n_partial,
            "n_contradict": n_contradict,
            "n_no_data": sum(1 for skill in SKILL_ORDER
                             for exp_key in ["exp1", "exp2", "exp3", "exp4"]
                             for _, v in table[skill][exp_key] if v == NO_DATA),
            "convergence_ratio": round(convergence_ratio, 4),
            "binomial_p": round(float(binom_p), 6),
        },
    }


def run_all(exp1: Dict, exp2: Dict, exp3: Dict, exp4: Dict) -> Dict:
    """Run Experiment 5."""
    conv = build_convergence_table(exp1, exp2, exp3, exp4)

    cr = conv["aggregate"]["convergence_ratio"]
    if cr >= 0.80:
        interpretation = (f"STRONG VALIDATION: Convergence ratio {cr:.2f} >= 0.80 "
                          f"across 4 experiments. Binomial p={conv['aggregate']['binomial_p']:.4f}.")
    elif cr >= 0.60:
        interpretation = (f"MODERATE VALIDATION: Convergence ratio {cr:.2f}. "
                          "Framework largely supported but some areas need revision.")
    else:
        interpretation = (f"WEAK VALIDATION: Convergence ratio {cr:.2f} < 0.60. "
                          "Framework needs significant revision.")

    return {
        "experiment": "Exp5_Convergence",
        **conv,
        "interpretation": interpretation,
    }
