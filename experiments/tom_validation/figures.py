"""§7.2 — Generate publication-quality figures.

Figure V1: Box plot of detection rate by ToM level.
Figure V2: Heatmap of detection rate by MQM subcategory × ToM level.
Figure V3: Forest plot of rater ToM slopes (from V4).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

from .config import TOM_LABELS


def _setup_style():
    """Set publication-quality plot defaults."""
    sns.set_style("whitegrid")
    plt.rcParams.update({
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.dpi": 150,
    })


def figure_v1_detection_boxplot(
    tom_df: pd.DataFrame,
    output_dir: Path,
) -> Path:
    """Figure V1: Box plot of detection rate by ToM level (§7.2).

    Shows distribution of detection rates per level, with jittered points
    colored by severity.
    """
    _setup_style()
    fig, ax = plt.subplots(figsize=(8, 5))

    df = tom_df.copy()
    df["tom_label"] = df["tom_level"].map(TOM_LABELS)

    # Order levels
    level_order = [TOM_LABELS[i] for i in sorted(TOM_LABELS.keys()) if i in df["tom_level"].values]

    # Color palette for severity
    sev_colors = {"Major": "#d62728", "Minor": "#1f77b4", "Neutral": "#7f7f7f"}

    # Box plot
    sns.boxplot(
        data=df, x="tom_label", y="detection_rate",
        order=level_order, color="lightgray", width=0.5,
        fliersize=0, ax=ax,
    )

    # Jittered points colored by severity
    for sev, color in sev_colors.items():
        subset = df[df["severity"] == sev]
        if len(subset) == 0:
            continue
        jitter = np.random.normal(0, 0.08, size=len(subset))
        x_pos = [level_order.index(lab) + j for lab, j in zip(subset["tom_label"], jitter)]
        ax.scatter(
            x_pos, subset["detection_rate"],
            c=color, alpha=0.15, s=8, label=sev, zorder=2,
        )

    # Mean markers
    means = df.groupby("tom_label")["detection_rate"].mean()
    for i, label in enumerate(level_order):
        if label in means.index:
            ax.plot(i, means[label], "D", color="black", markersize=7, zorder=3)

    ax.set_xlabel("ToM Level")
    ax.set_ylabel("Detection Rate")
    ax.set_title("Error Detection Rate by ToM Level")
    ax.set_ylim(-0.05, 1.15)
    ax.legend(title="Severity", loc="upper right")

    # Add mean annotation
    for i, label in enumerate(level_order):
        if label in means.index:
            ax.annotate(
                f"M={means[label]:.3f}",
                (i, means[label] + 0.06),
                ha="center", fontsize=9,
            )

    plt.tight_layout()
    path = output_dir / "V1_detection_boxplot.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_v2_category_heatmap(
    tom_df: pd.DataFrame,
    output_dir: Path,
) -> Path:
    """Figure V2: Heatmap of detection rate by MQM subcategory × ToM level (§7.2)."""
    _setup_style()

    # Compute mean detection rate per category
    cat_stats = tom_df.groupby(["category", "tom_level"]).agg(
        mean_det=("detection_rate", "mean"),
        n=("error_id", "count"),
    ).reset_index()

    # Pivot for heatmap
    # Each category belongs to one ToM level, so we show categories sorted by level
    cat_stats["tom_label"] = cat_stats["tom_level"].map(TOM_LABELS)
    cat_stats = cat_stats.sort_values(["tom_level", "category"])

    # Create a wide-format matrix: categories × metrics
    fig, ax = plt.subplots(figsize=(10, max(6, len(cat_stats) * 0.4)))

    # Horizontal bar chart (easier to read than heatmap for single-level mapping)
    colors = {0: "#2ca02c", 1: "#1f77b4", 2: "#ff7f0e", 3: "#d62728"}
    bar_colors = [colors.get(row["tom_level"], "#333333") for _, row in cat_stats.iterrows()]

    bars = ax.barh(
        range(len(cat_stats)),
        cat_stats["mean_det"],
        color=bar_colors, edgecolor="white", height=0.7,
    )

    # Labels
    labels = [f"{row['category']} (n={row['n']})" for _, row in cat_stats.iterrows()]
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel("Mean Detection Rate")
    ax.set_title("Detection Rate by MQM Subcategory (colored by ToM Level)")

    # Add value labels on bars
    for i, (_, row) in enumerate(cat_stats.iterrows()):
        ax.text(row["mean_det"] + 0.01, i, f"{row['mean_det']:.3f}", va="center", fontsize=9)

    # Legend
    handles = [mpatches.Patch(color=colors[lv], label=TOM_LABELS[lv]) for lv in sorted(colors.keys())]
    ax.legend(handles=handles, title="ToM Level", loc="lower right")

    ax.set_xlim(0, 1.1)
    ax.invert_yaxis()
    plt.tight_layout()

    path = output_dir / "V2_category_heatmap.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_v3_rater_slopes(
    v4_result: dict,
    output_dir: Path,
) -> Path | None:
    """Figure V3: Forest plot of per-rater ToM slopes from V4 (§7.2)."""
    if v4_result.get("skipped"):
        return None

    slopes = v4_result.get("rater_tom_slopes", {})
    if not slopes:
        return None

    _setup_style()
    fig, ax = plt.subplots(figsize=(6, max(3, len(slopes) * 0.5)))

    raters = sorted(slopes.keys())
    values = [slopes[r] for r in raters]
    y_pos = range(len(raters))

    ax.barh(y_pos, values, color=["#d62728" if v < 0 else "#2ca02c" for v in values],
            edgecolor="white", height=0.6)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(raters)
    ax.set_xlabel("ToM Slope (β)")
    ax.set_title("Per-Rater ToM Sensitivity (V4)")

    for i, v in enumerate(values):
        ax.text(v + 0.002 * np.sign(v), i, f"{v:.4f}", va="center", fontsize=9)

    plt.tight_layout()
    path = output_dir / "V3_rater_slopes.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_sensitivity_summary(
    sensitivity_results: dict,
    output_dir: Path,
) -> Path:
    """Supplementary figure: sensitivity analysis τ_b values."""
    _setup_style()

    # Extract testable results
    items = []
    for sid, r in sensitivity_results.items():
        if sid.startswith("_") or sid == "S8_per_system":
            continue
        if r.get("skipped"):
            continue
        items.append({
            "analysis": sid.replace("_", " "),
            "tau_b": r["tau_b"],
            "significant": r["significant"],
        })

    if not items:
        return None

    fig, ax = plt.subplots(figsize=(8, max(3, len(items) * 0.5)))

    y_pos = range(len(items))
    colors = ["#2ca02c" if it["significant"] else "#999999" for it in items]

    ax.barh(y_pos, [it["tau_b"] for it in items], color=colors, edgecolor="white", height=0.6)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([it["analysis"] for it in items])
    ax.set_xlabel("Kendall τ_b")
    ax.set_title("Sensitivity Analyses: Effect Size")

    handles = [
        mpatches.Patch(color="#2ca02c", label="p < 0.05"),
        mpatches.Patch(color="#999999", label="n.s."),
    ]
    ax.legend(handles=handles, loc="lower right")

    plt.tight_layout()
    path = output_dir / "sensitivity_summary.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path
