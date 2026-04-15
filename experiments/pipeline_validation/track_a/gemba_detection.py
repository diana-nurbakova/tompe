"""A2 — GEMBA-MQM detection validation.

Extends the core qe_validator by computing richer metrics:
category agreement, false-positive rate on clean items, detection rate
broken down by ToM level, and IoU-based span matching.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from tompe.pipeline.llm_client import LLMClient, make_client_from_config
from tompe.pipeline.qe_validator import (
    GEMBA_RESPONSE_SCHEMA,
    GEMBA_SYSTEM_PROMPT,
    GEMBAError,
    QEValidationResult,
    _build_gemba_user_prompt,
    _match_gemba_to_injected,
    validate_item_gemba,
)
from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel
from tompe.schemas.error import InjectedError
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    DEFAULT_LLM_CONFIG,
    GEMBA_DETECTION_TARGET,
    IOU_THRESHOLD,
    RESULTS_DIR,
    ensure_dirs,
)

logger = logging.getLogger(__name__)

# ── GEMBA category → PrimaryTag mapping ──────────────────────────────────────

_GEMBA_CATEGORY_MAP: dict[str, set[PrimaryTag]] = {
    "accuracy": {PrimaryTag.MISTRANSLATION, PrimaryTag.OMISSION, PrimaryTag.ADDITION},
    "fluency": {PrimaryTag.GRAMMAR, PrimaryTag.SPELLING, PrimaryTag.PUNCTUATION},
    "terminology": {PrimaryTag.TERMINOLOGY},
    "style": {PrimaryTag.STYLE},
    "locale": {PrimaryTag.LOCALE},
}


def _normalize_gemba_category(cat: str) -> str:
    """Normalize a GEMBA category string for lookup."""
    return cat.strip().lower()


def _category_matches(gemba_category: str, injected_tag: PrimaryTag) -> bool:
    """Check whether a GEMBA category maps to the injected PrimaryTag."""
    norm = _normalize_gemba_category(gemba_category)
    allowed_tags = _GEMBA_CATEGORY_MAP.get(norm, set())
    return injected_tag in allowed_tags


# ── IoU span matching ────────────────────────────────────────────────────────


def _compute_span_iou(
    g_start: int,
    g_end: int,
    i_start: int,
    i_end: int,
) -> float:
    """Compute Intersection-over-Union for two character spans."""
    intersection = max(0, min(g_end, i_end) - max(g_start, i_start))
    union = (g_end - g_start) + (i_end - i_start) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _find_span_in_text(span_text: str, full_text: str) -> tuple[int, int] | None:
    """Find the character offsets of span_text within full_text."""
    pos = full_text.lower().find(span_text.lower().strip())
    if pos < 0:
        return None
    return pos, pos + len(span_text.strip())


# ── Result dataclass ─────────────────────────────────────────────────────────


@dataclass
class GEMBADetectionResult:
    """Detection result for a single item."""

    item_id: str
    total_injected: int
    detected: int
    category_matches: int
    false_positives: int
    is_clean: bool
    clean_correct: bool  # True if clean item and GEMBA found 0 errors
    per_error: list[dict] = field(default_factory=list)


# ── Core detection logic ─────────────────────────────────────────────────────


async def run_gemba_detection(
    item: AssessmentItem,
    llm_config: dict,
) -> GEMBADetectionResult:
    """Run GEMBA-MQM on a single item and compare against ground truth.

    Returns a GEMBADetectionResult with per-error detail.
    """
    injected_errors = [e for e in item.errors if isinstance(e, InjectedError)]
    is_clean = len(injected_errors) == 0

    # Call the existing validator
    qe_result = await validate_item_gemba(
        source_text=item.source_text,
        reference=item.reference_translation,
        injected_text=item.presented_text,
        injected_errors=injected_errors,
        llm_config=llm_config,
        source_lang=item.source_lang,
        target_lang=item.target_lang,
    )

    gemba_errors = qe_result.gemba_errors

    # For clean items
    if is_clean:
        fp_count = len(gemba_errors)
        return GEMBADetectionResult(
            item_id=item.item_id,
            total_injected=0,
            detected=0,
            category_matches=0,
            false_positives=fp_count,
            is_clean=True,
            clean_correct=(fp_count == 0),
        )

    # Match each injected error to GEMBA detections using IoU
    per_error: list[dict] = []
    matched_gemba_indices: set[int] = set()
    detected_count = 0
    category_match_count = 0

    for inj in injected_errors:
        best_iou = 0.0
        best_idx: int | None = None
        best_gemba: GEMBAError | None = None

        for g_idx, g_err in enumerate(gemba_errors):
            if g_idx in matched_gemba_indices:
                continue

            # Try to find the GEMBA span in the presented text
            span_pos = _find_span_in_text(g_err.span, item.presented_text)
            if span_pos is None:
                continue

            g_start, g_end = span_pos
            iou = _compute_span_iou(g_start, g_end, inj.span_start, inj.span_end)

            if iou > best_iou:
                best_iou = iou
                best_idx = g_idx
                best_gemba = g_err

        is_detected = best_iou >= IOU_THRESHOLD
        cat_match = False

        if is_detected and best_gemba is not None and best_idx is not None:
            detected_count += 1
            matched_gemba_indices.add(best_idx)
            cat_match = _category_matches(best_gemba.category, inj.primary_tag)
            if cat_match:
                category_match_count += 1

        per_error.append({
            "error_id": inj.error_id,
            "primary_tag": inj.primary_tag.value,
            "error_type": inj.error_type,
            "severity": inj.severity.value,
            "tom_level": inj.tom_level.value,
            "detected": is_detected,
            "best_iou": round(best_iou, 4),
            "category_match": cat_match,
            "gemba_category": best_gemba.category if best_gemba else None,
        })

    false_positives = len(gemba_errors) - len(matched_gemba_indices)

    return GEMBADetectionResult(
        item_id=item.item_id,
        total_injected=len(injected_errors),
        detected=detected_count,
        category_matches=category_match_count,
        false_positives=max(0, false_positives),
        is_clean=False,
        clean_correct=False,
        per_error=per_error,
    )


# ── Batch runner ──────────────────────────────────────────────────────────────


async def run_batch_gemba(
    items: list[AssessmentItem],
    llm_config: dict,
) -> dict:
    """Run GEMBA detection on a batch and compute aggregate metrics.

    Returns dict with:
        detection_rate, category_agreement, false_positive_rate,
        clean_accuracy, by_tom_level breakdown, per_item details.
    """
    results: list[GEMBADetectionResult] = []
    for item in items:
        try:
            r = await run_gemba_detection(item, llm_config)
            results.append(r)
        except Exception as e:
            logger.error("GEMBA detection failed for item %s: %s", item.item_id, e)

    # Separate clean and injected items
    clean_results = [r for r in results if r.is_clean]
    injected_results = [r for r in results if not r.is_clean]

    # Overall detection rate (across injected items)
    total_injected = sum(r.total_injected for r in injected_results)
    total_detected = sum(r.detected for r in injected_results)
    total_cat_matches = sum(r.category_matches for r in injected_results)
    total_fp = sum(r.false_positives for r in results)

    detection_rate = total_detected / max(total_injected, 1)
    category_agreement = total_cat_matches / max(total_detected, 1)

    # False positive rate: FP per item (across all items)
    fp_rate = total_fp / max(len(results), 1)

    # Clean item accuracy
    clean_correct = sum(1 for r in clean_results if r.clean_correct)
    clean_accuracy = clean_correct / max(len(clean_results), 1)

    # By ToM level breakdown
    by_tom_level: dict[str, dict] = {}
    for r in injected_results:
        for pe in r.per_error:
            tom = pe["tom_level"]
            if tom not in by_tom_level:
                by_tom_level[tom] = {
                    "total": 0,
                    "detected": 0,
                    "category_matches": 0,
                }
            by_tom_level[tom]["total"] += 1
            if pe["detected"]:
                by_tom_level[tom]["detected"] += 1
            if pe["category_match"]:
                by_tom_level[tom]["category_matches"] += 1

    for tom, counts in by_tom_level.items():
        counts["detection_rate"] = counts["detected"] / max(counts["total"], 1)
        counts["category_agreement"] = (
            counts["category_matches"] / max(counts["detected"], 1)
        )

    summary = {
        "detection_rate": round(detection_rate, 4),
        "category_agreement": round(category_agreement, 4),
        "false_positive_rate": round(fp_rate, 4),
        "clean_accuracy": round(clean_accuracy, 4),
        "meets_target": detection_rate >= GEMBA_DETECTION_TARGET,
        "target": GEMBA_DETECTION_TARGET,
        "iou_threshold": IOU_THRESHOLD,
        "total_items": len(results),
        "total_injected_errors": total_injected,
        "total_detected": total_detected,
        "total_false_positives": total_fp,
        "clean_items": len(clean_results),
        "clean_correct": clean_correct,
        "by_tom_level": by_tom_level,
        "per_item": [asdict(r) for r in results],
    }

    logger.info(
        "GEMBA detection: %d/%d detected (%.1f%%), "
        "category agreement %.1f%%, FP rate %.2f, "
        "clean accuracy %.1f%%, target %.0f%%",
        total_detected,
        total_injected,
        detection_rate * 100,
        category_agreement * 100,
        fp_rate,
        clean_accuracy * 100,
        GEMBA_DETECTION_TARGET * 100,
    )

    return summary


def save_results(summary: dict, output_dir: Path | None = None) -> Path:
    """Save GEMBA detection results to JSON."""
    ensure_dirs()
    out_dir = output_dir or (RESULTS_DIR / "track_a")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "a2_gemba_detection.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    logger.info("GEMBA detection results saved to %s", out_path)
    return out_path


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="A2: GEMBA-MQM detection validation."
    )
    parser.add_argument(
        "--items-file",
        type=str,
        required=True,
        help="Path to JSON file with list of AssessmentItem dicts.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save results (default: results/track_a/).",
    )
    parser.add_argument(
        "--llm-provider",
        type=str,
        default=None,
        help="Override LLM provider (default from config).",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="Override LLM model (default from config).",
    )
    args = parser.parse_args()

    items_path = Path(args.items_file)
    if not items_path.exists():
        logger.error("Items file not found: %s", items_path)
        sys.exit(1)

    with open(items_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    items = [AssessmentItem(**item) for item in raw_items]
    logger.info("Loaded %d items from %s", len(items), items_path)

    llm_config = dict(DEFAULT_LLM_CONFIG)
    if args.llm_provider:
        llm_config["provider"] = args.llm_provider
    if args.llm_model:
        llm_config["model"] = args.llm_model

    summary = asyncio.run(run_batch_gemba(items, llm_config))
    out_dir = Path(args.output_dir) if args.output_dir else None
    save_results(summary, output_dir=out_dir)

    if not summary["meets_target"]:
        logger.warning(
            "BELOW TARGET: detection rate %.1f%% < %.0f%%",
            summary["detection_rate"] * 100,
            GEMBA_DETECTION_TARGET * 100,
        )
        sys.exit(1)

    logger.info("GEMBA detection meets target.")
