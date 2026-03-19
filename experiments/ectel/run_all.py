"""EC-TEL 2026 Experiment Orchestrator.

Runs all 5 retroactive validation experiments and produces:
- JSON results (per-experiment + combined)
- Publication-quality figures (F4, F5, F6 + supplementary)
- LaTeX convergence table
- Console summary

Usage:
    python -m experiments.ectel.run_all                    # full run
    python -m experiments.ectel.run_all --exclude Temnikova2010  # exclude a source
    python -m experiments.ectel.run_all --exclude Temnikova2010 --tag no_temnikova
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ectel.data.published_data import (
    EXP1_SOURCES, EXP2_SOURCES, EXP3_SOURCES, EXP4_SOURCES,
)
from experiments.ectel import exp1_difficulty_ordering as exp1
from experiments.ectel import exp2_fluency_paradox as exp2
from experiments.ectel import exp3_experience_interaction as exp3
from experiments.ectel import exp4_overediting as exp4
from experiments.ectel import exp5_convergence as exp5
from experiments.ectel import visualizations as viz


BASE_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ectel"


def filter_sources(sources: list, exclude: list[str]) -> list:
    """Remove sources whose 'source' field matches any name in exclude."""
    if not exclude:
        return sources
    return [s for s in sources if s["source"] not in exclude]


def generate_latex_convergence(exp5_results: dict, output_dir: Path) -> Path:
    """Generate LaTeX table for the convergence heatmap."""
    table = exp5_results["table"]
    agg = exp5_results["aggregate"]

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Convergence table: ToM framework predictions vs.\ published findings. "
        r"\checkmark{} = aligns, $\sim$ = partially aligns, \texttimes{} = contradicts, "
        r"--- = no data.}",
        r"\label{tab:convergence}",
        r"\begin{tabular}{llcccc}",
        r"\toprule",
        r"Skill & ToM & Exp~1 & Exp~2 & Exp~3 & Exp~4 \\",
        r"      &     & Difficulty & Fluency & Expert-- & Over- \\",
        r"      &     & ordering & paradox & novice & editing \\",
        r"\midrule",
    ]

    from .tom_mapping import SKILL_ORDER, SKILL_TO_TOM_RANK

    for skill in SKILL_ORDER:
        row = table[skill]
        tom = SKILL_TO_TOM_RANK[skill]
        cells = []
        for key in ["exp1_cells", "exp2_cells", "exp3_cells", "exp4_cells"]:
            verdicts = row[key]
            parts = []
            for c in verdicts:
                v = c["verdict"]
                s = c["src"]
                if v == "V":
                    parts.append(rf"{s}\checkmark{{}}")
                elif v == "~":
                    parts.append(rf"{s}$\sim$")
                elif v == "X":
                    parts.append(rf"{s}\texttimes{{}}")
            cell = " ".join(parts) if parts else "---"
            cells.append(cell)

        lines.append(
            rf"{skill} & {tom} & {cells[0]} & {cells[1]} & {cells[2]} & {cells[3]} \\"
        )

    lines.extend([
        r"\midrule",
        rf"\multicolumn{{6}}{{l}}{{Convergence ratio: "
        rf"{agg['convergence_ratio']:.0%} "
        rf"({agg['n_align']}\checkmark{{}} / "
        rf"{agg['n_align'] + agg['n_contradict']} cells, "
        rf"$p = {agg['binomial_p']:.4f}$)}} \\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    path = output_dir / "T_convergence.tex"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def print_summary(all_results: dict):
    """Print a concise console summary of all experiment results."""
    sep = "=" * 70
    dash = "-" * 70
    print(f"\n{sep}")
    tag = all_results["metadata"].get("tag", "full")
    excluded = all_results["metadata"].get("excluded_sources", [])
    title = f"EC-TEL 2026 RETROACTIVE VALIDATION -- RESULTS [{tag}]"
    if excluded:
        title += f"  (excluded: {', '.join(excluded)})"
    print(title)
    print(sep)

    for exp_key in ["exp1", "exp2", "exp3", "exp4", "exp5"]:
        r = all_results[exp_key]
        print(f"\n{dash}")
        print(f"  {r['experiment']}")
        print(dash)
        if "prediction" in r:
            print(f"  Prediction: {r['prediction']}")

        agg = r.get("aggregate", {})
        if "pooled_tau" in agg:
            print(f"  Pooled tau: {agg['pooled_tau']:.4f} (p={agg['pooled_p']:.4f})")
            print(f"  Weighted tau: {agg['weighted_tau']:.4f}")
            print(f"  Sources positive: {agg['positive_count']}/{agg['n_sources']}")
        elif "confirmed_count" in agg:
            total = agg.get("n_sources", agg.get("n_sources_with_data", 0))
            print(f"  Confirmed: {agg['confirmed_count']}/{total}")
        if "convergence_ratio" in agg:
            print(f"  Convergence ratio: {agg['convergence_ratio']:.0%}")
            print(f"  Binomial p: {agg['binomial_p']:.4f}")

        print(f"  >> {r['interpretation']}")

    print(f"\n{'=' * 70}")


def run(exclude: list[str] | None = None, tag: str = "full",
        output_dir: Path | None = None) -> dict:
    """Run all experiments with optional source exclusion.

    Args:
        exclude: List of source names to exclude (e.g. ["Temnikova2010"]).
        tag: Label for this run variant (used in filenames and metadata).
        output_dir: Override output directory. Defaults to outputs/ectel/<tag>/.
    """
    exclude = exclude or []

    if output_dir is None:
        output_dir = BASE_OUTPUT_DIR / tag if tag != "full" else BASE_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Filter sources
    exp1_sources = filter_sources(EXP1_SOURCES, exclude)
    exp2_sources = filter_sources(EXP2_SOURCES, exclude)
    exp3_sources = filter_sources(EXP3_SOURCES, exclude)
    exp4_sources = filter_sources(EXP4_SOURCES, exclude)

    excluded_label = f" (excluding {', '.join(exclude)})" if exclude else ""
    print(f"Running EC-TEL 2026 retroactive validation experiments{excluded_label}...\n")

    # Experiment 1
    src_count = len(exp1_sources)
    print(f"[1/5] Experiment 1: ToM Ordering vs Difficulty Rankings ({src_count} sources)...")
    exp1_results = exp1.run_all(exp1_sources)

    # Experiment 2
    src_count = len(exp2_sources)
    print(f"[2/5] Experiment 2: Fluency Paradox ({src_count} sources)...")
    exp2_results = exp2.run_all(exp2_sources)

    # Experiment 3
    src_count = len(exp3_sources)
    print(f"[3/5] Experiment 3: Experience x ToM Interaction ({src_count} sources)...")
    exp3_results = exp3.run_all(exp3_sources)

    # Experiment 4
    src_count = len(exp4_sources)
    print(f"[4/5] Experiment 4: Over-Editing as Misdirected ToM ({src_count} sources)...")
    exp4_results = exp4.run_all(exp4_sources)

    # Experiment 5
    print("[5/5] Experiment 5: Integrative Convergence...")
    exp5_results = exp5.run_all(exp1_results, exp2_results, exp3_results, exp4_results)

    all_results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "spec_version": "ECTEL2026_v1",
            "tag": tag,
            "excluded_sources": exclude,
            "description": "Retroactive validation of ToM framework against published PE data",
            "source_counts": {
                "exp1": len(exp1_sources),
                "exp2": len(exp2_sources),
                "exp3": len(exp3_sources),
                "exp4": len(exp4_sources),
            },
        },
        "exp1": exp1_results,
        "exp2": exp2_results,
        "exp3": exp3_results,
        "exp4": exp4_results,
        "exp5": exp5_results,
    }

    # Save JSON results
    results_path = output_dir / "all_results.json"
    results_path.write_text(
        json.dumps(all_results, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nResults saved to {results_path}")

    # Generate figures
    print("\nGenerating figures...")
    f4 = viz.figure_f4_difficulty_scatter(exp1_results, output_dir)
    print(f"  F4: {f4}")
    f5 = viz.figure_f5_fluency_asymmetry(exp2_results, output_dir)
    print(f"  F5: {f5}")
    f6 = viz.figure_f6_convergence_heatmap(exp5_results, output_dir)
    print(f"  F6: {f6}")
    f_exp4 = viz.figure_exp4_overediting_bars(exp4_results, output_dir)
    if f_exp4:
        print(f"  Supp: {f_exp4}")

    # Generate LaTeX
    print("\nGenerating LaTeX tables...")
    tex = generate_latex_convergence(exp5_results, output_dir)
    print(f"  {tex}")

    # Console summary
    print_summary(all_results)

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="EC-TEL 2026 retroactive validation experiments"
    )
    parser.add_argument(
        "--exclude", nargs="+", default=[],
        help="Source names to exclude (e.g. Temnikova2010)",
    )
    parser.add_argument(
        "--tag", default=None,
        help="Label for this run variant (default: auto-generated from exclusions)",
    )
    args = parser.parse_args()

    # Auto-generate tag from exclusions if not provided
    if args.tag is None:
        if args.exclude:
            args.tag = "no_" + "_".join(
                name.lower().replace("2010", "").replace("2017", "").replace("2018", "").replace("2019", "").replace("2020", "").replace("2021", "").replace("2013", "").replace("2016", "")
                for name in args.exclude
            )
        else:
            args.tag = "full"

    run(exclude=args.exclude, tag=args.tag)


if __name__ == "__main__":
    main()
