"""Figure generation for Wasserstein experiments (F1–F12).

Generates all figures from spec §7.1.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from .config import ARCHETYPES, N_SKILLS, SKILL_LABELS, SKILL_NAMES, TARGET_PROFILE
from .ground_metrics import METRIC_BUILDERS, build_all_metrics
from .metrics import (
    mastery_gap,
    pairwise_distances,
    profile_to_array,
    w1_balanced,
    w1_balanced_with_plan,
)
from .synthetic_trajectories import StudentTrajectory

logger = logging.getLogger(__name__)

# Color palette per archetype
ARCHETYPE_COLORS = {
    "coherent": "#2196F3",
    "scattered": "#FF9800",
    "fast_plateau": "#4CAF50",
    "slow_steady": "#9C27B0",
    "surface_only": "#F44336",
}

ARCHETYPE_SHORT = {
    "coherent": "Coherent",
    "scattered": "Scattered",
    "fast_plateau": "Fast/Plateau",
    "slow_steady": "Slow Steady",
    "surface_only": "Surface-Only",
}


def _setup_style():
    sns.set_theme(style="whitegrid", font_scale=1.1)
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["savefig.bbox"] = "tight"


def _ensure_dir(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)


# =============================================================================
# F1: Radar charts — 5 archetypes at session 1 and session 10
# =============================================================================

def figure_f1_radar_charts(
    students: list[StudentTrajectory],
    output_dir: Path,
):
    """Radar charts showing archetype profiles at session 1 and 10."""
    _setup_style()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), subplot_kw={"polar": True})
    angles = np.linspace(0, 2 * np.pi, N_SKILLS, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon
    labels = [SKILL_NAMES[sk] for sk in SKILL_LABELS]

    for ax, session_idx, title in [
        (axes[0], 0, "Session 1"),
        (axes[1], -1, "Session 10"),
    ]:
        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_thetagrids(
            np.degrees(angles[:-1]), labels, fontsize=9
        )

        # Plot one line per archetype (averaged across instances)
        for archetype_key in ARCHETYPES:
            instances = [
                s for s in students if s.archetype == archetype_key
            ]
            if not instances:
                continue
            avg = np.mean(
                [profile_to_array(s.profiles[session_idx]) for s in instances],
                axis=0,
            )
            vals = avg.tolist() + [avg[0]]
            ax.plot(
                angles, vals,
                label=ARCHETYPE_SHORT[archetype_key],
                color=ARCHETYPE_COLORS[archetype_key],
                linewidth=2,
            )
            ax.fill(angles, vals, alpha=0.1, color=ARCHETYPE_COLORS[archetype_key])

        # Target profile
        tgt = profile_to_array(TARGET_PROFILE)
        tgt_vals = tgt.tolist() + [tgt[0]]
        ax.plot(
            angles, tgt_vals,
            "--", color="black", linewidth=1.5, label="Target", alpha=0.6,
        )
        ax.set_ylim(0, 1.0)
        ax.set_title(title, fontsize=13, pad=15)

    axes[1].legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9)
    fig.suptitle("Student Archetype Profiles", fontsize=14, y=1.02)
    fig.savefig(output_dir / "F1_radar_charts.png")
    plt.close(fig)
    logger.info("Saved F1_radar_charts.png")


# =============================================================================
# F2: MasteryGap trajectory plot
# =============================================================================

def figure_f2_mastery_gap_trajectories(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
    output_dir: Path,
):
    """Line plot: MasteryGap over sessions, colored by archetype."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(10, 6))
    target = profile_to_array(TARGET_PROFILE)

    for student in students:
        gaps = [
            mastery_gap(p, cost_matrix, target) for p in student.profiles
        ]
        ax.plot(
            range(1, len(gaps) + 1), gaps,
            color=ARCHETYPE_COLORS[student.archetype],
            alpha=0.6,
            linewidth=1.5,
        )

    # Legend: one entry per archetype
    for arch_key, color in ARCHETYPE_COLORS.items():
        ax.plot([], [], color=color, linewidth=2, label=ARCHETYPE_SHORT[arch_key])

    ax.set_xlabel("Session")
    ax.set_ylabel("MasteryGap (W₁ to target)")
    ax.set_title("MasteryGap Trajectories by Archetype")
    ax.legend(loc="upper right")
    fig.savefig(output_dir / "F2_mastery_gap_trajectories.png")
    plt.close(fig)
    logger.info("Saved F2_mastery_gap_trajectories.png")


# =============================================================================
# F3: Fisher ratio bar chart across ground metrics
# =============================================================================

