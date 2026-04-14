"""Experiment 1: ToM Ordering vs Published Difficulty Rankings (Spec §3).

Prediction: Error types requiring higher-order ToM are harder to detect
and require more cognitive effort. Tests via Kendall's tau between
ToM ordinal rank and observed difficulty rank across 5 sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy import stats

from .tom_mapping import SKILL_TO_TOM_RANK


@dataclass
class RankCorrelationResult:
    source: str
    n: int
    tau: float
    p_value: float
    tom_ranks: List[int]
    observed_ranks: List[float]
    skills: List[str]
    notes: str = ""


def _extract_temnikova(source: dict) -> Tuple[List[str], List[int], List[float]]:
    """Extract (skills, tom_ranks, difficulty_ranks) from Temnikova data."""
    skills, tom_ranks, diff_ranks = [], [], []
    for m in source["measures"]:
        skills.append(m["skill"])
        tom_ranks.append(SKILL_TO_TOM_RANK[m["skill"]])
        diff_ranks.append(m["difficulty_rank"])
    return skills, tom_ranks, diff_ranks


def _extract_daems(source: dict) -> Tuple[List[str], List[int], List[float]]:
    """Extract from Daems — use fixation_rank as difficulty proxy."""
    skills, tom_ranks, diff_ranks = [], [], []
    for m in source["measures"]:
        skills.append(m["skill"])
        tom_ranks.append(SKILL_TO_TOM_RANK[m["skill"]])
        diff_ranks.append(m["fixation_rank"])
    return skills, tom_ranks, diff_ranks



def _extract_yamada(source: dict) -> Tuple[List[str], List[int], List[float]]:
    """Extract from Yamada — use (1 - NMT correction rate) as difficulty."""
    skills, tom_ranks, diff_ranks = [], [], []
    for m in source["measures"]:
        skills.append(m["skill"])
        tom_ranks.append(SKILL_TO_TOM_RANK[m["skill"]])
        diff_ranks.append(1.0 - m["nmt_correction"])
    return skills, tom_ranks, diff_ranks


def _extract_popovic(source: dict) -> Tuple[List[str], List[int], List[float]]:
    """Extract from Popovic — use NMT error rate as proxy for residual difficulty."""
    skills, tom_ranks, diff_ranks = [], [], []
    for m in source["measures"]:
        skills.append(m["skill"])
        tom_ranks.append(SKILL_TO_TOM_RANK[m["skill"]])
        diff_ranks.append(m["nmt_rate"])
    return skills, tom_ranks, diff_ranks


_EXTRACTORS = {
    "Temnikova2010": _extract_temnikova,
    "Daems2017": _extract_daems,
    "Yamada2019": _extract_yamada,
    "Popovic2018": _extract_popovic,
}


def run_source(source: dict) -> RankCorrelationResult:
    """Compute Kendall's tau for a single source."""
    name = source["source"]
    extractor = _EXTRACTORS[name]
    skills, tom_ranks, diff_ranks = extractor(source)

    tau, p = stats.kendalltau(tom_ranks, diff_ranks)

    return RankCorrelationResult(
        source=name,
        n=len(skills),
        tau=tau,
        p_value=p,
        tom_ranks=tom_ranks,
        observed_ranks=diff_ranks,
        skills=skills,
    )


def run_all(sources: List[dict]) -> Dict:
    """Run Experiment 1 across all sources.

    Returns dict with per-source results and aggregate meta-analytic result.
    """
    results = []
    all_tom, all_obs, all_weights = [], [], []

    for src in sources:
        r = run_source(src)
        results.append(r)

        # Pool for aggregate: weight by n
        n = r.n
        all_tom.extend(r.tom_ranks)
        all_obs.extend(r.observed_ranks)
        # Weights: use participant count if available
        n_part = _get_n_participants(src)
        all_weights.extend([n_part] * n)

    # Aggregate rank correlation (unweighted pooling of all data points)
    agg_tau, agg_p = stats.kendalltau(all_tom, all_obs)

    # Weighted Kendall's tau via Fisher z-transform of per-source taus
    taus = [r.tau for r in results]
    ns = [r.n for r in results]
    fisher_z = [np.arctanh(max(min(t, 0.99), -0.99)) for t in taus]
    weights = [n - 3 for n in ns]  # Kendall weight = n-3
    if sum(w for w in weights if w > 0) > 0:
        pos_weights = [max(w, 0.1) for w in weights]
        weighted_z = np.average(fisher_z, weights=pos_weights)
        weighted_tau = np.tanh(weighted_z)
    else:
        weighted_tau = np.mean(taus)

    return {
        "experiment": "Exp1_DifficultyOrdering",
        "prediction": "tau > 0: higher ToM rank correlates with greater difficulty",
        "per_source": [
            {
                "source": r.source,
                "n": r.n,
                "kendall_tau": round(r.tau, 4),
                "p_value": round(r.p_value, 4),
                "skills": r.skills,
                "tom_ranks": r.tom_ranks,
                "observed_ranks": [round(x, 4) for x in r.observed_ranks],
            }
            for r in results
        ],
        "aggregate": {
            "pooled_tau": round(agg_tau, 4),
            "pooled_p": round(agg_p, 4),
            "pooled_n": len(all_tom),
            "weighted_tau": round(weighted_tau, 4),
            "n_sources": len(results),
            "positive_count": sum(1 for r in results if r.tau > 0),
        },
        "interpretation": _interpret(results, agg_tau, agg_p),
    }


def _get_n_participants(source: dict) -> int:
    """Extract participant count for weighting."""
    n = source.get("n_participants")
    if n is None:
        return 10  # default weight for literature-derived rankings
    if isinstance(n, dict):
        return sum(n.values())
    return n


def _interpret(results: List[RankCorrelationResult], agg_tau: float, agg_p: float) -> str:
    pos = sum(1 for r in results if r.tau > 0)
    total = len(results)
    if agg_tau > 0 and agg_p < 0.05:
        return (f"CONFIRMED: Positive correlation (tau={agg_tau:.3f}, p={agg_p:.4f}). "
                f"{pos}/{total} sources show positive tau.")
    elif agg_tau > 0:
        return (f"TREND: Positive but not significant (tau={agg_tau:.3f}, p={agg_p:.4f}). "
                f"{pos}/{total} sources show positive tau.")
    else:
        return (f"DISCONFIRMED: Non-positive correlation (tau={agg_tau:.3f}). "
                f"Only {pos}/{total} sources positive.")
