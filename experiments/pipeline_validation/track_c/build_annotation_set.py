"""Track C: end-to-end builder for `data/annotations/annotation_set.json`.

Wires the pipeline outputs (full-pipeline items + baseline conditions
+ clean items) into the canonical annotation set consumed by the
expert annotation tool. Without this script teachers had to assemble
the inputs manually; the audit (annotation §4.1) flagged that gap.

Pipeline:

    1. Load `experiments/pipeline_validation/results/batch_200.jsonl`
       as the full-pipeline AssessmentItems.
    2. Load `baseline_segment_ids.json` (written by `generate_batch`)
       to identify the 60 shared segments.
    3. Resolve those segment_ids back to CorpusSegment objects (from
       `data/corpora/`) and run B0/B1/B2 via `track_b.run_ablation`.
    4. Partition the batch into clean / pipeline items.
    5. Call `select_annotation_items` and write
       `data/annotations/annotation_set.json`.

Usage:

    python -m experiments.pipeline_validation.track_c.build_annotation_set
    python -m experiments.pipeline_validation.track_c.build_annotation_set --skip-baselines
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from tompe.pipeline.segment_selector import load_corpus
from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    CORPORA,
    CORPORA_DIR,
    DEFAULT_LLM_CONFIG,
    RESULTS_DIR,
    ensure_dirs,
)
from experiments.pipeline_validation.track_b.ablation_comparison import run_ablation
from experiments.pipeline_validation.track_c.prepare_annotation_set import (
    save_annotation_set,
    select_annotation_items,
)

logger = logging.getLogger(__name__)

BATCH_PATH = RESULTS_DIR / "batch_200.jsonl"
BASELINE_IDS_PATH = RESULTS_DIR / "baseline_segment_ids.json"


def _load_batch(path: Path) -> list[AssessmentItem]:
    if not path.exists():
        raise FileNotFoundError(
            f"Batch file not found at {path}; run generate_batch first."
        )
    items: list[AssessmentItem] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(AssessmentItem.model_validate_json(line))
    logger.info("Loaded %d AssessmentItems from %s", len(items), path)
    return items


def _load_baseline_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Baseline IDs not found at {path}; run generate_batch first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_segments_for_items(
    pipeline_items: list[AssessmentItem],
    item_ids: list[str],
) -> list[CorpusSegment]:
    """Resolve the CorpusSegment for each baseline item_id from the
    pipeline items. We reconstruct CorpusSegment from the AssessmentItem
    fields rather than re-loading the raw corpus, which keeps the script
    deterministic with respect to whatever was used at generation time.
    """
    by_id = {it.item_id: it for it in pipeline_items}
    segments: list[CorpusSegment] = []
    for item_id in item_ids:
        item = by_id.get(item_id)
        if item is None:
            logger.warning("Baseline item_id %s not found in batch", item_id)
            continue
        segments.append(CorpusSegment(
            segment_id=item.segment_id,
            source_text=item.source_text,
            reference_translation=item.reference_translation,
            source_lang=item.source_lang,
            target_lang=item.target_lang,
            corpus_origin=item.metadata.corpus_origin if hasattr(item.metadata, "corpus_origin") else "unknown",
            domain=item.domain or "general",
            text_register="formal",
        ))
    return segments


def _partition(items: list[AssessmentItem]) -> tuple[list[AssessmentItem], list[AssessmentItem]]:
    """Split into (pipeline_items_with_errors, clean_items)."""
    pipeline_items = [i for i in items if i.errors]
    clean_items = [i for i in items if not i.errors]
    return pipeline_items, clean_items


async def build_annotation_set(
    skip_baselines: bool = False,
    seed: int | None = None,
) -> Path:
    """Build the annotation set and save it to disk."""
    ensure_dirs()

    items = _load_batch(BATCH_PATH)
    pipeline_items, clean_items = _partition(items)
    logger.info(
        "Partitioned batch: %d pipeline (with errors), %d clean",
        len(pipeline_items), len(clean_items),
    )

    baseline_items: dict[str, list[AssessmentItem]] = {"B0": [], "B1": [], "B2": []}
    if not skip_baselines:
        baseline_ids = _load_baseline_ids(BASELINE_IDS_PATH)
        segments = _resolve_segments_for_items(pipeline_items, baseline_ids)
        if not segments:
            logger.error("No baseline segments resolved; aborting baseline run")
        else:
            ablation = await run_ablation(
                segments=segments,
                llm_config=dict(DEFAULT_LLM_CONFIG),
                full_pipeline_items=None,  # not needed for annotation set baselines
                skip_gemba=True,            # metrics not needed here
            )
            for cond in ablation.conditions:
                if cond.condition == "B0_random":
                    baseline_items["B0"] = cond.items
                elif cond.condition == "B1_single_step":
                    baseline_items["B1"] = cond.items
                elif cond.condition == "B2_unconstrained":
                    baseline_items["B2"] = cond.items
            logger.info(
                "Baseline counts: B0=%d, B1=%d, B2=%d",
                len(baseline_items["B0"]),
                len(baseline_items["B1"]),
                len(baseline_items["B2"]),
            )

    kwargs = {} if seed is None else {"seed": seed}
    annotation_items = select_annotation_items(
        pipeline_items=pipeline_items,
        baseline_items=baseline_items,
        clean_items=clean_items,
        authentic_items=None,  # populated when authentic_detector is wired up
        **kwargs,
    )
    return save_annotation_set(annotation_items)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Build data/annotations/annotation_set.json end-to-end."
    )
    parser.add_argument(
        "--skip-baselines", action="store_true",
        help="Skip B0/B1/B2 ablation runs (faster; baselines empty in output).",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Override randomisation seed.",
    )
    args = parser.parse_args()

    out_path = asyncio.run(build_annotation_set(
        skip_baselines=args.skip_baselines,
        seed=args.seed,
    ))
    print(f"Annotation set written to {out_path}")


if __name__ == "__main__":
    main()