def figure_f3_fisher_ratios(
    b1_results: dict[str, dict],
    output_dir: Path,
):
    """Bar chart: Fisher discriminant ratio for each ground metric + baselines."""
    _setup_style()

    # Select structured metrics + baselines (including new Manhattan & JSD)
    display_order = [
        "euclidean", "manhattan", "cosine", "jsd",
        "M1_trivial", "M5_linear", "M2_graph", "M3_weighted", "M4_2d",
    ]
    display_labels = [
        "Euclidean", "Manhattan", "Cosine", "JSD",
        "M1 Trivial", "M5 Linear", "M2 Graph", "M3 Weighted", "M4 2D",
    ]
    ratios = [b1_results.get(k, {}).get("fisher_ratio", 0) for k in display_order]

    colors = [
        "#FF9800", "#FFC107", "#FF5722", "#E91E63",  # baselines
        "#ccc", "#aaa", "#2196F3", "#1976D2", "#0D47A1",  # OT metrics
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(display_labels, ratios, color=colors, edgecolor="white")
    ax.set_ylabel("Fisher Discriminant Ratio")
    ax.set_title("Archetype Discrimination by Ground Metric")
    ax.set_xticklabels(display_labels, rotation=30, ha="right")

    for bar, val in zip(bars, ratios):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
            f"{val:.2f}", ha="center", va="bottom", fontsize=9,
        )

    fig.savefig(output_dir / "F3_fisher_ratios.png")
    plt.close(fig)
    logger.info("Saved F3_fisher_ratios.png")


# =============================================================================
# F4: Pairwise W₁ heatmap at session 10
# =============================================================================

def figure_f4_pairwise_heatmap(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
    output_dir: Path,
):
    """Heatmap of pairwise W₁ between all 20 students at final session."""
    _setup_style()
    profiles = [s.profiles[-1] for s in students]
    D = pairwise_distances(profiles, cost_matrix)

    labels = [
        f"{ARCHETYPE_SHORT[s.archetype][:3]}{s.student_id.split('_')[-1]}"
        for s in students
    ]

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(
        D, xticklabels=labels, yticklabels=labels,
        cmap="YlOrRd", ax=ax, square=True,
        cbar_kws={"label": "W₁ Distance"},
    )
    ax.set_title("Pairwise W₁ Distance (Session 10, M2 Graph)")
    fig.savefig(output_dir / "F4_pairwise_heatmap.png")
    plt.close(fig)
    logger.info("Saved F4_pairwise_heatmap.png")


# =============================================================================
# F5: Ground metric sensitivity heatmap
# =============================================================================

def figure_f5_sensitivity_heatmap(
    effect_matrix: dict[str, dict[str, float]],
    output_dir: Path,
):
    """Heatmap: ground metrics (rows) × analyses (columns) × effect sizes."""
    _setup_style()

    metric_order = ["M1_trivial", "M5_linear", "M2_graph", "M3_weighted", "M4_2d"]
    analysis_order = ["B1_fisher", "B2_kruskal_H", "B3_anova_F"]

    data = np.zeros((len(metric_order), len(analysis_order)))
    for i, mn in enumerate(metric_order):
        for j, an in enumerate(analysis_order):
            data[i, j] = effect_matrix.get(mn, {}).get(an, 0)

    # Normalize columns for comparability
    for j in range(data.shape[1]):
        col_max = data[:, j].max()
        if col_max > 0:
            data[:, j] /= col_max

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(
        data,
        xticklabels=["B1: Fisher", "B2: Kruskal-H", "B3: ANOVA-F"],
        yticklabels=["M1 Trivial", "M5 Linear", "M2 Graph", "M3 Weighted", "M4 2D"],
        cmap="YlGnBu", annot=True, fmt=".2f", ax=ax,
        cbar_kws={"label": "Normalized Effect Size"},
    )
    ax.set_title("Ground Metric Sensitivity (Normalized)")
    fig.savefig(output_dir / "F5_sensitivity_heatmap.png")
    plt.close(fig)
    logger.info("Saved F5_sensitivity_heatmap.png")


# =============================================================================
# F8: Transport plan visualization
# =============================================================================

