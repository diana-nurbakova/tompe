"""Generate all plots for the pipeline validation paper.

Creates matplotlib/seaborn figures for Tracks A, B, and C results.
Saves as both PDF and PNG for LaTeX inclusion.

Usage:
    python -m experiments.pipeline_validation.figures
    python -m experiments.pipeline_validation.figures --results-dir path/to/results
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from experiments.pipeline_validation.config import RESULTS_DIR, TOM_LEVELS, ensure_dirs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Academic style defaults
# ---------------------------------------------------------------------------

matplotlib.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

# Column widths for two-column paper layouts
_SINGLE_COL_WIDTH = 3.5  # inches
_DOUBLE_COL_WIDTH = 7.0  # inches

# ToM level display labels
_TOM_LABELS = {
    "1st_machine": "L0\n(Machine)",
    "1st_author": "L1\n(Author)",
    "2nd_reader": "L2\n(Reader)",
    "recursive": "L3\n(Recursive)",
}

# Colour palette for conditions
_CONDITION_COLOURS = {
    "B0_random": "#d62728",
    "B1_single_step": "#ff7f0e",
    "B2_unconstrained": "#2ca02c",
    "full_pipeline": "#1f77b4",
}


def _save_fig(fig: plt.Figure, output_path: Path) -> None:
    """Save a figure as both PDF and PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path.with_suffix(".pdf"), format="pdf")
    fig.savefig(output_path.with_suffix(".png"), format="png")
    plt.close(fig)
    logger.info("Saved figure: %s (.pdf + .png)", output_path.stem)


# ---------------------------------------------------------------------------
# Track A: Detection by ToM level (A2)
# ---------------------------------------------------------------------------


def plot_detection_by_tom(results: dict, output_path: Path) -> None:
    """Bar chart: GEMBA detection rate by ToM level (A2).

    Args:
        results: GEMBA detection results dict (from a2_gemba_detection.json)
                 with a ``by_tom_level`` key.
        output_path: Base path for the figure (without extension).
    """
    by_tom = results.get("by_tom_level", {})
    if not by_tom:
        logger.warning("No by_tom_level data; skipping detection plot.")
        return

    levels = [lvl for lvl in TOM_LEVELS if lvl in by_tom]
    rates = [by_tom[lvl].get("detection_rate", 0.0) for lvl in levels]
    labels = [_TOM_LABELS.get(lvl, lvl) for lvl in levels]
    counts = [by_tom[lvl].get("total", 0) for lvl in levels]

    fig, ax = plt.subplots(figsize=(_SINGLE_COL_WIDTH, 2.4))
    x = np.arange(len(levels))
    bars = ax.bar(x, rates, width=0.6, color="#1f77b4", edgecolor="white", linewidth=0.5)

    # Annotate bars with rate and count
    for bar, rate, n in zip(bars, rates, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{rate:.0%}\n(n={n})",
            ha="center", va="bottom", fontsize=7,
        )

    # Target line
    target = results.get("target", 0.80)
    ax.axhline(y=target, color="#d62728", linestyle="--", linewidth=0.8, label=f"Target ({target:.0%})")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Detection Rate")
    ax.set_ylim(0, 1.15)
    ax.set_title("GEMBA Detection Rate by ToM Level")
    ax.legend(loc="upper right", frameon=False)

    _save_fig(fig, output_path)


# ---------------------------------------------------------------------------
# Track A: xCOMET score drop (A3)
# ---------------------------------------------------------------------------


def plot_score_drop_by_tom(results: dict, output_path: Path) -> None:
    """Box plot: xCOMET score drop distribution by ToM level (A3).

    Args:
        results: xCOMET scoring results dict (from a3_xcomet_scoring.json)
                 with a ``per_item`` list.
        output_path: Base path for the figure.
    """
    per_item = results.get("per_item", [])
    if not per_item:
        logger.warning("No per_item data; skipping score drop plot.")
        return

    # Group score drops by ToM level
    drops_by_tom: dict[str, list[float]] = {lvl: [] for lvl in TOM_LEVELS}
    for item in per_item:
        tom = item.get("tom_level")
        if tom in drops_by_tom:
            drops_by_tom[tom].append(item.get("score_drop", 0.0))

    levels = [lvl for lvl in TOM_LEVELS if drops_by_tom.get(lvl)]
    data = [drops_by_tom[lvl] for lvl in levels]
    labels = [_TOM_LABELS.get(lvl, lvl) for lvl in levels]

    fig, ax = plt.subplots(figsize=(_SINGLE_COL_WIDTH, 2.4))

    bp = ax.boxplot(
        data,
        labels=labels,
        patch_artist=True,
        widths=0.5,
        medianprops={"color": "black", "linewidth": 1.2},
    )
    for patch in bp["boxes"]:
        patch.set_facecolor("#aec7e8")
        patch.set_edgecolor("#1f77b4")

    ax.set_ylabel("xCOMET Score Drop")
    ax.set_title("Score Degradation by ToM Level")
    ax.axhline(y=0, color="grey", linestyle=":", linewidth=0.5)

    _save_fig(fig, output_path)


