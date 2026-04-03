"""Visualization module for EC-TEL experiments.

Generates publication-quality figures F4-F6 as specified in §10.2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from .tom_mapping import SKILL_ORDER, SKILL_TO_TOM_RANK, TOM_LEVEL_LABELS

# Consistent styling
COLORS = {
    "low": "#2196F3",   # blue for low-ToM
    "high": "#F44336",  # red for high-ToM
    "neutral": "#9E9E9E",
    "confirm": "#4CAF50",
    "partial": "#FFC107",
    "contradict": "#F44336",
    "nodata": "#EEEEEE",
}

SKILL_COLORS = {
    "S1": "#1565C0", "S2": "#1E88E5",
    "S3": "#7B1FA2",
    "S4": "#C62828", "S5": "#D32F2F", "S6": "#E53935",
    "S7": "#FF6F00",
}


def figure_f4_difficulty_scatter(exp1_results: Dict, output_dir: Path) -> Path:
    """F4: ToM ordering vs published difficulty — scatter plot (Spec §10.2).

    One subplot per source. X = ToM rank, Y = observed difficulty rank.
    Points colored by ToM group (low/high) with a shared legend.
    Each point annotated with the error type name from the source study.
    """
    from .data.published_data import EXP1_SOURCES

    # Build a lookup: source name -> list of error_type labels
    error_labels = {}
    for src_data in EXP1_SOURCES:
        name = src_data["source"]
        error_labels[name] = [m["error_type"] for m in src_data["measures"]]

    sources = exp1_results["per_source"]
    n = len(sources)
    fig, axes = plt.subplots(1, n, figsize=(4.5 * n, 5), sharey=False)
    if n == 1:
        axes = [axes]

    # ToM rank -> readable label for x-axis
    rank_labels = {1: "1\n(S1)", 2: "2\n(S2)", 3: "3\n(S3)",
                   4: "4\n(S4-S6)", 5: "5\n(S7)"}

    for ax, src in zip(axes, sources):
        tom_r = np.array(src["tom_ranks"])
        obs_r = np.array(src["observed_ranks"])
        skills = src["skills"]
        labels = error_labels.get(src["source"], skills)

        # Jitter for overlapping points
        jitter = np.random.default_rng(42).uniform(-0.08, 0.08, len(tom_r))

        for i, (skill, label) in enumerate(zip(skills, labels)):
            from .tom_mapping import is_low_tom
            color = COLORS["low"] if is_low_tom(skill) else COLORS["high"]
            ax.scatter(
                tom_r[i] + jitter[i], obs_r[i],
                c=color, s=90, zorder=3,
                edgecolors="white", linewidths=0.7,
            )
            # Annotate with error type name (shortened if needed)
            short = label if len(label) <= 20 else label[:18] + ".."
            ax.annotate(
                short, (tom_r[i] + jitter[i], obs_r[i]),
                textcoords="offset points", xytext=(6, 6),
                fontsize=6, alpha=0.85,
                arrowprops=dict(arrowstyle="-", alpha=0.3, lw=0.5),
            )

        # Trend line
        if len(tom_r) >= 3:
            z = np.polyfit(tom_r, obs_r, 1)
            x_line = np.linspace(tom_r.min() - 0.3, tom_r.max() + 0.3, 50)
            ax.plot(x_line, np.polyval(z, x_line), "--", color="gray", alpha=0.5)

        tau = src["kendall_tau"]
        p = src["p_value"]
        ax.set_title(f"{src['source']}\n" + r"$\tau$" + f"={tau:.3f}, p={p:.3f}",
                      fontsize=9)
        ax.set_xlabel("ToM Rank", fontsize=8)
        ax.set_ylabel("Observed Difficulty", fontsize=8)
        ax.grid(True, alpha=0.2)

        # Use readable x-tick labels
        unique_ranks = sorted(set(tom_r))
        ax.set_xticks(unique_ranks)
        ax.set_xticklabels([rank_labels.get(int(r), str(int(r))) for r in unique_ranks],
                           fontsize=7)

    # Shared legend
    low_patch = mpatches.Patch(color=COLORS["low"], label="Low-ToM (S1-S2: surface, grammar)")
    high_patch = mpatches.Patch(color=COLORS["high"], label="High-ToM (S3+: meaning, pragmatic, discourse)")
    fig.legend(handles=[low_patch, high_patch], loc="upper center",
               ncol=2, fontsize=9, framealpha=0.9,
               bbox_to_anchor=(0.5, 1.0))

    fig.suptitle("Experiment 1: ToM Ordering vs. Published Difficulty Rankings",
                 fontsize=12, fontweight="bold", y=1.07)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    path = output_dir / "F4_difficulty_scatter.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_f5_fluency_asymmetry(exp2_results: Dict, output_dir: Path) -> Path:
    """F5: Fluency paradox asymmetry — improvement ratio by ToM level (Spec §10.2).

    Bar chart: ToM levels on x-axis, NMT improvement ratio on y-axis.
    One cluster per study.
    """
    sources = exp2_results["per_source"]
    fig, ax = plt.subplots(figsize=(10, 5))

    bar_width = 0.18
    x_positions = np.arange(len(sources))

    for i, src in enumerate(sources):
        per_type = src.get("per_type", [])
        if not per_type:
            continue

        # Group by tom_group
        low_vals, high_vals = [], []
        for m in per_type:
            group = m.get("tom_group", "high")
            # Get the improvement/asymmetry value
            if "improvement_ratio" in m:
                val = m["improvement_ratio"]
            elif "drop" in m:
                val = -m["drop"]  # negative drop = improvement
            elif "nmt_reduction_pct" in m:
                val = m["nmt_reduction_pct"] / 100
            else:
                continue

            if group == "low":
                low_vals.append(val)
            else:
                high_vals.append(val)

        low_mean = np.mean(low_vals) if low_vals else 0
        high_mean = np.mean(high_vals) if high_vals else 0

        ax.bar(i - bar_width / 2, low_mean, bar_width,
               color=COLORS["low"], label="Low-ToM (S1-S2)" if i == 0 else "",
               edgecolor="white")
        ax.bar(i + bar_width / 2, high_mean, bar_width,
               color=COLORS["high"], label="High-ToM (S3+)" if i == 0 else "",
               edgecolor="white")

    ax.set_xticks(x_positions)
    ax.set_xticklabels([s["source"] for s in sources], fontsize=8)
    ax.set_ylabel("NMT Improvement Ratio")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.2)
    ax.set_title("Experiment 2: Fluency Paradox — NMT Improvement by ToM Level",
                 fontsize=12, fontweight="bold")

    fig.tight_layout()
    path = output_dir / "F5_fluency_asymmetry.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_f6_convergence_heatmap(exp5_results: Dict, output_dir: Path) -> Path:
    """F6: Convergence heatmap (Spec §10.2).

    Rows = skills (S1-S7), Columns = experiments (Exp 1-4).
    Color = strength of evidence (count of align verdicts).
    """
    table = exp5_results["table"]
    skills = SKILL_ORDER
    exp_names = ["Exp 1\nDifficulty", "Exp 2\nFluency\nParadox",
                 "Exp 3\nExpert-\nNovice", "Exp 4\nOver-\nEditing"]
    exp_keys = ["exp1_cells", "exp2_cells", "exp3_cells", "exp4_cells"]

    # Build matrix: count of V, ~, X per cell
    matrix = np.zeros((len(skills), len(exp_keys)))
    annotations = []

    for i, skill in enumerate(skills):
        row_annot = []
        for j, key in enumerate(exp_keys):
            cells = table[skill][key]
            n_align = sum(1 for c in cells if c["verdict"] == "V")
            n_partial = sum(1 for c in cells if c["verdict"] == "~")
            n_contra = sum(1 for c in cells if c["verdict"] == "X")
            n_data = n_align + n_partial + n_contra

            if n_data == 0:
                matrix[i, j] = -0.5  # no data
                row_annot.append("-")
            else:
                # Score: +1 for align, +0.5 for partial, -1 for contradict
                score = (n_align + 0.5 * n_partial - n_contra) / max(n_data, 1)
                matrix[i, j] = score
                parts = []
                if n_align > 0:
                    parts.append(f"{n_align}V")
                if n_partial > 0:
                    parts.append(f"{n_partial}~")
                if n_contra > 0:
                    parts.append(f"{n_contra}X")
                row_annot.append(" ".join(parts))
        annotations.append(row_annot)

    fig, ax = plt.subplots(figsize=(8, 6))

    # Custom colormap: red (contradict) → white (no data) → green (align)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "convergence",
        [(0.0, "#D32F2F"), (0.3, "#FFCDD2"), (0.5, "#F5F5F5"),
         (0.7, "#C8E6C9"), (1.0, "#388E3C")],
    )

    im = ax.imshow(matrix, cmap=cmap, vmin=-1, vmax=1, aspect="auto")

    # Annotate cells
    for i in range(len(skills)):
        for j in range(len(exp_keys)):
            text = annotations[i][j]
            color = "white" if abs(matrix[i, j]) > 0.7 else "black"
            ax.text(j, i, text, ha="center", va="center",
                    fontsize=8, color=color, fontweight="bold")

    ax.set_xticks(range(len(exp_names)))
    ax.set_xticklabels(exp_names, fontsize=9)
    SKILL_LONG_LABELS = {
        "S1": "S1 Surface",
        "S2": "S2 Grammar",
        "S3": "S3 Meaning",
        "S4": "S4 Completeness",
        "S5": "S5 Terminology",
        "S6": "S6 Pragmatic",
        "S7": "S7 Discourse",
    }
    ax.set_yticks(range(len(skills)))
    ax.set_yticklabels(
        [f"{SKILL_LONG_LABELS[s]}  (ToM {SKILL_TO_TOM_RANK[s]})" for s in skills],
        fontsize=9,
    )
    ax.set_title("Experiment 5: Convergence Heatmap — ToM Framework Validation",
                 fontsize=12, fontweight="bold", pad=15)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Evidence Score", fontsize=9)

    # Add aggregate stats as text
    agg = exp5_results["aggregate"]
    stats_text = (f"Convergence: {agg['convergence_ratio']:.0%}  "
                  f"({agg['n_align']}V / {agg['n_align'] + agg['n_contradict']})")
    fig.tight_layout()

    # Place stats box below the figure, after tight_layout to avoid overlap
    fig.text(0.45, -0.04, stats_text,
             ha="center", fontsize=10, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8F5E9", alpha=0.8))
    path = output_dir / "F6_convergence_heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_exp4_overediting_bars(exp4_results: Dict, output_dir: Path) -> Path:
    """Stacked bar chart for Exp 4: unnecessary vs necessary by ToM level."""
    sources_with_data = [
        s for s in exp4_results["per_source"]
        if s.get("per_type") and len(s["per_type"]) > 0
    ]

    if not sources_with_data:
        return None

    fig, axes = plt.subplots(1, len(sources_with_data),
                              figsize=(5 * len(sources_with_data), 4))
    if len(sources_with_data) == 1:
        axes = [axes]

    for ax, src in zip(axes, sources_with_data):
        per_type = src["per_type"]
        labels = [m.get("error_type", m.get("edit_type", "?")) for m in per_type]
        pcts = [m.get("pct_of_unnecessary", m.get("pct_unnecessary", m.get("pct_of_preferential", 0)))
                for m in per_type]
        groups = [m.get("tom_group", "high") for m in per_type]
        colors = [COLORS["low"] if g == "low" else COLORS["high"] for g in groups]

        x = np.arange(len(labels))
        ax.bar(x, pcts, color=colors, edgecolor="white")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Unnecessary Edit Proportion")
        ax.set_title(src["source"], fontsize=10)
        ax.grid(True, axis="y", alpha=0.2)

    # Legend (shared across subplots)
    low_patch = mpatches.Patch(color=COLORS["low"], label="Low-ToM (S1-S2)")
    high_patch = mpatches.Patch(color=COLORS["high"], label="High-ToM (S3+)")
    fig.legend(handles=[low_patch, high_patch], loc="upper right",
               fontsize=9, framealpha=0.9)

    fig.suptitle("Experiment 4: Over-Editing Concentration by ToM Level",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 0.92, 1])

    path = output_dir / "F_exp4_overediting.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def figure_exp3b_learning_curves(exp3b_results: dict, output_dir: Path) -> Path:
    """Learning curves by ToM level for Exp 3b (developmental gradient).

    Left panel: learning curves (performance over sessions) per error type.
    Right panel: phase improvement bar chart (early vs late by ToM level).
    """
    # Find the longitudinal source (Koponen2015)
    longitudinal = None
    for src in exp3b_results["per_source"]:
        if src["source"] == "Koponen2015":
            longitudinal = src
            break

    if not longitudinal:
        return None

    per_type = longitudinal["per_type"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # ── Left panel: Learning curves ──
    for entry in per_type:
        skill = entry["skill"]
        perf = entry["performance_by_session"]
        sessions = list(range(1, len(perf) + 1))
        color = SKILL_COLORS.get(skill, "#666666")
        label = f"{skill} {entry['error_type']}"
        ax1.plot(sessions, perf, "o-", color=color, label=label,
                 linewidth=2, markersize=5)

    # Mastery threshold line
    ax1.axhline(0.80, color="gray", linestyle="--", alpha=0.5, linewidth=1)
    ax1.text(0.6, 0.81, "Mastery threshold (0.80)", fontsize=7, color="gray",
             alpha=0.7)

    ax1.set_xlabel("Training Session", fontsize=10)
    ax1.set_ylabel("Correct Edit Rate", fontsize=10)
    ax1.set_title("Learning Curves by Error Type", fontsize=11, fontweight="bold")
    ax1.legend(fontsize=7, loc="lower right")
    ax1.grid(True, alpha=0.2)
    ax1.set_ylim(0.15, 1.0)
    ax1.set_xticks(range(1, longitudinal["n_sessions"] + 1))

    # ── Right panel: Phase improvement bar chart ──
    skills = [e["skill"] for e in per_type]
    labels = [f"{e['skill']}\n{e['error_type'][:12]}" for e in per_type]
    early_imps = [e["phases"]["early_improvement"] for e in per_type]
    late_imps = [e["phases"]["late_improvement"] for e in per_type]

    x = np.arange(len(skills))
    width = 0.35

    ax2.bar(x - width / 2, early_imps, width, label="Early improvement",
            color=COLORS["low"], edgecolor="white")
    ax2.bar(x + width / 2, late_imps, width, label="Late improvement",
            color=COLORS["high"], edgecolor="white")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=8)
    ax2.set_ylabel("Improvement Magnitude", fontsize=10)
    ax2.set_title("Phase Improvement by Error Type", fontsize=11, fontweight="bold")
    ax2.legend(fontsize=8)
    ax2.grid(True, axis="y", alpha=0.2)

    # Add tau annotation
    methods = longitudinal["methods"]
    tau_a = methods["A_mastery_session"]["kendall_tau"]
    p_a = methods["A_mastery_session"]["p_value"]
    fig.suptitle(
        "Experiment 3b: Developmental ToM Gradient — "
        r"Mastery ordering $\tau$" + f"={tau_a:.3f}, p={p_a:.3f}",
        fontsize=13, fontweight="bold", y=1.02,
    )

    fig.tight_layout()
    path = output_dir / "F_exp3b_developmental.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