def figure_f8_transport_plan(
    student_profile: dict[str, float],
    cost_matrix: np.ndarray,
    output_dir: Path,
    student_label: str = "Student",
):
    """Visualize what mass moves where from student to target."""
    _setup_style()
    target = profile_to_array(TARGET_PROFILE)
    dist, plan = w1_balanced_with_plan(student_profile, target, cost_matrix)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Left: transport plan matrix
    sns.heatmap(
        plan, ax=ax1,
        xticklabels=[SKILL_NAMES[sk] for sk in SKILL_LABELS],
        yticklabels=[SKILL_NAMES[sk] for sk in SKILL_LABELS],
        cmap="Blues", annot=True, fmt=".3f",
        cbar_kws={"label": "Transport Mass"},
    )
    ax1.set_xlabel("Target Skills")
    ax1.set_ylabel(f"{student_label} Skills")
    ax1.set_title(f"Transport Plan (W₁ = {dist:.4f})")

    # Right: bar chart comparison
    student_arr = profile_to_array(student_profile)
    from .metrics import normalize
    student_norm = normalize(student_arr)
    target_norm = normalize(target)
    x = np.arange(N_SKILLS)
    width = 0.35
    ax2.bar(x - width / 2, student_norm, width, label=student_label, color="#2196F3")
    ax2.bar(x + width / 2, target_norm, width, label="Target", color="#4CAF50")
    ax2.set_xticks(x)
    ax2.set_xticklabels([SKILL_NAMES[sk] for sk in SKILL_LABELS], rotation=30, ha="right")
    ax2.set_ylabel("Normalized Mass")
    ax2.set_title("Profile Comparison")
    ax2.legend()

    fig.suptitle(f"Optimal Transport: {student_label} → Target", fontsize=13)
    fig.savefig(output_dir / f"F8_transport_plan_{student_label.lower().replace(' ', '_')}.png")
    plt.close(fig)
    logger.info("Saved F8_transport_plan.png")


# =============================================================================
# F9: Ground metric matrices side by side
# =============================================================================

def figure_f9_ground_metrics(output_dir: Path):
    """Visualize all 5 ground metric matrices as heatmaps."""
    _setup_style()
    metrics = {name: builder() for name, builder in METRIC_BUILDERS.items()}
    labels = [SKILL_NAMES[sk] for sk in SKILL_LABELS]

    fig, axes = plt.subplots(1, 5, figsize=(25, 4))
    titles = ["M1: Trivial", "M2: Graph", "M3: Weighted", "M4: 2D", "M5: Linear"]

    for ax, (name, M), title in zip(axes, metrics.items(), titles):
        sns.heatmap(
            M, ax=ax, xticklabels=labels, yticklabels=labels,
            cmap="viridis", annot=True, fmt=".2f",
            square=True, cbar=False, vmin=0, vmax=1,
        )
        ax.set_title(title, fontsize=11)
        ax.tick_params(axis="both", labelsize=7)

    fig.suptitle("Ground Metric Matrices (Normalized)", fontsize=14, y=1.05)
    fig.savefig(output_dir / "F9_ground_metrics.png")
    plt.close(fig)
    logger.info("Saved F9_ground_metrics.png")


# =============================================================================
# F10: Balanced vs unbalanced for Slow Steady archetype
# =============================================================================

