"""Full Wasserstein experiment pipeline: data → analysis → figures → tables.

Usage:
    python -m experiments.wasserstein.run_all [--track a|b|both] [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from .analysis import run_track_b
from .config import ARCHETYPES, N_SESSIONS, NOISE_STD
from .ground_metrics import METRIC_BUILDERS, build_all_metrics
from .synthetic_trajectories import generate_all_students
from .visualizations import generate_all_figures

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, complex):
            return float(np.real(obj))
        return super().default(obj)


def save_results(results: dict, path: Path):
    """Save results dict to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    logger.info("Results saved to %s", path)


def generate_tables(results: dict, output_dir: Path):
    """Generate LaTeX table snippets from results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # T1: Ground metric matrices
    metrics = {name: builder() for name, builder in METRIC_BUILDERS.items()}
    lines = [
        r"\begin{table}[htbp]",
        r"\caption{Ground Metric Matrices (M1--M5)}",
        r"\label{tab:ground-metrics}",
    ]
    for name, M in metrics.items():
        lines.append(f"\n% {name}")
        lines.append(r"\begin{equation}")
        lines.append(f"D_{{{name}}} = " + _matrix_to_latex(M))
        lines.append(r"\end{equation}")
    lines.append(r"\end{table}")

    with open(output_dir / "T1_ground_metrics.tex", "w") as f:
        f.write("\n".join(lines))

    # T2: Archetype parameters
    lines = [
        r"\begin{table}[htbp]",
        r"\caption{Synthetic Student Archetype Parameters}",
        r"\label{tab:archetypes}",
        r"\begin{tabular}{lllr}",
        r"\toprule",
        r"Key & Name & Description & Instances \\",
        r"\midrule",
    ]
    for key, cfg in ARCHETYPES.items():
        lines.append(
            f"{key} & {cfg['name']} & {cfg['description']} & {cfg['n_instances']} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])

    with open(output_dir / "T2_archetypes.tex", "w") as f:
        f.write("\n".join(lines))

    logger.info("LaTeX tables saved to %s", output_dir)


def _matrix_to_latex(M: np.ndarray) -> str:
    """Convert numpy matrix to LaTeX pmatrix."""
    rows = []
    for row in M:
        rows.append(" & ".join(f"{v:.2f}" for v in row))
    return r"\begin{pmatrix}" + r" \\ ".join(rows) + r"\end{pmatrix}"


def run_pipeline(
    track: str = "both",
    output_dir: str = "outputs/wasserstein",
    n_sessions: int = N_SESSIONS,
    noise_std: float = NOISE_STD,
    seed: int = 42,
):
    """Execute the full experiment pipeline."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_results = {}

    # =========================================================================
    # Track A: WMT MQM Analysis
    # =========================================================================
    if track in ("a", "both"):
        logger.info("=" * 60)
        logger.info("TRACK A: WMT MQM Annotator Analysis")
        logger.info("=" * 60)
        try:
            from .wmt_analysis import run_track_a

            track_a_results = run_track_a(year=2020, lp="en-de")
            all_results["track_a"] = track_a_results
            save_results(track_a_results, output_path / "track_a_results.json")
        except ImportError as e:
            logger.warning(
                "Track A requires 'datasets' package. Install with: "
                "pip install 'tompe[experiments]'. Error: %s", e
            )
        except Exception as e:
            logger.error("Track A failed: %s", e, exc_info=True)

    # =========================================================================
    # Track B: Synthetic Trajectories
    # =========================================================================
    if track in ("b", "both"):
        logger.info("=" * 60)
        logger.info("TRACK B: Synthetic Trajectory Analysis")
        logger.info("=" * 60)

        track_b_results = run_track_b(n_sessions, noise_std, seed)
        all_results["track_b"] = track_b_results
        save_results(track_b_results, output_path / "track_b_results.json")

        # Generate figures
        logger.info("Generating figures...")
        students = generate_all_students(n_sessions, noise_std, seed)
        ground_metrics = build_all_metrics()
        primary_metric = ground_metrics["M2_graph"]

        generate_all_figures(
            students=students,
            cost_matrix=primary_metric,
            b1_results=track_b_results["B1_archetype_discrimination"],
            b5_results=track_b_results["B5_ground_metric_sensitivity"],
            b7_results=track_b_results["B7_balanced_vs_unbalanced"],
            output_dir=output_path / "figures",
        )

        # Generate tables
        generate_tables(track_b_results, output_path / "tables")

    # =========================================================================
    # Combined results
    # =========================================================================
    save_results(all_results, output_path / "all_results.json")

    logger.info("=" * 60)
    logger.info("Pipeline complete. Results in: %s", output_path)
    logger.info("=" * 60)

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="Run Wasserstein distance experiments"
    )
    parser.add_argument(
        "--track", choices=["a", "b", "both"], default="both",
        help="Which track to run (default: both)",
    )
    parser.add_argument(
        "--output-dir", default="outputs/wasserstein",
        help="Output directory (default: outputs/wasserstein)",
    )
    parser.add_argument("--sessions", type=int, default=N_SESSIONS)
    parser.add_argument("--noise", type=float, default=NOISE_STD)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    run_pipeline(
        track=args.track,
        output_dir=args.output_dir,
        n_sessions=args.sessions,
        noise_std=args.noise,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
