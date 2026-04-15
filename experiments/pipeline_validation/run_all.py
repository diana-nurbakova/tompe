"""Master script for the full pipeline validation experiment.

Orchestrates batch generation, Track A/B/C execution, figure generation,
and table generation. Each track can be run independently.

Usage:
    python -m experiments.pipeline_validation.run_all --track a
    python -m experiments.pipeline_validation.run_all --track all
    python -m experiments.pipeline_validation.run_all --track b --skip-generation
    python -m experiments.pipeline_validation.run_all --track figures
    python -m experiments.pipeline_validation.run_all --dry-run --track all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    BASELINE_ITEMS,
    DEFAULT_LLM_CONFIG,
    RESULTS_DIR,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Item loading helpers
# ---------------------------------------------------------------------------


def _load_items_jsonl(path: Path) -> list[AssessmentItem]:
    """Load AssessmentItem objects from a JSONL file."""
    items: list[AssessmentItem] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            items.append(AssessmentItem.model_validate(data))
    logger.info("Loaded %d items from %s", len(items), path)
    return items


def _load_baseline_segment_ids(path: Path) -> list[str]:
    """Load baseline segment IDs from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        ids = json.load(f)
    logger.info("Loaded %d baseline segment IDs from %s", len(ids), path)
    return ids


def _items_to_segments(items: list[AssessmentItem]) -> list[CorpusSegment]:
    """Extract CorpusSegment-like objects from AssessmentItems.

    Creates minimal CorpusSegment objects from item fields for use
    in the ablation study where baselines need segments.
    """
    segments: list[CorpusSegment] = []
    seen: set[str] = set()
    for item in items:
        if item.segment_id in seen:
            continue
        seen.add(item.segment_id)
        segments.append(CorpusSegment(
            segment_id=item.segment_id,
            source_text=item.source_text,
            reference_translation=item.reference_translation,
            source_lang=item.source_lang,
            target_lang=item.target_lang,
            corpus_origin="europarl",  # placeholder; ablation does not depend on origin
            domain=item.domain,
            complexity_score=0.5,
            terminology_density=0.1,
            register="formal",
        ))
    return segments


# ---------------------------------------------------------------------------
# Track A: Structural + GEMBA + xCOMET
# ---------------------------------------------------------------------------


async def run_track_a(items: list[AssessmentItem], llm_config: dict) -> dict:
    """Run Track A: structural check (A1), GEMBA detection (A2), xCOMET (A3).

    Returns a dict with results from each sub-track.
    """
    from experiments.pipeline_validation.track_a.structural_check import (
        check_batch as structural_check_batch,
        save_results as save_structural,
    )
    from experiments.pipeline_validation.track_a.gemba_detection import (
        run_batch_gemba,
        save_results as save_gemba,
    )
    from experiments.pipeline_validation.track_a.xcomet_scoring import (
        score_batch as xcomet_score_batch,
        save_results as save_xcomet,
    )

    results: dict = {}

    # A1: Structural validation
    logger.info("=" * 60)
    logger.info("Track A1: Structural validation (%d items)", len(items))
    logger.info("=" * 60)
    structural_results = structural_check_batch(items)
    save_structural(structural_results)
    results["structural"] = structural_results
    logger.info(
        "A1 complete: pass rate %.1f%% (target met: %s)",
        structural_results["pass_rate"] * 100,
        structural_results["meets_target"],
    )

    # A2: GEMBA detection
    logger.info("=" * 60)
    logger.info("Track A2: GEMBA-MQM detection (%d items)", len(items))
    logger.info("=" * 60)
    gemba_results = await run_batch_gemba(items, llm_config)
    save_gemba(gemba_results)
    results["gemba"] = gemba_results
    logger.info(
        "A2 complete: detection rate %.1f%% (target met: %s)",
        gemba_results["detection_rate"] * 100,
        gemba_results["meets_target"],
    )

    # A3: xCOMET scoring
    logger.info("=" * 60)
    logger.info("Track A3: xCOMET scoring (%d items)", len(items))
    logger.info("=" * 60)
    xcomet_results = xcomet_score_batch(items)
    if xcomet_results is not None:
        save_xcomet(xcomet_results)
        results["xcomet"] = xcomet_results
        logger.info(
            "A3 complete: mean score drop %.4f",
            xcomet_results["mean_score_drop"],
        )
    else:
        logger.warning("A3 skipped: xCOMET model unavailable.")

    return results