def figure_f10_balanced_vs_unbalanced(
    b7_results: dict,
    output_dir: Path,
):
    """MasteryGap trajectories under balanced vs unbalanced for Slow Steady."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    for reg_key, data in b7_results.items():
        students = data.get("students", {})
        # Find slow_steady students
        for sid, sdata in students.items():
            if sdata["archetype"] != "slow_steady":
                continue
            sessions = range(1, len(sdata["balanced_gaps"]) + 1)
            if sid == "slow_steady_0":
                ax.plot(
                    sessions, sdata["balanced_gaps"],
                    "b-", linewidth=2, label=f"Balanced ({sid})",
                )
                ax.plot(
                    sessions, sdata["unbalanced_gaps"],
                    "r--", linewidth=2, label=f"Unbalanced {reg_key} ({sid})",
                )
            break  # Only first instance per reg_m

    ax.set_xlabel("Session")
    ax.set_ylabel("MasteryGap")
    ax.set_title("Balanced vs Unbalanced OT: Slow Steady Archetype")
    ax.legend()
    fig.savefig(output_dir / "F10_balanced_vs_unbalanced.png")
    plt.close(fig)
    logger.info("Saved F10_balanced_vs_unbalanced.png")


# =============================================================================
# F11: 2D embedding space with trajectory arrows
# =============================================================================

def figure_f11_embedding_space(
    students: list[StudentTrajectory],
    output_dir: Path,
):
    """Skills as points in 2D space, student trajectory arrows."""
    from .config import EMBEDDING_2D

    _setup_style()
    fig, ax = plt.subplots(figsize=(8, 8))

    # Plot skill nodes
    for i, sk in enumerate(SKILL_LABELS):
        ax.scatter(
            EMBEDDING_2D[i, 0], EMBEDDING_2D[i, 1],
            s=200, zorder=5, color="#333",
        )
        ax.annotate(
            f"{sk}\n{SKILL_NAMES[sk]}",
            (EMBEDDING_2D[i, 0], EMBEDDING_2D[i, 1]),
            textcoords="offset points", xytext=(10, 5),
            fontsize=9, fontweight="bold",
        )

    # Plot edges from adjacency
    from .config import ADJACENCY
    for i in range(N_SKILLS):
        for j in range(i + 1, N_SKILLS):
            if ADJACENCY[i, j]:
                ax.plot(
                    [EMBEDDING_2D[i, 0], EMBEDDING_2D[j, 0]],
                    [EMBEDDING_2D[i, 1], EMBEDDING_2D[j, 1]],
                    "k-", alpha=0.3, linewidth=1,
                )

    ax.set_xlabel("Linguistic Grain (scope)")
    ax.set_ylabel("ToM Level (cognitive depth)")
    ax.set_title("Skill Embedding: ToM Level × Linguistic Grain")
    ax.set_xlim(0, 5)
    ax.set_ylim(0, 5)
    fig.savefig(output_dir / "F11_embedding_space.png")
    plt.close(fig)
    logger.info("Saved F11_embedding_space.png")


# =============================================================================
# F12: Permutation null distribution + observed effect sizes
# =============================================================================

def figure_f12_permutation_null(
    b5_results: dict,
    output_dir: Path,
):
    """Observed M2/M3/M4 effect sizes vs random metric null distribution."""
    _setup_style()
    effect_matrix = b5_results.get("effect_matrix", {})

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    analyses = ["B1_fisher", "B2_kruskal_H", "B3_anova_F"]
    titles = ["B1: Fisher Ratio", "B2: Kruskal-Wallis H", "B3: ANOVA F"]

    for ax, analysis, title in zip(axes, analyses, titles):
        # Random null distribution
        rand_vals = [
            effect_matrix.get(k, {}).get(analysis, 0)
            for k in effect_matrix
            if k.startswith("M_rand_")
        ]
        if rand_vals:
            ax.hist(rand_vals, bins=8, alpha=0.5, color="gray", label="Random (null)")

        # Observed structured metrics
        for metric, color, label in [
            ("M2_graph", "#2196F3", "M2 Graph"),
            ("M3_weighted", "#1976D2", "M3 Weighted"),
            ("M4_2d", "#0D47A1", "M4 2D"),
        ]:
            val = effect_matrix.get(metric, {}).get(analysis, 0)
            ax.axvline(val, color=color, linewidth=2, linestyle="--", label=label)

        ax.set_title(title)
        ax.set_xlabel("Effect Size")
        ax.legend(fontsize=8)

    fig.suptitle("Observed vs. Permutation Null Effect Sizes", fontsize=13)
    fig.savefig(output_dir / "F12_permutation_null.png")
    plt.close(fig)
    logger.info("Saved F12_permutation_null.png")


# =============================================================================
# Generate all figures
# =============================================================================

def generate_all_figures(
    students: list[StudentTrajectory],
    cost_matrix: np.ndarray,
    b1_results: dict,
    b5_results: dict,
    b7_results: dict,
    output_dir: str | Path = "outputs/wasserstein/figures",
):
    """Generate all figures F1–F12 (excluding Track A-specific ones)."""
    output_dir = Path(output_dir)
    _ensure_dir(output_dir)

    figure_f1_radar_charts(students, output_dir)
    figure_f2_mastery_gap_trajectories(students, cost_matrix, output_dir)
    figure_f3_fisher_ratios(b1_results, output_dir)
    figure_f4_pairwise_heatmap(students, cost_matrix, output_dir)

    if "effect_matrix" in b5_results:
        figure_f5_sensitivity_heatmap(b5_results["effect_matrix"], output_dir)

    # F8: Transport plan for first coherent and first scattered student
    for student in students:
        if student.archetype == "coherent":
            figure_f8_transport_plan(
                student.profiles[-1], cost_matrix, output_dir,
                student_label="Coherent Learner",
            )
            break

    for student in students:
        if student.archetype == "scattered":
            figure_f8_transport_plan(
                student.profiles[-1], cost_matrix, output_dir,
                student_label="Scattered Learner",
            )
            break

    figure_f9_ground_metrics(output_dir)
    figure_f10_balanced_vs_unbalanced(b7_results, output_dir)
    figure_f11_embedding_space(students, output_dir)
    figure_f12_permutation_null(b5_results, output_dir)

    logger.info("All figures saved to %s", output_dir)
