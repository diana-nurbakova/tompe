"""Generate LaTeX tables for the pipeline validation paper.

Creates booktabs-formatted LaTeX table strings matching the spec's
Table 1 (pipeline validation), Table 2 (ablation comparison), and
Table 3 (three-way agreement + explanation quality).

Usage:
    python -m experiments.pipeline_validation.tables
    python -m experiments.pipeline_validation.tables --results-dir path/to/results
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from experiments.pipeline_validation.config import RESULTS_DIR, TOM_LEVELS, ensure_dirs

logger = logging.getLogger(__name__)

# ToM level display labels for tables
_TOM_SHORT = {
    "1st_machine": "L0 (Machine)",
    "1st_author": "L1 (Author)",
    "2nd_reader": "L2 (Reader)",
    "recursive": "L3 (Recursive)",
}


def _fmt(value, fmt: str = ".3f", na: str = "--") -> str:
    """Format a numeric value for a LaTeX cell, returning *na* for None."""
    if value is None:
        return na
    try:
        return f"{float(value):{fmt}}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value, na: str = "--") -> str:
    """Format a value as a percentage string (e.g. 0.92 -> 92.0)."""
    if value is None:
        return na
    try:
        return f"{float(value) * 100:.1f}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Table 1: Pipeline validation metrics (N=200)
# ---------------------------------------------------------------------------


def table1_pipeline_validation(results: dict) -> str:
    r"""Table 1: Pipeline validation metrics (N=200).

    Combines structural (A1), GEMBA (A2), and xCOMET (A3) results
    into a single summary table broken down by ToM level.

    Args:
        results: Dict with keys ``structural``, ``gemba``, ``xcomet``,
                 each containing the respective track result dicts.

    Returns:
        LaTeX table string (booktabs format).
    """
    structural = results.get("structural", {})
    gemba = results.get("gemba", {})
    xcomet = results.get("xcomet", {})

    gemba_by_tom = gemba.get("by_tom_level", {})
    xcomet_by_tom = xcomet.get("by_tom_level", {})

    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Pipeline validation metrics ($N{=}200$).}",
        r"  \label{tab:pipeline-validation}",
        r"  \small",
        r"  \begin{tabular}{l c c c c}",
        r"    \toprule",
        r"    \textbf{ToM Level} & \textbf{Struct.\ Pass} & \textbf{GEMBA Det.} & \textbf{Cat.\ Agree.} & \textbf{xCOMET $\Delta$} \\",
        r"    \midrule",
    ]

    for lvl in TOM_LEVELS:
        label = _TOM_SHORT.get(lvl, lvl)
        g = gemba_by_tom.get(lvl, {})
        x = xcomet_by_tom.get(lvl, {})

        det_rate = _pct(g.get("detection_rate"))
        cat_agree = _pct(g.get("category_agreement"))
        score_drop = _fmt(x.get("mean_drop"), ".4f")

        lines.append(
            f"    {label} & -- & {det_rate}\\% & {cat_agree}\\% & {score_drop} \\\\"
        )

    # Aggregate row
    lines.append(r"    \midrule")
    lines.append(
        f"    \\textbf{{Overall}} & "
        f"{_pct(structural.get('pass_rate'))}\\% & "
        f"{_pct(gemba.get('detection_rate'))}\\% & "
        f"{_pct(gemba.get('category_agreement'))}\\% & "
        f"{_fmt(xcomet.get('mean_score_drop'), '.4f')} \\\\"
    )

    # Clean items row
    clean_acc = gemba.get("clean_accuracy")
    clean_drop = xcomet.get("clean_stability", {}).get("mean_abs_drop")
    lines.append(
        f"    Clean ($n$={gemba.get('clean_items', 50)}) & "
        f"-- & "
        f"FP acc.\ {_pct(clean_acc)}\\% & "
        f"-- & "
        f"{_fmt(clean_drop, '.4f')} \\\\"
    )

    lines.extend([
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Table 2: Ablation comparison (N=60 x 4 conditions)
# ---------------------------------------------------------------------------


def table2_ablation_comparison(results: dict) -> str:
    r"""Table 2: Ablation comparison ($N{=}60 \times 4$ conditions).

    Args:
        results: Ablation results dict (from ablation_results.json)
                 with a ``table`` list of row dicts.

    Returns:
        LaTeX table string.
    """
    table = results.get("table", [])

    # Condition display names
    cond_names = {
        "B0_random": "B0: Random",
        "B1_single_step": "B1: Single-step",
        "B2_unconstrained": "B2: Unconstrained",
        "full_pipeline": "\\textbf{Full pipeline}",
    }

    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Ablation comparison ($N{=}60$ segments $\times$ 4 conditions).}",
        r"  \label{tab:ablation}",
        r"  \small",
        r"  \begin{tabular}{l c c c c c}",
        r"    \toprule",
        r"    \textbf{Condition} & \textbf{Struct.} & \textbf{GEMBA} & \textbf{Cat.\ Fid.} & \textbf{xCOMET $\Delta$} & \textbf{Text Pres.} \\",
        r"    \midrule",
    ]

    for row in table:
        cond = row.get("condition", "")
        name = cond_names.get(cond, cond)
        lines.append(
            f"    {name} & "
            f"{_pct(row.get('structural_pass_rate'))}\\% & "
            f"{_pct(row.get('gemba_detection_rate'))}\\% & "
            f"{_pct(row.get('category_fidelity'))}\\% & "
            f"{_fmt(row.get('xcomet_score_drop'), '.4f')} & "
            f"{_pct(row.get('text_preservation_rate'))}\\% \\\\"
        )

    # Deltas row (improvement of full pipeline over baselines)
    deltas = results.get("deltas_vs_full", {})
    if deltas:
        lines.append(r"    \midrule")
        lines.append(r"    \multicolumn{6}{l}{\textit{Improvement of full pipeline over baselines:}} \\")
        for cond, d in deltas.items():
            name = cond_names.get(cond, cond).replace("\\textbf{", "").replace("}", "")
            struct_d = d.get("structural_delta", 0)
            gemba_d = d.get("gemba_delta", 0)
            sign_s = "+" if struct_d >= 0 else ""
            sign_g = "+" if gemba_d >= 0 else ""
            lines.append(
                f"    vs.\ {name} & "
                f"{sign_s}{_pct(struct_d)}pp & "
                f"{sign_g}{_pct(gemba_d)}pp & "
                f"-- & -- & -- \\\\"
            )

    lines.extend([
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Table 3: Three-way agreement + explanation quality
# ---------------------------------------------------------------------------


def table3_agreement_and_explanation(results: dict) -> str:
    r"""Table 3: Three-way agreement and explanation quality.

    Args:
        results: Dict with keys ``agreement`` (from three_way_agreement.json)
                 and optionally ``explanation`` (from explanation_quality.json).

    Returns:
        LaTeX table string.
    """
    agreement = results.get("agreement", {})
    explanation = results.get("explanation", {})

    pairwise = agreement.get("pairwise_agreement", {})
    by_tom = agreement.get("agreement_by_tom", {})
    overlap = agreement.get("three_way_overlap", {})
    trend = agreement.get("cochran_armitage_trend", {})

    expl_by_tom = explanation.get("by_tom_level", {})

    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Three-way agreement and explanation quality by ToM level.}",
        r"  \label{tab:agreement-explanation}",
        r"  \small",
        r"  \begin{tabular}{l c c c c c c}",
        r"    \toprule",
        r"    & \multicolumn{3}{c}{\textbf{Agreement ($\kappa$)}} & \multicolumn{3}{c}{\textbf{Explanation Quality}} \\",
        r"    \cmidrule(lr){2-4} \cmidrule(lr){5-7}",
        r"    \textbf{ToM Level} & \textbf{P--H} & \textbf{P--G} & \textbf{H--G} & \textbf{Accuracy} & \textbf{Clarity} & \textbf{Complete.} \\",
        r"    \midrule",
    ]

    for lvl in TOM_LEVELS:
        label = _TOM_SHORT.get(lvl, lvl)
        tom_data = by_tom.get(lvl, {})
        expl_data = expl_by_tom.get(lvl, {})

        ph = _fmt(tom_data.get("pipeline_human_kappa"))
        pg = _fmt(tom_data.get("pipeline_gemba_kappa"))
        hg = _fmt(tom_data.get("human_gemba_kappa"))

        acc = _fmt(expl_data.get("factual_accuracy"))
        cla = _fmt(expl_data.get("clarity"))
        com = _fmt(expl_data.get("completeness"))

        lines.append(
            f"    {label} & {ph} & {pg} & {hg} & {acc} & {cla} & {com} \\\\"
        )

    # Overall row
    lines.append(r"    \midrule")
    lines.append(
        f"    \\textbf{{Overall}} & "
        f"{_fmt(pairwise.get('pipeline_human_kappa'))} & "
        f"{_fmt(pairwise.get('pipeline_gemba_kappa'))} & "
        f"{_fmt(pairwise.get('human_gemba_kappa'))} & "
        f"-- & -- & -- \\\\"
    )

    # Three-way overlap
    all_three = overlap.get("all_three", 0)
    missed = overlap.get("missed_by_both", 0)
    lines.append(
        f"    Three-way overlap & "
        f"\\multicolumn{{3}}{{c}}{{{_pct(all_three)}\\% all agree}} & "
        f"\\multicolumn{{3}}{{c}}{{{_pct(missed)}\\% missed by both}} \\\\"
    )

    # Trend test
    z = trend.get("z_statistic", 0)
    p = trend.get("p_value", 1)
    direction = trend.get("trend_direction", "none")
    lines.append(
        f"    Trend test & "
        f"\\multicolumn{{6}}{{c}}{{$z = {_fmt(z, '.2f')}$, "
        f"$p = {_fmt(p, '.4f')}$ ({direction})}} \\\\"
    )

    lines.extend([
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Master generator
# ---------------------------------------------------------------------------


def generate_all_tables(results_dir: Path, output_dir: Path | None = None) -> None:
    """Load results and write .tex files.

    Reads from the standard result file locations and writes
    table1.tex, table2.tex, table3.tex.
    """
    ensure_dirs()
    out_dir = output_dir or (results_dir / "tables")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Table 1: Combine Track A results
    t1_data: dict = {}

    structural_path = results_dir / "track_a" / "a1_structural_check.json"
    if structural_path.exists():
        with open(structural_path, "r", encoding="utf-8") as f:
            t1_data["structural"] = json.load(f)

    gemba_path = results_dir / "track_a" / "a2_gemba_detection.json"
    if gemba_path.exists():
        with open(gemba_path, "r", encoding="utf-8") as f:
            t1_data["gemba"] = json.load(f)

    xcomet_path = results_dir / "track_a" / "a3_xcomet_scoring.json"
    if xcomet_path.exists():
        with open(xcomet_path, "r", encoding="utf-8") as f:
            t1_data["xcomet"] = json.load(f)

    if t1_data:
        tex1 = table1_pipeline_validation(t1_data)
        (out_dir / "table1.tex").write_text(tex1, encoding="utf-8")
        logger.info("Written table1.tex")
    else:
        logger.info("No Track A results found; skipping Table 1.")

    # Table 2: Ablation
    ablation_path = results_dir / "track_b" / "ablation_results.json"
    if ablation_path.exists():
        with open(ablation_path, "r", encoding="utf-8") as f:
            ablation_data = json.load(f)
        tex2 = table2_ablation_comparison(ablation_data)
        (out_dir / "table2.tex").write_text(tex2, encoding="utf-8")
        logger.info("Written table2.tex")
    else:
        logger.info("No ablation results found; skipping Table 2.")

    # Table 3: Agreement + explanation quality
    t3_data: dict = {}
    agreement_path = results_dir / "track_c" / "three_way_agreement.json"
    if agreement_path.exists():
        with open(agreement_path, "r", encoding="utf-8") as f:
            t3_data["agreement"] = json.load(f)

    expl_path = results_dir / "track_c" / "explanation_quality.json"
    if expl_path.exists():
        with open(expl_path, "r", encoding="utf-8") as f:
            t3_data["explanation"] = json.load(f)

    if t3_data:
        tex3 = table3_agreement_and_explanation(t3_data)
        (out_dir / "table3.tex").write_text(tex3, encoding="utf-8")
        logger.info("Written table3.tex")
    else:
        logger.info("No Track C results found; skipping Table 3.")

    logger.info("Table generation complete. Output: %s", out_dir)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Generate LaTeX tables for the pipeline validation paper."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_DIR,
        help=f"Results directory (default: {RESULTS_DIR}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for .tex files (default: results/tables/).",
    )
    args = parser.parse_args()

    generate_all_tables(args.results_dir, args.output_dir)