# ---------------------------------------------------------------------------
# Track B: Ablation radar chart
# ---------------------------------------------------------------------------


def plot_ablation_radar(results: dict, output_path: Path) -> None:
    """Radar/spider chart comparing 4 conditions on 5 metrics (Track B).

    Args:
        results: Ablation comparison dict (from ablation_results.json)
                 with a ``table`` list of row dicts.
        output_path: Base path for the figure.
    """
    table = results.get("table", [])
    if not table:
        logger.warning("No ablation table data; skipping radar plot.")
        return

    metrics = [
        "structural_pass_rate",
        "gemba_detection_rate",
        "category_fidelity",
        "xcomet_score_drop",
        "text_preservation_rate",
    ]
    metric_labels = [
        "Structural\nPass Rate",
        "GEMBA\nDetection",
        "Category\nFidelity",
        "xCOMET\nScore Drop",
        "Text\nPreservation",
    ]

    # Number of variables
    N = len(metrics)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # close the loop

    fig, ax = plt.subplots(figsize=(_SINGLE_COL_WIDTH, _SINGLE_COL_WIDTH), subplot_kw={"polar": True})

    for row in table:
        condition = row["condition"]
        values = []
        for m in metrics:
            v = row.get(m)
            if v is None:
                v = 0.0
            values.append(float(v))
        values += values[:1]  # close the loop

        colour = _CONDITION_COLOURS.get(condition, "#999999")
        label = condition.replace("_", " ").title()
        ax.plot(angles, values, linewidth=1.2, color=colour, label=label)
        ax.fill(angles, values, alpha=0.08, color=colour)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metric_labels, fontsize=7)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.50, 0.75, 1.00])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=6)
    ax.set_title("Ablation: 4 Conditions on 5 Metrics", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), frameon=False, fontsize=7)

    _save_fig(fig, output_path)


# ---------------------------------------------------------------------------
# Track C: Three-way agreement heatmap
# ---------------------------------------------------------------------------


def plot_three_way_heatmap(results: dict, output_path: Path) -> None:
    """Heatmap: detection agreement matrix by ToM level (Track C).

    Rows are ToM levels, columns are annotator pairs.

    Args:
        results: Three-way agreement results dict
                 (from three_way_agreement.json) with ``agreement_by_tom``.
        output_path: Base path for the figure.
    """
    by_tom = results.get("agreement_by_tom", {})
    if not by_tom:
        logger.warning("No agreement_by_tom data; skipping heatmap.")
        return

    pairs = ["pipeline_human_kappa", "pipeline_gemba_kappa", "human_gemba_kappa"]
    pair_labels = ["Pipeline-Human", "Pipeline-GEMBA", "Human-GEMBA"]

    levels = [lvl for lvl in TOM_LEVELS if lvl in by_tom and by_tom[lvl].get("n_spans", 0) > 0]
    if not levels:
        logger.warning("No ToM levels with data; skipping heatmap.")
        return

    matrix = np.zeros((len(levels), len(pairs)))
    for i, lvl in enumerate(levels):
        for j, pair in enumerate(pairs):
            matrix[i, j] = by_tom[lvl].get(pair, 0.0)

    level_labels = [_TOM_LABELS.get(lvl, lvl).replace("\n", " ") for lvl in levels]

    fig, ax = plt.subplots(figsize=(_SINGLE_COL_WIDTH, 2.0))

    try:
        import seaborn as sns
        sns.heatmap(
            matrix,
            annot=True,
            fmt=".2f",
            xticklabels=pair_labels,
            yticklabels=level_labels,
            cmap="YlOrRd",
            vmin=0, vmax=1,
            linewidths=0.5,
            ax=ax,
        )
    except ImportError:
        # Fallback to plain matplotlib
        im = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(pair_labels)))
        ax.set_xticklabels(pair_labels, fontsize=7)
        ax.set_yticks(range(len(level_labels)))
        ax.set_yticklabels(level_labels, fontsize=7)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=7)
        fig.colorbar(im, ax=ax, shrink=0.8)

    ax.set_title("Cohen's Kappa by ToM Level and Annotator Pair")

    _save_fig(fig, output_path)


# ---------------------------------------------------------------------------
# Track C: Explanation quality
# ---------------------------------------------------------------------------