# ---------------------------------------------------------------------------
# Track B: Ablation baselines
# ---------------------------------------------------------------------------


async def run_track_b(
    items: list[AssessmentItem],
    baseline_ids: list[str],
    llm_config: dict,
) -> dict:
    """Run Track B: ablation comparison across 4 conditions.

    Uses the subset of items identified by baseline_ids, reconstructs
    CorpusSegment objects, and runs all baselines plus the full pipeline.

    Returns the ablation comparison dict.
    """
    from experiments.pipeline_validation.track_b.ablation_comparison import (
        run_ablation,
        compare_conditions,
        save_results as save_ablation,
    )

    # Select the baseline items
    baseline_items = [it for it in items if it.item_id in set(baseline_ids)]
    if not baseline_items:
        logger.warning(
            "No items matched baseline IDs. Using first %d injected items.",
            BASELINE_ITEMS,
        )
        from tompe.schemas.error import InjectedError
        injected = [it for it in items if any(isinstance(e, InjectedError) for e in it.errors)]
        baseline_items = injected[:BASELINE_ITEMS]

    segments = _items_to_segments(baseline_items)

    logger.info("=" * 60)
    logger.info("Track B: Ablation comparison (%d segments)", len(segments))
    logger.info("=" * 60)

    ablation_results = await run_ablation(segments, llm_config)
    comparison = compare_conditions(ablation_results)
    save_ablation(ablation_results)

    logger.info("Track B complete.")
    for row in comparison.get("table", []):
        logger.info(
            "  %s: structural=%.1f%%, gemba=%.1f%%",
            row["condition"],
            row["structural_pass_rate"] * 100,
            row["gemba_detection_rate"] * 100,
        )

    return comparison


# ---------------------------------------------------------------------------
# Track C: Human annotation (prepare + analyse)
# ---------------------------------------------------------------------------


