"""Track C1: Prepare the annotation set for the human evaluation study.

Selects and randomises items for the annotation study following the
composition specified in annotation-tool-spec section 4.1:

  - Full pipeline: 6 per ToM level = 24
  - Baseline B0: 6
  - Baseline B1: 6
  - Baseline B2: 6
  - Clean items: 12
  - Authentic MT: 12 (if available)
  - Practice items: 3 (excluded from analysis)

Items are stratified by ToM level and randomised with a fixed seed.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from tompe.schemas.enums import TOMLevel
from tompe.schemas.expert_annotation import AnnotationSetItem
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    ANNOTATION_BASELINE_PER_CONDITION,
    ANNOTATION_CLEAN,
    ANNOTATION_AUTHENTIC,
    ANNOTATION_PIPELINE_PER_TOM,
    ANNOTATION_PRACTICE,
    ANNOTATION_RANDOMISATION_SEED,
    ANNOTATIONS_DIR,
    RESULTS_DIR,
    TOM_LEVELS,
    ensure_dirs,
)

logger = logging.getLogger(__name__)

# Maps TOM_LEVELS config strings to the enum
_TOM_ENUM_MAP: dict[str, TOMLevel] = {
    "1st_machine": TOMLevel.FIRST_ORDER_MACHINE,
    "1st_author": TOMLevel.FIRST_ORDER_AUTHOR,
    "2nd_reader": TOMLevel.SECOND_ORDER_READER,
    "recursive": TOMLevel.RECURSIVE_MULTI,
}

# Baseline composition: distribute 6 baseline items across ToM levels
# (2 from L0, 1 from L1, 2 from L2, 1 from L3)
_BASELINE_TOM_QUOTA: dict[str, int] = {
    "1st_machine": 2,
    "1st_author": 1,
    "2nd_reader": 2,
    "recursive": 1,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tom_level(item: AssessmentItem) -> str | None:
    """Extract the dominant ToM level string from an item's metadata."""
    profile = item.metadata.tom_profile
    if not profile:
        return None
    # Return the level with the highest count
    best_level = max(profile, key=lambda k: profile[k])
    # Handle both enum keys and string keys
    if isinstance(best_level, TOMLevel):
        return best_level.value
    return str(best_level)


def _stratified_sample(
    items: list[AssessmentItem],
    per_level: int,
    rng: random.Random,
) -> list[AssessmentItem]:
    """Sample *per_level* items from each of the 4 ToM levels."""
    by_level: dict[str, list[AssessmentItem]] = {lvl: [] for lvl in TOM_LEVELS}

    for item in items:
        lvl = _get_tom_level(item)
        if lvl in by_level:
            by_level[lvl].append(item)

    selected: list[AssessmentItem] = []
    for lvl in TOM_LEVELS:
        pool = by_level[lvl]
        if len(pool) < per_level:
            logger.warning(
                "Only %d items for ToM level %s (need %d); using all available",
                len(pool), lvl, per_level,
            )
            selected.extend(pool)
        else:
            selected.extend(rng.sample(pool, per_level))

    return selected


def _baseline_sample(
    items: list[AssessmentItem],
    rng: random.Random,
) -> list[AssessmentItem]:
    """Sample baseline items using the ToM-level quota (2/1/2/1)."""
    by_level: dict[str, list[AssessmentItem]] = {lvl: [] for lvl in TOM_LEVELS}

    for item in items:
        lvl = _get_tom_level(item)
        if lvl in by_level:
            by_level[lvl].append(item)

    selected: list[AssessmentItem] = []
    for lvl, quota in _BASELINE_TOM_QUOTA.items():
        pool = by_level.get(lvl, [])
        if len(pool) < quota:
            logger.warning(
                "Baseline: only %d items for level %s (need %d)", len(pool), lvl, quota,
            )
            selected.extend(pool)
        else:
            selected.extend(rng.sample(pool, quota))

    return selected