def plot_explanation_quality(results: dict, output_path: Path) -> None:
    """Grouped bar chart: factual accuracy, clarity, completeness by ToM level.

    Args:
        results: Explanation quality results dict with ``by_tom_level`` key,
                 each containing accuracy, clarity, completeness scores.
        output_path: Base path for the figure.
    """
    by_tom = results.get("by_tom_level", {})
    if not by_tom:
        logger.warning("No explanation quality data; skipping plot.")
        return

    dimensions = ["factual_accuracy", "clarity", "completeness"]
    dim_labels = ["Factual\nAccuracy", "Clarity", "Completeness"]

    levels = [lvl for lvl in TOM_LEVELS if lvl in by_tom]
    if not levels:
        logger.warning("No ToM levels with explanation data; skipping.")
        return

    n_dims = len(dimensions)
    n_levels = len(levels)
    x = np.arange(n_levels)
    width = 0.8 / n_dims

    fig, ax = plt.subplots(figsize=(_SINGLE_COL_WIDTH, 2.4))

    colours = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    for d_idx, (dim, colour) in enumerate(zip(dimensions, colours)):
        values = [by_tom[lvl].get(dim, 0.0) for lvl in levels]
        offset = (d_idx - n_dims / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=dim_labels[d_idx], color=colour, edgecolor="white", linewidth=0.5)

    level_labels = [_TOM_LABELS.get(lvl, lvl) for lvl in levels]
    ax.set_xticks(x)
    ax.set_xticklabels(level_labels)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.1)
    ax.set_title("Explanation Quality by ToM Level")
    ax.legend(frameon=False, loc="upper right")

    _save_fig(fig, output_path)


# ---------------------------------------------------------------------------
# Master generator
# ---------------------------------------------------------------------------


def generate_all_figures(results_dir: Path) -> None:
    """Load results from JSON files and generate all figures.

    Looks for result files in the standard subdirectory structure:
        results_dir/track_a/a2_gemba_detection.json
        results_dir/track_a/a3_xcomet_scoring.json
        results_dir/track_b/ablation_results.json
        results_dir/track_c/three_way_agreement.json
        results_dir/track_c/explanation_quality.json  (if available)

    Saves figures into results_dir/figures/.
    """
    ensure_dirs()
    figures_dir = results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Track A: GEMBA detection by ToM
    gemba_path = results_dir / "track_a" / "a2_gemba_detection.json"
    if gemba_path.exists():
        with open(gemba_path, "r", encoding="utf-8") as f:
            gemba_results = json.load(f)
        plot_detection_by_tom(gemba_results, figures_dir / "fig_detection_by_tom")
    else:
        logger.info("Skipping detection plot: %s not found", gemba_path)

    # Track A: xCOMET score drop by ToM
    xcomet_path = results_dir / "track_a" / "a3_xcomet_scoring.json"
    if xcomet_path.exists():
        with open(xcomet_path, "r", encoding="utf-8") as f:
            xcomet_results = json.load(f)
        plot_score_drop_by_tom(xcomet_results, figures_dir / "fig_score_drop_by_tom")
    else:
        logger.info("Skipping score drop plot: %s not found", xcomet_path)

    # Track B: Ablation radar
    ablation_path = results_dir / "track_b" / "ablation_results.json"
    if ablation_path.exists():
        with open(ablation_path, "r", encoding="utf-8") as f:
            ablation_results = json.load(f)
        plot_ablation_radar(ablation_results, figures_dir / "fig_ablation_radar")
    else:
        logger.info("Skipping ablation radar: %s not found", ablation_path)

    # Track C: Three-way agreement heatmap
    agreement_path = results_dir / "track_c" / "three_way_agreement.json"
    if agreement_path.exists():
        with open(agreement_path, "r", encoding="utf-8") as f:
            agreement_results = json.load(f)
        plot_three_way_heatmap(agreement_results, figures_dir / "fig_three_way_heatmap")
    else:
        logger.info("Skipping agreement heatmap: %s not found", agreement_path)

    # Track C: Explanation quality (optional)
    expl_path = results_dir / "track_c" / "explanation_quality.json"
    if expl_path.exists():
        with open(expl_path, "r", encoding="utf-8") as f:
            expl_results = json.load(f)
        plot_explanation_quality(expl_results, figures_dir / "fig_explanation_quality")
    else:
        logger.info("Skipping explanation quality plot: %s not found", expl_path)

    logger.info("Figure generation complete. Output: %s", figures_dir)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Generate all pipeline validation figures."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_DIR,
        help=f"Results directory (default: {RESULTS_DIR}).",
    )
    args = parser.parse_args()

    generate_all_figures(args.results_dir)