def run_track_c_prepare(
    items: list[AssessmentItem],
) -> None:
    """Run Track C: prepare annotation set (human annotation is offline).

    Selects items from the batch and baseline conditions, randomises them,
    and saves the annotation set for the human evaluation study.
    """
    from tompe.schemas.error import InjectedError
    from experiments.pipeline_validation.track_c.prepare_annotation_set import (
        select_annotation_items,
        save_annotation_set,
    )

    logger.info("=" * 60)
    logger.info("Track C (prepare): Building annotation set")
    logger.info("=" * 60)

    # Separate pipeline items (with errors) and clean items
    pipeline_items = [
        it for it in items
        if any(isinstance(e, InjectedError) for e in it.errors)
    ]
    clean_items = [
        it for it in items
        if not any(isinstance(e, InjectedError) for e in it.errors)
    ]

    # For baselines, we would need pre-generated baseline items.
    # If they exist in results, load them; otherwise pass empty dicts.
    baselines: dict[str, list[AssessmentItem]] = {}
    for bname in ("B0", "B1", "B2"):
        bpath = RESULTS_DIR / "track_b" / f"{bname}_items.json"
        if bpath.exists():
            with open(bpath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            baselines[bname] = [AssessmentItem.model_validate(r) for r in raw]
            logger.info("Loaded %d baseline %s items", len(baselines[bname]), bname)
        else:
            logger.info("No baseline %s items found at %s", bname, bpath)

    annotation_set = select_annotation_items(
        pipeline_items=pipeline_items,
        baseline_items=baselines,
        clean_items=clean_items,
    )
    path = save_annotation_set(annotation_set)
    logger.info(
        "Track C prepare complete: %d items saved to %s",
        len(annotation_set), path,
    )


def run_track_c_analysis() -> None:
    """Run post-annotation analysis (after human annotations are collected).

    Loads the collected annotations and runs three-way agreement (C2)
    and naturalness test (C3).
    """
    from experiments.pipeline_validation.track_c.three_way_agreement import (
        run_three_way_analysis,
        save_results as save_agreement,
    )
    from experiments.pipeline_validation.track_c.naturalness_test import (
        compare_naturalness,
        save_results as save_naturalness,
    )
    from tompe.schemas.expert_annotation import ExpertAnnotation, GEMBAAnnotation

    logger.info("=" * 60)
    logger.info("Track C (analysis): Post-annotation analysis")
    logger.info("=" * 60)

    # Load items
    batch_path = RESULTS_DIR / "batch_200.jsonl"
    if not batch_path.exists():
        logger.error("Batch file not found: %s. Run generation first.", batch_path)
        return

    items = _load_items_jsonl(batch_path)

    # Load human annotations
    from experiments.pipeline_validation.config import ANNOTATIONS_DIR
    human_path = ANNOTATIONS_DIR / "expert_annotations.json"
    gemba_path = RESULTS_DIR / "track_a" / "a2_gemba_detection.json"

    if not human_path.exists():
        logger.error(
            "Human annotations not found at %s. "
            "Complete the annotation study first.", human_path
        )
        return

    with open(human_path, "r", encoding="utf-8") as f:
        human_raw = json.load(f)
    human_annotations = {
        r["item_id"]: ExpertAnnotation.model_validate(r) for r in human_raw
    }
    logger.info("Loaded %d expert annotations", len(human_annotations))

    # Load GEMBA annotations (reconstruct from detection results)
    gemba_annotations: dict[str, GEMBAAnnotation] = {}
    if gemba_path.exists():
        with open(gemba_path, "r", encoding="utf-8") as f:
            gemba_data = json.load(f)
        # Attempt to load GEMBA annotations if stored separately
        gemba_annot_path = ANNOTATIONS_DIR / "gemba_annotations.json"
        if gemba_annot_path.exists():
            with open(gemba_annot_path, "r", encoding="utf-8") as f:
                gemba_raw = json.load(f)
            gemba_annotations = {
                r["item_id"]: GEMBAAnnotation.model_validate(r) for r in gemba_raw
            }
            logger.info("Loaded %d GEMBA annotations", len(gemba_annotations))
        else:
            logger.warning(
                "GEMBA annotations file not found at %s. "
                "Three-way analysis will have limited data.", gemba_annot_path
            )
    else:
        logger.warning("GEMBA results not found; three-way analysis may be incomplete.")

    # C2: Three-way agreement
    if human_annotations and gemba_annotations:
        agreement = run_three_way_analysis(items, human_annotations, gemba_annotations)
        save_agreement(agreement)
        logger.info(
            "C2 complete: pipeline-human kappa=%.3f, human-GEMBA kappa=%.3f",
            agreement["pairwise_agreement"].get("pipeline_human_kappa", 0),
            agreement["pairwise_agreement"].get("human_gemba_kappa", 0),
        )
    else:
        logger.warning("Skipping C2: insufficient annotation data.")

    # C3: Naturalness test
    # Split human annotations by item source
    pipeline_annots = [
        a for a in human_annotations.values()
        if getattr(a, "item_source", "") in ("full_pipeline", "baseline_B0", "baseline_B1", "baseline_B2")
    ]
    authentic_annots = [
        a for a in human_annotations.values()
        if getattr(a, "item_source", "") == "authentic"
    ]

    if pipeline_annots and authentic_annots:
        comparison = compare_naturalness(pipeline_annots, authentic_annots)
        save_naturalness(comparison)
        logger.info("C3 complete: naturalness comparison saved.")
    else:
        logger.warning(
            "Skipping C3: need both pipeline (%d) and authentic (%d) annotations.",
            len(pipeline_annots), len(authentic_annots),
        )

    logger.info("Track C analysis complete.")


# ---------------------------------------------------------------------------
# Figure and table generation
# ---------------------------------------------------------------------------


def run_figures() -> None:
    """Generate all figures from existing result files."""
    from experiments.pipeline_validation.figures import generate_all_figures
    logger.info("=" * 60)
    logger.info("Generating figures")
    logger.info("=" * 60)
    generate_all_figures(RESULTS_DIR)


def run_tables() -> None:
    """Generate all LaTeX tables from existing result files."""
    from experiments.pipeline_validation.tables import generate_all_tables
    logger.info("=" * 60)
    logger.info("Generating LaTeX tables")
    logger.info("=" * 60)
    generate_all_tables(RESULTS_DIR)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def main() -> None:
    """Parse args and run selected tracks."""
    parser = argparse.ArgumentParser(
        description="Master script for the full pipeline validation experiment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m experiments.pipeline_validation.run_all --track a\n"
            "  python -m experiments.pipeline_validation.run_all --track all\n"
            "  python -m experiments.pipeline_validation.run_all --track b --skip-generation\n"
            "  python -m experiments.pipeline_validation.run_all --track figures\n"
        ),
    )
    parser.add_argument(
        "--track",
        choices=["a", "b", "c-prepare", "c-analysis", "figures", "tables", "all"],
        default="all",
        help="Which track to run (default: all).",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip batch generation; load from existing batch_200.jsonl.",
    )
    parser.add_argument(
        "--llm-config",
        type=str,
        default=None,
        help="Optional JSON string to override LLM configuration.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be done without executing.",
    )
    args = parser.parse_args()

    # Setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    ensure_dirs()

    # LLM config
    llm_config = dict(DEFAULT_LLM_CONFIG)
    if args.llm_config:
        try:
            overrides = json.loads(args.llm_config)
            llm_config.update(overrides)
            logger.info("LLM config overrides applied: %s", overrides)
        except json.JSONDecodeError as exc:
            logger.error("Invalid --llm-config JSON: %s", exc)
            sys.exit(1)

    track = args.track
    run_all = track == "all"
    batch_path = RESULTS_DIR / "batch_200.jsonl"
    baseline_ids_path = RESULTS_DIR / "baseline_segment_ids.json"

    # Dry run report
    if args.dry_run:
        logger.info("=== DRY RUN ===")
        logger.info("Track: %s", track)
        logger.info("Skip generation: %s", args.skip_generation)
        logger.info("LLM config: %s", llm_config)
        logger.info("Batch path: %s (exists: %s)", batch_path, batch_path.exists())
        logger.info("Baseline IDs: %s (exists: %s)", baseline_ids_path, baseline_ids_path.exists())

        if run_all or track == "a":
            logger.info("Would run: Track A (structural + GEMBA + xCOMET)")
        if run_all or track == "b":
            logger.info("Would run: Track B (ablation comparison)")
        if run_all or track == "c-prepare":
            logger.info("Would run: Track C prepare (annotation set)")
        if run_all or track == "c-analysis":
            logger.info("Would run: Track C analysis (agreement + naturalness)")
        if run_all or track == "figures":
            logger.info("Would run: Figure generation")
        if run_all or track == "tables":
            logger.info("Would run: Table generation")
        return

    # Step 0: Generate or load batch
    items: list[AssessmentItem] = []

    if args.skip_generation:
        if not batch_path.exists():
            logger.error(
                "Cannot skip generation: %s does not exist. "
                "Run without --skip-generation first.", batch_path
            )
            sys.exit(1)
        items = _load_items_jsonl(batch_path)
    elif run_all or track in ("a", "b", "c-prepare"):
        if batch_path.exists():
            logger.info("Batch file exists; loading from %s", batch_path)
            items = _load_items_jsonl(batch_path)
        else:
            from experiments.pipeline_validation.generate_batch import generate_batch
            logger.info("Generating validation batch...")
            items = await generate_batch(llm_config=llm_config)

    # Load baseline IDs
    baseline_ids: list[str] = []
    if baseline_ids_path.exists():
        baseline_ids = _load_baseline_segment_ids(baseline_ids_path)

    # Step 1: Track A
    if run_all or track == "a":
        if not items:
            logger.error("No items available for Track A.")
            sys.exit(1)
        await run_track_a(items, llm_config)

    # Step 2: Track B
    if run_all or track == "b":
        if not items:
            logger.error("No items available for Track B.")
            sys.exit(1)
        await run_track_b(items, baseline_ids, llm_config)

    # Step 3: Track C prepare
    if run_all or track == "c-prepare":
        if not items:
            logger.error("No items available for Track C prepare.")
            sys.exit(1)
        run_track_c_prepare(items)

    # Step 4: Track C analysis (post-annotation)
    if track == "c-analysis":
        run_track_c_analysis()

    # Step 5: Figures
    if run_all or track == "figures":
        run_figures()

    # Step 6: Tables
    if run_all or track == "tables":
        run_tables()

    logger.info("=" * 60)
    logger.info("Pipeline validation complete.")
    logger.info("Results directory: %s", RESULTS_DIR)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())
