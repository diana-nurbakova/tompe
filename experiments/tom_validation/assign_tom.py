"""§4.3–4.4 — Assign ToM levels and compute segment-level covariates."""

from __future__ import annotations

import pandas as pd
import numpy as np

from .config import MQM_TO_TOM, TOM_LABELS, UNMAPPED_CATEGORIES


def assign_tom_levels(aligned_df: pd.DataFrame) -> pd.DataFrame:
    """Map MQM category to ToM level for each aligned error.

    Adds columns: tom_level, tom_label, is_ambiguous.
    Drops rows with unmappable categories.
    """
    df = aligned_df.copy()

    df["tom_level"] = df["category"].map(MQM_TO_TOM)
    df["tom_label"] = df["tom_level"].map(TOM_LABELS)
    df["is_ambiguous"] = df["category"] == "Accuracy/Mistranslation"

    # Drop unmapped
    n_before = len(df)
    df = df.dropna(subset=["tom_level"])
    df["tom_level"] = df["tom_level"].astype(int)
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        print(f"  Dropped {n_dropped} errors with unmapped categories")

    print(f"  ToM assignment: {len(df)} errors across L0-L3")
    for level in sorted(df["tom_level"].unique()):
        n = (df["tom_level"] == level).sum()
        print(f"    {TOM_LABELS[level]}: {n} errors")

    return df


def compute_covariates(
    tom_df: pd.DataFrame,
    raw_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute segment-level covariates (§4.4).

    Adds columns: segment_length, system_quality, error_density.
    """
    df = tom_df.copy()

    # Segment length: token count of source text
    df["segment_length"] = df["source_text"].apply(
        lambda x: len(x.split()) if isinstance(x, str) else 0
    )

    # System quality: mean MQM score per system
    # Lower = better (fewer/less severe errors)
    # Use detection_count as a proxy for error weight
    sys_quality = df.groupby("system").agg(
        mean_detection=("detection_count", "mean"),
        n_errors=("error_id", "count"),
    ).reset_index()
    sys_quality["system_quality"] = -sys_quality["n_errors"]  # more errors = worse
    sys_quality_map = dict(zip(sys_quality["system"], sys_quality["system_quality"]))
    df["system_quality"] = df["system"].map(sys_quality_map)

    # Error density per segment-system pair
    seg_sys_counts = df.groupby(["segment_id", "system"]).size().reset_index(name="n_errors_seg")
    seg_lengths = df.groupby(["segment_id", "system"])["segment_length"].first().reset_index()
    density = seg_sys_counts.merge(seg_lengths, on=["segment_id", "system"])
    density["error_density"] = density["n_errors_seg"] / density["segment_length"].clip(lower=1)
    density_map = {(r["segment_id"], r["system"]): r["error_density"]
                   for _, r in density.iterrows()}
    df["error_density"] = df.apply(
        lambda r: density_map.get((r["segment_id"], r["system"]), 0), axis=1
    )

    return df


def build_rater_level_data(tom_df: pd.DataFrame) -> pd.DataFrame:
    """Build rater × error dataset for V4 (§5.5).

    Each unique error generates one row per rater (detected=0/1).
    """
    rows = []
    for _, err in tom_df.iterrows():
        detected = err["raters_detected"].split(",") if err["raters_detected"] else []
        missed = err["raters_missed"].split(",") if err["raters_missed"] else []

        for rater in detected:
            if rater:
                rows.append({
                    "error_id": err["error_id"],
                    "segment_id": err["segment_id"],
                    "system": err["system"],
                    "doc": err["doc"],
                    "rater": rater,
                    "detected": 1,
                    "tom_level": err["tom_level"],
                    "category": err["category"],
                    "severity": err["severity"],
                    "segment_length": err.get("segment_length", 0),
                    "system_quality": err.get("system_quality", 0),
                })
        for rater in missed:
            if rater:
                rows.append({
                    "error_id": err["error_id"],
                    "segment_id": err["segment_id"],
                    "system": err["system"],
                    "doc": err["doc"],
                    "rater": rater,
                    "detected": 0,
                    "tom_level": err["tom_level"],
                    "category": err["category"],
                    "severity": err["severity"],
                    "segment_length": err.get("segment_length", 0),
                    "system_quality": err.get("system_quality", 0),
                })

    return pd.DataFrame(rows)
