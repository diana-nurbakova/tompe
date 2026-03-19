"""Experiment 2: Fluency Paradox as ToM-Selective Detection Impairment (Spec §4).

Prediction: NMT's fluency improvement selectively impairs detection of high-ToM
errors (S3+) while leaving low-ToM error detection (S1-S2) largely unaffected.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from scipy import stats

from .tom_mapping import is_high_tom, is_low_tom, tom_group


def _compute_improvement_ratio(nmt_val: float, smt_val: float) -> float:
    """Compute NMT improvement ratio: (SMT - NMT) / SMT.

    Positive = NMT improved (fewer errors / higher correction).
    For correction rates, we want (NMT - SMT) / SMT inverted.
    """
    if smt_val == 0:
        return 0.0
    return (smt_val - nmt_val) / smt_val


def analyze_yamada(source: dict) -> Dict:
    """Source 2A: Yamada (2019) — NMT vs SMT correction rates by error type."""
    low_tom_drops, high_tom_drops = [], []

    for m in source["measures"]:
        # For correction rates: drop = SMT_rate - NMT_rate (positive = NMT worse)
        drop = m["smt_correction"] - m["nmt_correction"]
        skill = m["skill"]
        if is_low_tom(skill):
            low_tom_drops.append(drop)
        else:
            high_tom_drops.append(drop)

    low_mean = np.mean(low_tom_drops) if low_tom_drops else 0
    high_mean = np.mean(high_tom_drops) if high_tom_drops else 0

    return {
        "source": "Yamada2019",
        "low_tom_drop": round(float(low_mean), 4),
        "high_tom_drop": round(float(high_mean), 4),
        "asymmetry": round(float(high_mean - low_mean), 4),
        "prediction_met": high_mean > low_mean,
        "notes": "High-ToM drop >> Low-ToM drop confirms fluency paradox",
        "per_type": [
            {
                "error_type": m["error_type"],
                "skill": m["skill"],
                "tom_group": tom_group(m["skill"]),
                "nmt_correction": m["nmt_correction"],
                "smt_correction": m["smt_correction"],
                "drop": round(m["smt_correction"] - m["nmt_correction"], 4),
            }
            for m in source["measures"]
        ],
    }


def analyze_bentivogli(source: dict) -> Dict:
    """Source 2B: Bentivogli (2018) — NMT reduction % by error category."""
    low_tom, high_tom = [], []
    for m in source["measures"]:
        r = m["nmt_reduction_pct"]
        if is_low_tom(m["skill"]):
            low_tom.append(r)
        else:
            high_tom.append(r)

    low_mean = np.mean(low_tom) if low_tom else 0
    high_mean = np.mean(high_tom) if high_tom else 0

    return {
        "source": "Bentivogli2018",
        "low_tom_reduction_pct": round(float(low_mean), 1),
        "high_tom_reduction_pct": round(float(high_mean), 1),
        "asymmetry": round(float(low_mean - high_mean), 1),
        "prediction_met": low_mean > high_mean,
        "per_type": [
            {
                "error_type": m["error_type"],
                "skill": m["skill"],
                "tom_group": tom_group(m["skill"]),
                "nmt_reduction_pct": m["nmt_reduction_pct"],
            }
            for m in source["measures"]
        ],
    }


def analyze_van_brussel(source: dict) -> Dict:
    """Source 2C: Van Brussel (2018) — NMT vs SMT error counts."""
    low_ratios, high_ratios = [], []
    per_type = []
    for m in source["measures"]:
        ratio = _compute_improvement_ratio(m["nmt_count"], m["smt_count"])
        entry = {
            "error_type": m["error_type"],
            "skill": m["skill"],
            "tom_group": tom_group(m["skill"]),
            "nmt_count": m["nmt_count"],
            "smt_count": m["smt_count"],
            "improvement_ratio": round(ratio, 4),
        }
        per_type.append(entry)
        if is_low_tom(m["skill"]):
            low_ratios.append(ratio)
        else:
            high_ratios.append(ratio)

    low_mean = np.mean(low_ratios) if low_ratios else 0
    high_mean = np.mean(high_ratios) if high_ratios else 0

    return {
        "source": "VanBrussel2018",
        "low_tom_improvement": round(float(low_mean), 4),
        "high_tom_improvement": round(float(high_mean), 4),
        "asymmetry": round(float(low_mean - high_mean), 4),
        "prediction_met": low_mean > high_mean,
        "per_type": per_type,
    }


def analyze_koponen(source: dict) -> Dict:
    """Source 2D: Koponen et al. (2019) — Overlooked errors NMT vs SMT."""
    per_type = []
    low_nmt, low_smt, high_nmt, high_smt = [], [], [], []
    for m in source["measures"]:
        skill = m["skill"]
        nmt_o = m.get("nmt_overlooked", 0)
        smt_o = m.get("smt_overlooked", 0)
        # improvement_ratio: positive = NMT has fewer overlooked errors (better)
        ratio = (smt_o - nmt_o) / smt_o if smt_o > 0 else 0.0
        per_type.append({
            "error_type": m["error_type"],
            "skill": skill,
            "tom_group": tom_group(skill),
            "nmt_overlooked": nmt_o,
            "smt_overlooked": smt_o,
            "improvement_ratio": round(ratio, 4),
        })
        if is_low_tom(skill):
            low_nmt.append(nmt_o)
            low_smt.append(smt_o)
        else:
            high_nmt.append(nmt_o)
            high_smt.append(smt_o)

    # NMT makes overlooking worse for high-ToM?
    low_change = sum(low_nmt) - sum(low_smt)
    high_change = sum(high_nmt) - sum(high_smt)

    return {
        "source": "Koponen2019",
        "low_tom_overlooked_change": int(low_change),
        "high_tom_overlooked_change": int(high_change),
        "prediction_met": high_change > low_change,
        "notes": "Positive = NMT increases overlooking vs SMT",
        "per_type": per_type,
    }


def run_all(sources: List[dict]) -> Dict:
    """Run Experiment 2 across all sources."""
    analyzers = {
        "Yamada2019": analyze_yamada,
        "Bentivogli2018": analyze_bentivogli,
        "VanBrussel2018": analyze_van_brussel,
        "Koponen2019": analyze_koponen,
    }

    per_source = []
    for src in sources:
        name = src["source"]
        if name in analyzers:
            per_source.append(analyzers[name](src))

    confirmed = sum(1 for r in per_source if r.get("prediction_met", False))

    return {
        "experiment": "Exp2_FluencyParadox",
        "prediction": ("NMT improves low-ToM error rates substantially but "
                       "high-ToM rates modestly or not at all"),
        "per_source": per_source,
        "aggregate": {
            "n_sources": len(per_source),
            "confirmed_count": confirmed,
            "confirmation_rate": round(confirmed / max(len(per_source), 1), 2),
        },
        "interpretation": _interpret(per_source, confirmed),
    }


def _interpret(results: List[Dict], confirmed: int) -> str:
    total = len(results)
    if confirmed == total:
        return (f"CONFIRMED: All {total} sources show asymmetric NMT impact — "
                "low-ToM errors improve more than high-ToM errors.")
    elif confirmed > total / 2:
        return (f"MOSTLY CONFIRMED: {confirmed}/{total} sources show the predicted asymmetry.")
    else:
        return (f"DISCONFIRMED: Only {confirmed}/{total} sources show the predicted asymmetry. "
                "The fluency paradox may not be ToM-mediated.")
