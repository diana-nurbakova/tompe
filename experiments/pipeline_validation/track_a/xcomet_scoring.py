"""A3 — xCOMET-XL quality measurement.

Computes quality scores for clean and error-injected translations, then
measures score drops to validate that injected errors produce measurable
degradation detectable by a neural QE metric.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel
from tompe.schemas.error import InjectedError
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    RESULTS_DIR,
    XCOMET_BATCH_SIZE,
    XCOMET_MODEL,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


# ── Result dataclass ─────────────────────────────────────────────────────────


@dataclass
class XCOMETResult:
    """xCOMET scores for a single item."""

    item_id: str
    score_clean: float
    score_injected: float
    score_drop: float
    tom_level: str | None = None


# ── Model loading ────────────────────────────────────────────────────────────


def load_xcomet_model(
    model_name: str = XCOMET_MODEL,
) -> Any | None:
    """Load an xCOMET model via the comet library.

    Returns the loaded model, or None if the library or GPU is unavailable.
    """
    try:
        from comet import download_model, load_from_checkpoint

        model_path = download_model(model_name)
        model = load_from_checkpoint(model_path)
        logger.info("Loaded xCOMET model: %s", model_name)
        return model
    except ImportError:
        logger.warning(
            "comet library not installed — xCOMET scoring unavailable. "
            "Install with: pip install unbabel-comet"
        )
        return None
    except Exception as e:
        logger.warning(
            "Failed to load xCOMET model '%s': %s. "
            "GPU may be required for XCOMET-XL.",
            model_name,
            e,
        )
        return None


# ── Scoring helpers ──────────────────────────────────────────────────────────


def _score_translations(
    model: Any,
    sources: list[str],
    translations: list[str],
    references: list[str],
    batch_size: int = XCOMET_BATCH_SIZE,
) -> list[float]:
    """Score a batch of translations using the loaded xCOMET model.

    Returns per-segment scores.
    """
    data = [
        {"src": src, "mt": mt, "ref": ref}
        for src, mt, ref in zip(sources, translations, references)
    ]
    output = model.predict(data, batch_size=batch_size, gpus=1)
    # comet .predict() returns a dict with "scores" (per-segment) and "system_score"
    return output["scores"]


# ── Per-item scoring ─────────────────────────────────────────────────────────


def score_item(
    item: AssessmentItem,
    model: Any,
) -> XCOMETResult | None:
    """Score a single item (clean and injected) and return score drop.

    Returns None if the model is unavailable.
    """
    if model is None:
        return None

    injected_errors = [e for e in item.errors if isinstance(e, InjectedError)]
    tom_level = None
    if injected_errors:
        # Use the highest-demand ToM level among injected errors
        tom_order = [
            TOMLevel.FIRST_ORDER_MACHINE,
            TOMLevel.FIRST_ORDER_AUTHOR,
            TOMLevel.SECOND_ORDER_READER,
            TOMLevel.RECURSIVE_MULTI,
        ]
        levels_present = {e.tom_level for e in injected_errors}
        for lvl in reversed(tom_order):
            if lvl in levels_present:
                tom_level = lvl.value
                break

    # Score clean (reference as MT)
    clean_scores = _score_translations(
        model,
        sources=[item.source_text],
        translations=[item.reference_translation],
        references=[item.reference_translation],
    )
    score_clean = clean_scores[0]

    # Score injected (presented_text as MT)
    injected_scores = _score_translations(
        model,
        sources=[item.source_text],
        translations=[item.presented_text],
        references=[item.reference_translation],
    )
    score_injected = injected_scores[0]

    score_drop = score_clean - score_injected

    return XCOMETResult(
        item_id=item.item_id,
        score_clean=round(score_clean, 6),
        score_injected=round(score_injected, 6),
        score_drop=round(score_drop, 6),
        tom_level=tom_level,
    )


# ── Batch scoring ────────────────────────────────────────────────────────────


def score_batch(
    items: list[AssessmentItem],
    model: Any = None,
) -> dict | None:
    """Score a batch of items and return aggregate metrics.

    If model is None, attempts to load it. Returns None if loading fails.

    Returns dict with:
        mean_score_clean, mean_score_injected, mean_score_drop,
        by_tom_level, by_severity, clean_stability, per_item details.
    """
    if model is None:
        model = load_xcomet_model()
    if model is None:
        logger.warning("xCOMET model unavailable — skipping scoring.")
        return None

    # Separate clean and injected items
    clean_items: list[AssessmentItem] = []
    injected_items: list[AssessmentItem] = []
    for item in items:
        has_injected = any(isinstance(e, InjectedError) for e in item.errors)
        if has_injected:
            injected_items.append(item)
        else:
            clean_items.append(item)

    # --- Batch score clean references ---
    all_sources = [it.source_text for it in items]
    all_references = [it.reference_translation for it in items]
    all_presented = [it.presented_text for it in items]

    logger.info("Scoring %d clean translations...", len(items))
    clean_scores = _score_translations(
        model, all_sources, all_references, all_references
    )

    logger.info("Scoring %d injected translations...", len(items))
    injected_scores = _score_translations(
        model, all_sources, all_presented, all_references
    )

    # --- Build per-item results ---
    per_item_results: list[XCOMETResult] = []
    for idx, item in enumerate(items):
        inj_errors = [e for e in item.errors if isinstance(e, InjectedError)]
        tom_level = None
        if inj_errors:
            tom_order = [
                TOMLevel.FIRST_ORDER_MACHINE,
                TOMLevel.FIRST_ORDER_AUTHOR,
                TOMLevel.SECOND_ORDER_READER,
                TOMLevel.RECURSIVE_MULTI,
            ]
            levels_present = {e.tom_level for e in inj_errors}
            for lvl in reversed(tom_order):
                if lvl in levels_present:
                    tom_level = lvl.value
                    break

        r = XCOMETResult(
            item_id=item.item_id,
            score_clean=round(clean_scores[idx], 6),
            score_injected=round(injected_scores[idx], 6),
            score_drop=round(clean_scores[idx] - injected_scores[idx], 6),
            tom_level=tom_level,
        )
        per_item_results.append(r)

    # --- Aggregate metrics ---
    n = len(per_item_results)
    mean_clean = sum(r.score_clean for r in per_item_results) / max(n, 1)
    mean_injected = sum(r.score_injected for r in per_item_results) / max(n, 1)
    mean_drop = sum(r.score_drop for r in per_item_results) / max(n, 1)

    # By ToM level
    by_tom_level: dict[str, dict] = {}
    for r in per_item_results:
        if r.tom_level is None:
            continue
        if r.tom_level not in by_tom_level:
            by_tom_level[r.tom_level] = {"scores": [], "drops": []}
        by_tom_level[r.tom_level]["scores"].append(r.score_injected)
        by_tom_level[r.tom_level]["drops"].append(r.score_drop)

    for tom, data in by_tom_level.items():
        count = len(data["scores"])
        data["count"] = count
        data["mean_score"] = round(sum(data["scores"]) / max(count, 1), 6)
        data["mean_drop"] = round(sum(data["drops"]) / max(count, 1), 6)
        del data["scores"]
        del data["drops"]

    # By severity (use max severity per item)
    by_severity: dict[str, dict] = {}
    for idx, item in enumerate(items):
        inj_errors = [e for e in item.errors if isinstance(e, InjectedError)]
        if not inj_errors:
            continue
        sev_order = {Severity.MINOR: 0, Severity.MAJOR: 1, Severity.CRITICAL: 2}
        max_sev = max(inj_errors, key=lambda e: sev_order.get(e.severity, 0)).severity
        sev_key = max_sev.value
        if sev_key not in by_severity:
            by_severity[sev_key] = {"scores": [], "drops": []}
        by_severity[sev_key]["scores"].append(per_item_results[idx].score_injected)
        by_severity[sev_key]["drops"].append(per_item_results[idx].score_drop)

    for sev, data in by_severity.items():
        count = len(data["scores"])
        data["count"] = count
        data["mean_score"] = round(sum(data["scores"]) / max(count, 1), 6)
        data["mean_drop"] = round(sum(data["drops"]) / max(count, 1), 6)
        del data["scores"]
        del data["drops"]

    # Clean stability: for clean items, score_drop should be ~0
    clean_results = [r for r in per_item_results if r.tom_level is None]
    clean_drops = [abs(r.score_drop) for r in clean_results]
    clean_stability = {
        "count": len(clean_results),
        "mean_abs_drop": round(sum(clean_drops) / max(len(clean_drops), 1), 6),
        "max_abs_drop": round(max(clean_drops) if clean_drops else 0.0, 6),
    }

    summary = {
        "mean_score_clean": round(mean_clean, 6),
        "mean_score_injected": round(mean_injected, 6),
        "mean_score_drop": round(mean_drop, 6),
        "total_items": n,
        "injected_items": len(injected_items),
        "clean_items": len(clean_items),
        "model": XCOMET_MODEL,
        "by_tom_level": by_tom_level,
        "by_severity": by_severity,
        "clean_stability": clean_stability,
        "per_item": [asdict(r) for r in per_item_results],
    }

    logger.info(
        "xCOMET scoring: mean clean=%.4f, mean injected=%.4f, "
        "mean drop=%.4f (%d items)",
        mean_clean,
        mean_injected,
        mean_drop,
        n,
    )

    return summary


def save_results(summary: dict, output_dir: Path | None = None) -> Path:
    """Save xCOMET scoring results to JSON."""
    ensure_dirs()
    out_dir = output_dir or (RESULTS_DIR / "track_a")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "a3_xcomet_scoring.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    logger.info("xCOMET scoring results saved to %s", out_path)
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
        description="A3: xCOMET-XL quality score measurement."
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
        "--model",
        type=str,
        default=XCOMET_MODEL,
        help=f"xCOMET model name (default: {XCOMET_MODEL}).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=XCOMET_BATCH_SIZE,
        help=f"Batch size for scoring (default: {XCOMET_BATCH_SIZE}).",
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

    model = load_xcomet_model(args.model)
    if model is None:
        logger.error(
            "Cannot load xCOMET model. Ensure 'unbabel-comet' is installed "
            "and a GPU is available."
        )
        sys.exit(1)

    summary = score_batch(items, model=model)
    if summary is None:
        logger.error("Scoring returned no results.")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else None
    save_results(summary, output_dir=out_dir)

    logger.info(
        "xCOMET scoring complete. Mean drop: %.4f",
        summary["mean_score_drop"],
    )
