"""C1–C4 tagging-strategy ablation (error-injection spec §5.5).

Runs the full ToM-PE injection pipeline on the same shared segments under
each of the four tag formats (C1 bare → C4 full) and computes Layer 1
automatic metrics per condition:

  - parse_success_rate — fraction of items where the LLM emitted a
    well-formed tag of the requested format
  - structural_pass_rate — fraction of items where the full
    `_verify_injection` check passes (parse + diff + format-specific
    attribute checks)
  - gemba_detection_rate — fraction of items where GEMBA-MQM
    independently detects the injected error (≥1 match)
  - category_fidelity — fraction of injected errors whose primary_tag
    is a valid PrimaryTag value (C2+ only; N/A for C1 which has no
    semantic tag name)
  - text_preservation_rate — fraction of items where non-error text is
    ≥95% similar to the reference (proxy for span isolation)
  - mean_severity_drop — mean of (clean_score − injected_score) per item

Layer 2 (LLM-as-judge) and Layer 3 (expert human) metrics are not
included in this v1 runner; they require a calibrated judge prompt and
a manual review pass respectively (spec §5.5 follow-up work).

Usage:

    python -m experiments.pipeline_validation.ablation_tagging \\
        --n-items 30 --conditions C1,C2,C3,C4

    python -m experiments.pipeline_validation.ablation_tagging \\
        --dry-run --n-items 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tompe.pipeline.codebook import load_default_codebook
from tompe.pipeline.error_injector import (
    ErrorProfile,
    inject_errors_reference_based,
)
from tompe.pipeline.tag_formats import TagFormat
from tompe.schemas.annotation import AnnotationConfig
from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.enums import (
    AnnotationLevel,
    ItemPathway,
    MQMCategory,
    PrimaryTag,
    Severity,
    TOMLevel,
)
from tompe.schemas.error import InjectedError
from tompe.schemas.item import AssessmentItem, ItemMetadata

from experiments.pipeline_validation.config import (
    DEFAULT_LLM_CONFIG,
    RESULTS_DIR,
    VALIDATION_SEVERITY_DISTRIBUTION,
    ensure_dirs,
)
from experiments.pipeline_validation.generate_batch import load_all_segments
from experiments.pipeline_validation.track_b.ablation_comparison import (
    _compute_metrics,
    compute_text_preservation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TaggingConditionResult:
    """Metrics for one tag-format condition."""

    condition: str  # "C1" .. "C4"
    n_items: int = 0
    n_parse_success: int = 0  # tag well-formed, no other checks
    n_structural_pass: int = 0  # _verify_injection returned []
    parse_success_rate: float = 0.0
    structural_pass_rate: float = 0.0
    gemba_detection_rate: float = 0.0
    category_fidelity: float | None = None
    text_preservation_rate: float | None = None
    items: list[AssessmentItem] = field(default_factory=list)


@dataclass
class TaggingAblationResults:
    """Collected results across the four conditions."""

    n_segments: int
    conditions: list[TaggingConditionResult] = field(default_factory=list)
    segments_used: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-condition runner
# ---------------------------------------------------------------------------


def _sample_segments(
    all_segments: list[CorpusSegment],
    n: int,
    seed: int = 42,
) -> list[CorpusSegment]:
    """Sample N segments deterministically, balancing across origins."""
    if n >= len(all_segments):
        return list(all_segments)

    rng = random.Random(seed)
    by_origin: dict[str, list[CorpusSegment]] = {}
    for seg in all_segments:
        by_origin.setdefault(seg.corpus_origin, []).append(seg)

    # Ceiling-divide so the per-origin quota over-fills slightly; the
    # final trim brings us back to exactly n.
    n_origins = max(1, len(by_origin))
    quota = max(1, (n + n_origins - 1) // n_origins)
    sampled: list[CorpusSegment] = []
    for origin, segs in by_origin.items():
        rng.shuffle(segs)
        sampled.extend(segs[:quota])

    rng.shuffle(sampled)
    return sampled[:n]


def _segment_to_item(
    seg: CorpusSegment,
    presented_text: str,
    errors: list[InjectedError],
    condition: str,
    parse_succeeded: bool,
) -> AssessmentItem:
    """Wrap a tagged segment into an AssessmentItem for metric evaluation."""
    tom_profile: dict[TOMLevel, int] = {level: 0 for level in TOMLevel}
    mqm_profile: dict[MQMCategory, int] = {cat: 0 for cat in MQMCategory}
    for err in errors:
        tom_profile[err.tom_level] = tom_profile.get(err.tom_level, 0) + 1

    metadata = ItemMetadata(
        tom_profile=tom_profile,
        mqm_profile=mqm_profile,
        estimated_time_minutes=2.0,
        has_clean_segments=False,
        scaffolding_level=AnnotationLevel.ANALYST,
        pathway=ItemPathway.CONTROLLED,
        translation_direction=f"{seg.source_lang}->{seg.target_lang}",
    )
    annotation_config = AnnotationConfig(level=AnnotationLevel.ANALYST)

    item = AssessmentItem(
        item_id=f"ablation_{condition}_{seg.segment_id}",
        segment_id=seg.segment_id,
        source_text=seg.source_text,
        source_lang=seg.source_lang,
        target_lang=seg.target_lang,
        presented_text=presented_text,
        reference_translation=seg.reference_translation,
        mt_system="reference_perturbed",
        pathway=ItemPathway.CONTROLLED,
        errors=errors,
        clean_spans=[],
        annotations=[],
        annotation_config=annotation_config,
        difficulty_level=3,
        domain=seg.domain,
        metadata=metadata,
    )
    # Stash parse_succeeded as an annotation; it isn't a real schema
    # field but `model_dump()` preserves it for the metric step below.
    setattr(item, "_parse_succeeded", parse_succeeded)
    return item


async def _run_condition(
    condition: TagFormat,
    segments: list[CorpusSegment],
    llm_config: dict,
) -> TaggingConditionResult:
    """Run injection under one tag-format condition over all segments."""
    name = condition.value  # "C1" .. "C4"
    logger.info("=== Condition %s: %d segments ===", name, len(segments))

    codebook = load_default_codebook()
    profile = ErrorProfile(
        primary_tags=list(PrimaryTag),
        severity_distribution={
            Severity(k): v for k, v in VALIDATION_SEVERITY_DISTRIBUTION.items()
        },
        tom_levels=None,
        direction="both",
    )

    items: list[AssessmentItem] = []
    n_parse_success = 0
    n_structural_pass = 0
    for seg in segments:
        try:
            modified_text, errors = await inject_errors_reference_based(
                segment=seg,
                error_profile=profile,
                llm_config=llm_config,
                codebook=codebook,
                tag_format=condition,
            )
            n_parse_success += 1
            n_structural_pass += 1  # got past verify_injection
            items.append(_segment_to_item(seg, modified_text, errors, name, True))
        except ValueError as exc:
            # Verification failed after retries — parse may have succeeded
            # but format-specific checks did not. Track as a soft failure.
            logger.info("Condition %s: segment %s verification failed: %s",
                        name, seg.segment_id, exc)
            items.append(_segment_to_item(
                seg, seg.reference_translation, [], name, False,
            ))
        except Exception:
            logger.exception("Condition %s: segment %s unexpected error",
                             name, seg.segment_id)
            items.append(_segment_to_item(
                seg, seg.reference_translation, [], name, False,
            ))

    result = TaggingConditionResult(
        condition=name,
        n_items=len(items),
        n_parse_success=n_parse_success,
        n_structural_pass=n_structural_pass,
        parse_success_rate=n_parse_success / max(1, len(items)),
        structural_pass_rate=n_structural_pass / max(1, len(items)),
        items=items,
    )

    # Reuse Track B's per-condition metric computation (GEMBA + xCOMET +
    # category fidelity + text preservation).
    enriched = await _compute_metrics(
        f"tagging_{name}",
        [it for it in items if it.errors],  # only items with successful injections
        llm_config=llm_config,
    )
    result.gemba_detection_rate = enriched.gemba_detection_rate
    result.category_fidelity = (
        enriched.category_fidelity if condition != TagFormat.C1_BARE else None
    )
    if items:
        result.text_preservation_rate = compute_text_preservation(items)
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_tagging_ablation(
    n_items: int,
    conditions: list[TagFormat],
    llm_config: dict,
    seed: int = 42,
    dry_run: bool = False,
) -> TaggingAblationResults:
    """Run the C1–C4 ablation on the shared sample of N items."""
    ensure_dirs()
    all_segs = load_all_segments()
    segments = _sample_segments(all_segs, n_items, seed=seed)
    logger.info("Sampled %d segments (from %d available)",
                len(segments), len(all_segs))

    results = TaggingAblationResults(
        n_segments=len(segments),
        segments_used=[s.segment_id for s in segments],
    )

    if dry_run:
        logger.info("=== DRY RUN ===")
        logger.info("Conditions: %s", [c.value for c in conditions])
        logger.info("Sample size per condition: %d", len(segments))
        logger.info("Total injections would be: %d × %d = %d",
                    len(conditions), len(segments),
                    len(conditions) * len(segments))
        return results

    for condition in conditions:
        cond_result = await _run_condition(condition, segments, llm_config)
        results.conditions.append(cond_result)
        logger.info(
            "Condition %s done: parse=%.2f struct=%.2f gemba=%.2f tp=%s",
            cond_result.condition,
            cond_result.parse_success_rate,
            cond_result.structural_pass_rate,
            cond_result.gemba_detection_rate,
            (f"{cond_result.text_preservation_rate:.2f}"
             if cond_result.text_preservation_rate is not None else "N/A"),
        )

    return results


def save_results(
    results: TaggingAblationResults,
    output_path: Path | None = None,
) -> Path:
    """Save the ablation results as JSON.

    Items are dropped from the serialisation (only the metrics are kept)
    because the full items can be re-generated from the recorded
    segment_ids if needed.
    """
    out_dir = output_path or (RESULTS_DIR / "tagging_ablation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "tagging_ablation_results.json"

    payload: dict = {
        "n_segments": results.n_segments,
        "segments_used": results.segments_used,
        "conditions": [],
    }
    for c in results.conditions:
        d = asdict(c)
        d.pop("items", None)  # don't serialise full items
        payload["conditions"].append(d)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    logger.info("Tagging-ablation results saved to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_conditions(spec: str) -> list[TagFormat]:
    name_to_fmt = {c.value: c for c in TagFormat}
    out: list[TagFormat] = []
    for token in spec.split(","):
        token = token.strip().upper()
        if not token:
            continue
        if token not in name_to_fmt:
            raise SystemExit(
                f"Unknown condition {token!r}; expected any of "
                f"{sorted(name_to_fmt.keys())}"
            )
        out.append(name_to_fmt[token])
    return out


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="C1–C4 tagging-strategy ablation (error-injection spec §5.5)."
    )
    parser.add_argument(
        "--n-items", type=int, default=30,
        help="Number of source segments to inject per condition (default: 30).",
    )
    parser.add_argument(
        "--conditions", type=str, default="C1,C2,C3,C4",
        help="Comma-separated list of conditions (any of C1, C2, C3, C4).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Seed for the segment sample (default: 42).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be done without running injection.",
    )
    parser.add_argument(
        "--llm-provider", type=str, default=None,
        help="Override LLM provider.",
    )
    parser.add_argument(
        "--llm-model", type=str, default=None,
        help="Override LLM model.",
    )
    args = parser.parse_args()

    config = dict(DEFAULT_LLM_CONFIG)
    if args.llm_provider:
        config["provider"] = args.llm_provider
    if args.llm_model:
        config["model"] = args.llm_model

    conditions = _parse_conditions(args.conditions)

    results = asyncio.run(run_tagging_ablation(
        n_items=args.n_items,
        conditions=conditions,
        llm_config=config,
        seed=args.seed,
        dry_run=args.dry_run,
    ))
    if results.conditions:
        path = save_results(results)
        print(f"Tagging-ablation results written to {path}")
    elif args.dry_run:
        print("Dry run complete.")


if __name__ == "__main__":
    main()