def _item_to_annotation_set_item(
    item: AssessmentItem,
    condition: str,
    display_order: int,
    is_practice: bool = False,
) -> AnnotationSetItem:
    """Convert an AssessmentItem to an AnnotationSetItem."""
    tom_level_str = _get_tom_level(item)
    tom_int: int | None = None
    if tom_level_str is not None:
        level_order = {lvl: i for i, lvl in enumerate(TOM_LEVELS)}
        tom_int = level_order.get(tom_level_str)

    return AnnotationSetItem(
        item_id=item.item_id,
        source_text=item.source_text,
        presented_text=item.presented_text,
        reference_translation=item.reference_translation,
        item_source=condition,
        tom_level=tom_int,
        condition=condition,
        display_order=display_order,
        is_practice=is_practice,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_annotation_items(
    pipeline_items: list[AssessmentItem],
    baseline_items: dict[str, list[AssessmentItem]],  # {"B0": [...], "B1": [...], "B2": [...]}
    clean_items: list[AssessmentItem],
    authentic_items: list[AssessmentItem] | None = None,
    seed: int = ANNOTATION_RANDOMISATION_SEED,
) -> list[AnnotationSetItem]:
    """Select and randomise items for the annotation study.

    Args:
        pipeline_items: Full-pipeline items (should cover all 4 ToM levels).
        baseline_items: Dict mapping baseline name to items.
        clean_items: Items with no injected errors.
        authentic_items: Real MT error items (optional).
        seed: Random seed for reproducibility.

    Returns:
        Ordered list of AnnotationSetItem ready for the annotation tool.
    """
    rng = random.Random(seed)

    selected: list[tuple[AssessmentItem, str, bool]] = []  # (item, condition, is_practice)

    # 1. Full pipeline: 6 per ToM level = 24
    pipeline_selected = _stratified_sample(pipeline_items, ANNOTATION_PIPELINE_PER_TOM, rng)
    for item in pipeline_selected:
        selected.append((item, "full_pipeline", False))
    logger.info("Pipeline items selected: %d (target: %d)", len(pipeline_selected), 24)

    # 2. Baselines: 6 per condition, using shared segments with ToM quota
    for bname in ("B0", "B1", "B2"):
        pool = baseline_items.get(bname, [])
        b_selected = _baseline_sample(pool, rng)
        for item in b_selected:
            selected.append((item, f"baseline_{bname}", False))
        logger.info(
            "Baseline %s items selected: %d (target: %d)",
            bname, len(b_selected), ANNOTATION_BASELINE_PER_CONDITION,
        )

    # 3. Clean items: 12
    if len(clean_items) < ANNOTATION_CLEAN:
        logger.warning(
            "Only %d clean items available (need %d)", len(clean_items), ANNOTATION_CLEAN,
        )
        clean_selected = clean_items[:]
    else:
        clean_selected = rng.sample(clean_items, ANNOTATION_CLEAN)
    for item in clean_selected:
        selected.append((item, "clean", False))

    # 4. Authentic MT: 12 (if available)
    if authentic_items:
        n_auth = min(len(authentic_items), ANNOTATION_AUTHENTIC)
        if n_auth < ANNOTATION_AUTHENTIC:
            logger.warning(
                "Only %d authentic items available (need %d)", n_auth, ANNOTATION_AUTHENTIC,
            )
        auth_selected = rng.sample(authentic_items, n_auth)
        for item in auth_selected:
            selected.append((item, "authentic", False))
        logger.info("Authentic items selected: %d", n_auth)
    else:
        logger.info("No authentic items provided; skipping")

    # 5. Practice items: 3 from pipeline (excluded from analysis)
    remaining_pipeline = [
        it for it in pipeline_items if it not in [s[0] for s in selected]
    ]
    n_practice = min(ANNOTATION_PRACTICE, len(remaining_pipeline))
    if n_practice < ANNOTATION_PRACTICE:
        logger.warning(
            "Only %d items available for practice (need %d)", n_practice, ANNOTATION_PRACTICE,
        )
    practice = rng.sample(remaining_pipeline, n_practice) if remaining_pipeline else []
    for item in practice:
        selected.append((item, "practice", True))

    # Randomise the non-practice items; practice items always come first
    practice_entries = [(it, cond, pr) for it, cond, pr in selected if pr]
    analysis_entries = [(it, cond, pr) for it, cond, pr in selected if not pr]
    rng.shuffle(analysis_entries)

    # Build final ordered list
    ordered = practice_entries + analysis_entries
    annotation_items: list[AnnotationSetItem] = []
    for idx, (item, condition, is_practice) in enumerate(ordered):
        annotation_items.append(
            _item_to_annotation_set_item(item, condition, display_order=idx, is_practice=is_practice)
        )

    logger.info(
        "Annotation set: %d total (%d practice, %d analysis)",
        len(annotation_items),
        sum(1 for a in annotation_items if a.is_practice),
        sum(1 for a in annotation_items if not a.is_practice),
    )

    return annotation_items


def save_annotation_set(
    items: list[AnnotationSetItem],
    output_dir: Path | None = None,
) -> Path:
    """Save the annotation set as a JSON file.

    Args:
        items: The annotation set items.
        output_dir: Output directory (default: ANNOTATIONS_DIR).

    Returns:
        Path to the saved JSON file.
    """
    ensure_dirs()
    out_dir = output_dir or ANNOTATIONS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "annotation_set.json"

    data = [item.model_dump(mode="json") for item in items]
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Annotation set saved to %s (%d items)", out_path, len(items))
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Track C1: prepare annotation set")
    parser.add_argument("--pipeline-items", type=Path, help="JSON file with pipeline items")
    parser.add_argument("--baselines-dir", type=Path, help="Dir with B0.json, B1.json, B2.json")
    parser.add_argument("--clean-items", type=Path, help="JSON file with clean items")
    parser.add_argument("--authentic-items", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=ANNOTATION_RANDOMISATION_SEED)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    def _load_items(path: Path | None) -> list[AssessmentItem]:
        if path is None or not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [AssessmentItem.model_validate(r) for r in raw]

    def _load_baselines(baselines_dir: Path | None) -> dict[str, list[AssessmentItem]]:
        result: dict[str, list[AssessmentItem]] = {}
        if baselines_dir is None or not baselines_dir.exists():
            return result
        for name in ("B0", "B1", "B2"):
            fpath = baselines_dir / f"{name}.json"
            if fpath.exists():
                raw = json.loads(fpath.read_text(encoding="utf-8"))
                result[name] = [AssessmentItem.model_validate(r) for r in raw]
        return result

    pipeline = _load_items(args.pipeline_items)
    baselines = _load_baselines(args.baselines_dir)
    clean = _load_items(args.clean_items)
    authentic = _load_items(args.authentic_items) if args.authentic_items else None

    if not pipeline:
        logger.error("No pipeline items loaded; provide --pipeline-items")
    else:
        annotation_set = select_annotation_items(
            pipeline, baselines, clean, authentic, seed=args.seed,
        )
        path = save_annotation_set(annotation_set, args.output_dir)
        print(f"Annotation set saved to {path} ({len(annotation_set)} items)")
