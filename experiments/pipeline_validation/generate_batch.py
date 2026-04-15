"""Generate the 200-item validation batch (spec section 2).

Loads corpus segments from JSONL files, samples 50 per corpus, runs error
injection on 150 items (stratified by ToM level), keeps 50 clean, generates
explanations, and saves the batch as JSONL.

Usage:
    python -m experiments.pipeline_validation.generate_batch
    python -m experiments.pipeline_validation.generate_batch --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass  # dotenv not installed; rely on environment variables

from tompe.pipeline.codebook import load_default_codebook
from tompe.pipeline.error_injector import ErrorProfile, inject_errors_reference_based
from tompe.pipeline.explanation_generator import generate_all_explanations
from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.annotation import AnnotationConfig
from tompe.schemas.enums import (
    AnnotationLevel,
    ItemPathway,
    MQMCategory,
    PrimaryTag,
    Severity,
    TOMLevel,
)
from tompe.schemas.item import AssessmentItem, ItemMetadata

from experiments.pipeline_validation.config import (
    BASELINE_ITEMS,
    BASELINE_ITEMS_PER_TOM,
    CLEAN_ITEMS,
    CORPORA,
    CORPORA_DIR,
    DEFAULT_LLM_CONFIG,
    DIRECTION,
    INJECTED_ITEMS,
    ITEMS_PER_CORPUS,
    ITEMS_PER_TOM_LEVEL,
    MAX_ERRORS_PER_ITEM,
    MT_SYSTEMS,
    RESULTS_DIR,
    SEVERITY_DISTRIBUTION,
    SOURCE_LANG,
    TARGET_LANG,
    TOM_LEVELS,
    TOTAL_ITEMS,
    ensure_dirs,
)

logger = logging.getLogger(__name__)

SEED = 42

# Map config TOM_LEVELS strings to enums
_TOM_ENUM_MAP: dict[str, TOMLevel] = {
    "1st_machine": TOMLevel.FIRST_ORDER_MACHINE,
    "1st_author": TOMLevel.FIRST_ORDER_AUTHOR,
    "2nd_reader": TOMLevel.SECOND_ORDER_READER,
    "recursive": TOMLevel.RECURSIVE_MULTI,
}

# Build the severity distribution from config
_SEVERITY_MAP: dict[str, Severity] = {
    "minor": Severity.MINOR,
    "major": Severity.MAJOR,
    "critical": Severity.CRITICAL,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_corpus_segments(corpus_name: str, n: int) -> list[CorpusSegment]:
    """Load up to *n* segments from the JSONL files for a given corpus.

    Looks for ``*.jsonl`` files in ``CORPORA_DIR / corpus_name /`` and reads
    CorpusSegment objects from them. Segments are shuffled (with a fixed seed)
    before sampling to ensure reproducibility.
    """
    corpus_dir = CORPORA_DIR / corpus_name
    if not corpus_dir.exists():
        logger.warning("Corpus directory not found: %s", corpus_dir)
        return []

    segments: list[CorpusSegment] = []
    for jsonl_path in sorted(corpus_dir.glob("*.jsonl")):
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # Supply defaults for fields that may be absent in raw corpora
                    data.setdefault("complexity_score", 0.0)
                    data.setdefault("terminology_density", 0.0)
                    data.setdefault("text_register", data.get("register", "formal"))
                    segments.append(CorpusSegment.model_validate(data))
                except Exception as exc:
                    logger.debug(
                        "Skipping invalid line in %s: %s", jsonl_path.name, exc
                    )

    logger.info(
        "Corpus '%s': loaded %d segments, sampling %d",
        corpus_name, len(segments), min(n, len(segments)),
    )

    rng = random.Random(SEED)
    rng.shuffle(segments)
    return segments[:n]


def _build_error_profile(tom_level: TOMLevel) -> ErrorProfile:
    """Build an ErrorProfile targeting a specific ToM level."""
    severity_dist = {
        _SEVERITY_MAP[k]: v for k, v in SEVERITY_DISTRIBUTION.items()
    }
    return ErrorProfile(
        primary_tags=list(PrimaryTag),
        severity_distribution=severity_dist,
        tom_levels=[tom_level],
    )


def _assign_mt_system(index: int) -> str:
    """Assign an MT system label based on item index.

    First 100 items: google_translate, next 100: deepseek_v3.
    """
    systems = list(MT_SYSTEMS.keys())
    if index < MT_SYSTEMS[systems[0]]:
        return systems[0]
    return systems[1]


def _build_assessment_item(
    segment: CorpusSegment,
    presented_text: str,
    errors: list,
    mt_system: str,
    item_index: int,
    is_clean: bool,
    explanations: list | None = None,
) -> AssessmentItem:
    """Construct an AssessmentItem from injection results."""
    item_id = f"val_{item_index:04d}_{segment.segment_id}"

    # Build ToM profile
    tom_profile: dict[TOMLevel, int] = {level: 0 for level in TOMLevel}
    mqm_profile: dict[MQMCategory, int] = {cat: 0 for cat in MQMCategory}

    from tompe.schemas.error import InjectedError

    for err in errors:
        if isinstance(err, InjectedError):
            tom_profile[err.tom_level] = tom_profile.get(err.tom_level, 0) + 1

    metadata = ItemMetadata(
        tom_profile=tom_profile,
        mqm_profile=mqm_profile,
        estimated_time_minutes=2.0,
        has_clean_segments=is_clean,
        scaffolding_level=AnnotationLevel.ANALYST,
        pathway=ItemPathway.CONTROLLED,
        translation_direction=f"{SOURCE_LANG}->{TARGET_LANG}",
    )

    annotation_config = AnnotationConfig(level=AnnotationLevel.ANALYST)

    return AssessmentItem(
        item_id=item_id,
        segment_id=segment.segment_id,
        source_text=segment.source_text,
        source_lang=segment.source_lang,
        target_lang=segment.target_lang,
        presented_text=presented_text,
        reference_translation=segment.reference_translation,
        mt_system=mt_system,
        pathway=ItemPathway.CONTROLLED,
        errors=errors if errors else [],
        clean_spans=[],
        annotations=[],
        annotation_config=annotation_config,
        difficulty_level=3,
        domain=segment.domain,
        metadata=metadata,
    )


def select_baseline_segments(
    items: list[AssessmentItem],
    n: int = BASELINE_ITEMS,
) -> list[str]:
    """Select *n* item IDs for baseline comparison, stratified by ToM level.

    Returns a list of item_id strings for the ablation study (Track B).
    Selects ~BASELINE_ITEMS_PER_TOM items per ToM level from the injected
    items.
    """
    from tompe.schemas.error import InjectedError

    rng = random.Random(SEED)

    # Group injected items by dominant ToM level
    by_tom: dict[str, list[AssessmentItem]] = {lvl: [] for lvl in TOM_LEVELS}
    for item in items:
        injected = [e for e in item.errors if isinstance(e, InjectedError)]
        if not injected:
            continue
        # Pick the first injected error's ToM level as representative
        tom = injected[0].tom_level
        tom_str = tom.value if isinstance(tom, TOMLevel) else str(tom)
        if tom_str in by_tom:
            by_tom[tom_str].append(item)

    selected_ids: list[str] = []
    per_tom = BASELINE_ITEMS_PER_TOM

    for lvl in TOM_LEVELS:
        pool = by_tom[lvl]
        if len(pool) <= per_tom:
            selected_ids.extend(it.item_id for it in pool)
        else:
            sample = rng.sample(pool, per_tom)
            selected_ids.extend(it.item_id for it in sample)

    logger.info(
        "Selected %d baseline segment IDs (%d requested)",
        len(selected_ids), n,
    )
    return selected_ids[:n]


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


async def generate_batch(
    llm_config: dict | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> list[AssessmentItem]:
    """Generate the validation batch.

    Args:
        llm_config: LLM configuration dict. Uses DEFAULT_LLM_CONFIG if None.
        dry_run: If True, report what would be done without running injection.
        limit: If set, cap total items to this number (for quick testing).

    Returns:
        List of AssessmentItem objects.
    """
    ensure_dirs()
    config = llm_config or dict(DEFAULT_LLM_CONFIG)
    codebook = load_default_codebook()

    # Step 1: Load corpus segments
    target_total = limit if limit else TOTAL_ITEMS
    # Over-sample per corpus to account for empty corpora, then cap later
    active_corpora = sum(1 for c in CORPORA if (CORPORA_DIR / c).exists())
    per_corpus = max(4, target_total // max(active_corpora, 1) + 2) if limit else ITEMS_PER_CORPUS

    all_segments: list[CorpusSegment] = []
    for corpus_name in CORPORA:
        segs = load_corpus_segments(corpus_name, per_corpus)
        all_segments.extend(segs)

    logger.info("Total segments loaded: %d (target: %d)", len(all_segments), target_total)

    # Cap to target if we loaded more
    if len(all_segments) > target_total:
        rng_pre = random.Random(SEED)
        rng_pre.shuffle(all_segments)
        all_segments = all_segments[:target_total]

    if len(all_segments) < target_total:
        logger.warning(
            "Only %d segments available (need %d). "
            "Proceeding with available segments.",
            len(all_segments), target_total,
        )

    # Step 2: Split into injection and clean pools
    # Always reserve 25% for clean items, matching CLEAN_RATIO from config
    rng = random.Random(SEED)
    rng.shuffle(all_segments)

    total_available = len(all_segments)
    n_clean = min(CLEAN_ITEMS, max(1, int(total_available * 0.25)))
    n_inject = total_available - n_clean

    inject_segments = all_segments[:n_inject]
    clean_segments = all_segments[n_inject : n_inject + n_clean]

    # Stratify injection segments by ToM level (evenly across available slots)
    tom_enums = [_TOM_ENUM_MAP[lvl] for lvl in TOM_LEVELS]
    tom_assignments = [tom_enums[i % len(tom_enums)] for i in range(n_inject)]
    rng.shuffle(tom_assignments)

    if dry_run:
        logger.info("=== DRY RUN ===")
        logger.info("Would process %d corpora: %s", len(CORPORA), CORPORA)
        logger.info("Total segments available: %d", len(all_segments))
        logger.info("Would inject errors into %d segments", n_inject)
        logger.info("Would keep %d segments clean", n_clean)
        logger.info(
            "ToM level distribution: %s",
            {lvl: tom_assignments.count(_TOM_ENUM_MAP[lvl]) for lvl in TOM_LEVELS},
        )
        logger.info("MT systems: %s", MT_SYSTEMS)
        logger.info("Error profile: severity=%s, max_errors=%d",
                     SEVERITY_DISTRIBUTION, MAX_ERRORS_PER_ITEM)
        logger.info("LLM config: %s", config)
        logger.info("Output: %s", RESULTS_DIR / "batch_200.jsonl")
        return []

    # Step 3: Run error injection
    items: list[AssessmentItem] = []
    item_index = 0

    logger.info("Injecting errors into %d segments...", n_inject)
    for seg_idx, (segment, tom_level) in enumerate(zip(inject_segments, tom_assignments)):
        mt_system = _assign_mt_system(item_index)
        profile = _build_error_profile(tom_level)

        try:
            presented_text, injected_errors = await inject_errors_reference_based(
                segment=segment,
                error_profile=profile,
                llm_config=config,
                codebook=codebook,
            )

            # Step 4: Generate explanations
            explanations = None
            try:
                explanations = await generate_all_explanations(
                    source_text=segment.source_text,
                    reference=segment.reference_translation,
                    errors=injected_errors,
                    mt_system=mt_system,
                    llm_config=config,
                )
            except Exception as exc:
                logger.warning(
                    "Explanation generation failed for segment %s: %s",
                    segment.segment_id, exc,
                )

            item = _build_assessment_item(
                segment=segment,
                presented_text=presented_text,
                errors=injected_errors,
                mt_system=mt_system,
                item_index=item_index,
                is_clean=False,
                explanations=explanations,
            )

            items.append(item)

            if (seg_idx + 1) % 25 == 0:
                logger.info(
                    "  Injected %d/%d segments", seg_idx + 1, n_inject
                )
        except Exception as exc:
            logger.error(
                "Injection failed for segment %s: %s",
                segment.segment_id, exc,
            )

        item_index += 1

    # Step 5: Build clean items
    logger.info("Building %d clean items...", n_clean)
    for segment in clean_segments:
        mt_system = _assign_mt_system(item_index)
        item = _build_assessment_item(
            segment=segment,
            presented_text=segment.reference_translation,
            errors=[],
            mt_system=mt_system,
            item_index=item_index,
            is_clean=True,
        )
        items.append(item)
        item_index += 1

    logger.info("Total items generated: %d", len(items))

    # Step 6: Save batch as JSONL
    batch_label = f"batch_{len(items)}" if limit else "batch_200"
    batch_path = RESULTS_DIR / f"{batch_label}.jsonl"
    with open(batch_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
    logger.info("Batch saved to %s", batch_path)

    # Step 7: Select baseline segment IDs
    baseline_ids = select_baseline_segments(items)
    baseline_path = RESULTS_DIR / "baseline_segment_ids.json"
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(baseline_ids, f, indent=2, ensure_ascii=False)
    logger.info("Baseline segment IDs saved to %s (%d IDs)", baseline_path, len(baseline_ids))

    return items


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Generate the 200-item validation batch (spec section 2)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be done without running injection.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap total items for quick testing (e.g. --limit 10).",
    )
    parser.add_argument(
        "--llm-provider",
        type=str,
        default=None,
        help="Override LLM provider.",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="Override LLM model.",
    )
    args = parser.parse_args()

    config = dict(DEFAULT_LLM_CONFIG)
    if args.llm_provider:
        config["provider"] = args.llm_provider
    if args.llm_model:
        config["model"] = args.llm_model

    result = asyncio.run(
        generate_batch(llm_config=config, dry_run=args.dry_run, limit=args.limit)
    )
    if result:
        print(f"Generated {len(result)} items.")
    else:
        print("Dry run complete.")
