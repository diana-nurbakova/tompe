"""Track C: false-positive analysis (annotation-tool spec §6.6).

For each human-flagged error in the annotation set, classify it into one
of three categories:

  - **true_positive**:        IoU ≥ threshold against any pipeline-injected error
                              (the human correctly found a controlled-pipeline error).
  - **real_mt_error**:        no injected-error match, but IoU ≥ threshold against a
                              GEMBA-MQM-flagged span (i.e. the human found a real MT
                              error that was already present in the reference, not an
                              injected one — a "false positive" against the manifest
                              but a "true positive" against the actual translation).
  - **genuine_false_alarm**:  neither — the human flagged a span that neither the
                              pipeline nor GEMBA-MQM considers an error.

This is the categorisation called out as a checklist item in
annotation-tool spec §6.6 ("FP analysis: real-MT vs genuine FP").

GEMBA annotations are cached at ``data/annotations/_gemba/{item_id}.json``
on the first run; subsequent runs reuse the cache. The script can be
re-invoked offline once the cache is populated, which is the workflow
the spec assumes ("GEMBA-MQM parallel annotation pre-computed").

Usage:

    # Pre-compute + analyse, given a real annotation run on disk:
    python -m experiments.pipeline_validation.track_c.false_positive_analysis \\
        --batch-path experiments/pipeline_validation/results/batch_200.jsonl \\
        --annotations-dir data/annotations

    # Skip the GEMBA pre-compute (use whatever's cached):
    python -m experiments.pipeline_validation.track_c.false_positive_analysis \\
        --batch-path … --annotations-dir … --no-gemba-precompute

    # Dry-run / no annotators yet — only report what would happen:
    python -m experiments.pipeline_validation.track_c.false_positive_analysis \\
        --batch-path … --annotations-dir … --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from tompe.schemas.error import InjectedError
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    DEFAULT_LLM_CONFIG,
    IOU_THRESHOLD,
    RESULTS_DIR,
    ensure_dirs,
)
from experiments.pipeline_validation.track_c.three_way_agreement import (
    _cohens_kappa,
    _span_iou,
)

logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────────

CATEGORIES = ("true_positive", "real_mt_error", "genuine_false_alarm")
GEMBA_CACHE_SUBDIR = "_gemba"


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class CategorisedError:
    """A single human-annotated error after FP categorisation."""

    item_id: str
    annotator_id: str
    span_start: int
    span_end: int
    span_text: str
    human_category: str  # PrimaryTag value the annotator picked
    severity: str
    category: str  # "true_positive" | "real_mt_error" | "genuine_false_alarm"
    best_iou_injected: float = 0.0
    best_iou_gemba: float = 0.0


@dataclass
class AnnotatorStats:
    """Per-annotator FP statistics."""

    annotator_id: str
    n_items_annotated: int = 0
    n_errors_flagged: int = 0
    n_true_positive: int = 0
    n_real_mt_error: int = 0
    n_genuine_false_alarm: int = 0

    @property
    def true_positive_rate(self) -> float:
        return self.n_true_positive / max(1, self.n_errors_flagged)

    @property
    def false_positive_rate(self) -> float:
        fp = self.n_real_mt_error + self.n_genuine_false_alarm
        return fp / max(1, self.n_errors_flagged)

    @property
    def real_mt_rate_among_fps(self) -> float:
        fp = self.n_real_mt_error + self.n_genuine_false_alarm
        return self.n_real_mt_error / max(1, fp)


# ── GEMBA pre-computation + cache ───────────────────────────────────────────


def _gemba_cache_path(annotations_dir: Path, item_id: str) -> Path:
    return annotations_dir / GEMBA_CACHE_SUBDIR / f"{item_id}.json"


def _load_gemba_cache(annotations_dir: Path, item_id: str) -> list[dict] | None:
    path = _gemba_cache_path(annotations_dir, item_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("errors", [])
    except Exception as exc:
        logger.warning("Failed to read GEMBA cache for %s: %s", item_id, exc)
        return None


def _save_gemba_cache(annotations_dir: Path, item_id: str, payload: dict) -> None:
    path = _gemba_cache_path(annotations_dir, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


async def precompute_gemba_annotations(
    items: dict[str, AssessmentItem],
    annotations_dir: Path,
    llm_config: dict,
    force_refresh: bool = False,
) -> dict[str, list[dict]]:
    """Run GEMBA-MQM on each item and persist the raw error list to a cache.

    Returns a dict mapping item_id → list of error dicts (the same shape
    as the cached JSON's ``errors`` field). When a cache file is present
    and ``force_refresh`` is False, the GEMBA call is skipped.
    """
    # Imported lazily to avoid an unconditional dependency on the LLM client.
    from tompe.pipeline.qe_validator import validate_item_gemba

    out: dict[str, list[dict]] = {}
    n_cached = 0
    n_called = 0
    for item_id, item in items.items():
        cached = None if force_refresh else _load_gemba_cache(annotations_dir, item_id)
        if cached is not None:
            out[item_id] = cached
            n_cached += 1
            continue

        try:
            qe_result = await validate_item_gemba(
                source_text=item.source_text,
                reference=item.reference_translation,
                injected_text=item.presented_text,
                injected_errors=[],  # we want the raw GEMBA output, not a match
                llm_config=llm_config,
                source_lang=item.source_lang,
                target_lang=item.target_lang,
            )
        except Exception as exc:
            logger.exception("GEMBA pre-compute failed for %s: %s", item_id, exc)
            continue

        errors = []
        for g_err in qe_result.gemba_errors:
            # Locate the span in the presented text (best-effort, case-insensitive).
            span_pos = item.presented_text.lower().find(
                (g_err.span or "").lower().strip()
            )
            if span_pos < 0:
                span_start, span_end = 0, 0
            else:
                span_start = span_pos
                span_end = span_pos + len(g_err.span)
            errors.append({
                "span_start": span_start,
                "span_end": span_end,
                "span_text": g_err.span,
                "category": g_err.category,
                "subcategory": g_err.subcategory,
                "severity": g_err.severity,
                "explanation": g_err.explanation,
            })

        payload = {
            "item_id": item_id,
            "overall_quality": qe_result.overall_quality,
            "overall_score": qe_result.overall_score,
            "errors": errors,
        }
        _save_gemba_cache(annotations_dir, item_id, payload)
        out[item_id] = errors
        n_called += 1

    logger.info(
        "GEMBA pre-compute: %d items cached / %d items called (LLM)",
        n_cached, n_called,
    )
    return out


# ── Item + annotation loading ───────────────────────────────────────────────


def load_items_from_batch(batch_path: Path) -> dict[str, AssessmentItem]:
    """Load AssessmentItems from a JSONL batch file, keyed by item_id."""
    if not batch_path.exists():
        raise FileNotFoundError(f"Batch file not found: {batch_path}")
    out: dict[str, AssessmentItem] = {}
    with open(batch_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = AssessmentItem.model_validate_json(line)
            out[item.item_id] = item
    logger.info("Loaded %d items from %s", len(out), batch_path)
    return out


def load_human_annotations(
    annotations_dir: Path,
    annotator_ids: Iterable[str] | None = None,
) -> dict[str, list[dict]]:
    """Load all per-annotator JSON files under ``annotations_dir``.

    Returns a dict mapping annotator_id → list of annotation records
    (one per item). The cache subdirectory (``_gemba``) is skipped.
    """
    out: dict[str, list[dict]] = {}
    if not annotations_dir.exists():
        return out

    candidates = [
        d for d in annotations_dir.iterdir()
        if d.is_dir() and d.name != GEMBA_CACHE_SUBDIR
    ]
    if annotator_ids is not None:
        wanted = set(annotator_ids)
        candidates = [d for d in candidates if d.name in wanted]

    for ann_dir in candidates:
        records: list[dict] = []
        for path in sorted(ann_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    records.append(json.load(f))
            except Exception as exc:
                logger.warning("Skipping unreadable annotation %s: %s", path, exc)
        if records:
            out[ann_dir.name] = records
            logger.info("Annotator %s: %d items loaded", ann_dir.name, len(records))
    return out


# ── Categorisation core ─────────────────────────────────────────────────────


def _best_iou(
    span_start: int,
    span_end: int,
    candidates: list[dict],
) -> tuple[float, dict | None]:
    """Return (best_iou, best_candidate) for the most overlapping candidate."""
    best_iou = 0.0
    best: dict | None = None
    for c in candidates:
        c_start = c.get("span_start", 0)
        c_end = c.get("span_end", 0)
        if c_end <= c_start:
            continue
        iou = _span_iou(span_start, span_end, c_start, c_end)
        if iou > best_iou:
            best_iou, best = iou, c
    return best_iou, best


def classify_human_error(
    h_err: dict,
    injected_errors: list[InjectedError],
    gemba_errors: list[dict],
    iou_threshold: float = IOU_THRESHOLD,
) -> tuple[str, float, float]:
    """Classify a single human-annotated error.

    Returns (category, best_iou_injected, best_iou_gemba) where category
    is one of CATEGORIES.
    """
    h_start = h_err.get("span_start", 0)
    h_end = h_err.get("span_end", 0)

    injected_candidates = [
        {"span_start": e.span_start, "span_end": e.span_end}
        for e in injected_errors
    ]
    iou_inj, _ = _best_iou(h_start, h_end, injected_candidates)
    if iou_inj >= iou_threshold:
        return "true_positive", iou_inj, 0.0

    iou_gemba, _ = _best_iou(h_start, h_end, gemba_errors)
    if iou_gemba >= iou_threshold:
        return "real_mt_error", iou_inj, iou_gemba

    return "genuine_false_alarm", iou_inj, iou_gemba


# ── Per-annotator analysis ──────────────────────────────────────────────────


def analyse_annotator(
    annotator_id: str,
    records: list[dict],
    items_by_id: dict[str, AssessmentItem],
    gemba_by_id: dict[str, list[dict]],
    iou_threshold: float = IOU_THRESHOLD,
) -> tuple[AnnotatorStats, list[CategorisedError]]:
    """Categorise every error in this annotator's records."""
    stats = AnnotatorStats(annotator_id=annotator_id)
    categorised: list[CategorisedError] = []

    seen_items = set()
    for rec in records:
        if rec.get("is_practice"):
            continue
        item_id = rec.get("item_id")
        if item_id is None:
            continue
        seen_items.add(item_id)

        item = items_by_id.get(item_id)
        injected_errors = [
            e for e in (item.errors if item else [])
            if isinstance(e, InjectedError)
        ]
        gemba_errors = gemba_by_id.get(item_id, [])

        for h_err in rec.get("errors", []):
            category, iou_inj, iou_gemba = classify_human_error(
                h_err, injected_errors, gemba_errors, iou_threshold,
            )
            stats.n_errors_flagged += 1
            if category == "true_positive":
                stats.n_true_positive += 1
            elif category == "real_mt_error":
                stats.n_real_mt_error += 1
            else:
                stats.n_genuine_false_alarm += 1

            categorised.append(CategorisedError(
                item_id=item_id,
                annotator_id=annotator_id,
                span_start=h_err.get("span_start", 0),
                span_end=h_err.get("span_end", 0),
                span_text=h_err.get("span_text", ""),
                human_category=h_err.get("category", ""),
                severity=h_err.get("severity", ""),
                category=category,
                best_iou_injected=round(iou_inj, 4),
                best_iou_gemba=round(iou_gemba, 4),
            ))

    stats.n_items_annotated = len(seen_items)
    return stats, categorised


# ── Cross-annotator agreement on FP categorisation ──────────────────────────


def pairwise_fp_agreement(
    categorised_by_annotator: dict[str, list[CategorisedError]],
    iou_threshold: float = IOU_THRESHOLD,
) -> dict[str, Any]:
    """For each pair of annotators, compute κ on the "real_mt vs false_alarm"
    classification of spans they both flagged (within IoU ≥ threshold of
    each other), excluding spans either annotator scored as a true positive.

    Returns a dict mapping "a1__a2" → {"n_pairs", "kappa", "agreement"}.
    """
    annotators = sorted(categorised_by_annotator)
    out: dict[str, Any] = {}

    for i in range(len(annotators)):
        for j in range(i + 1, len(annotators)):
            a1, a2 = annotators[i], annotators[j]
            errs1 = categorised_by_annotator[a1]
            errs2 = categorised_by_annotator[a2]

            # Group by item for efficient pairing
            by_item_2: dict[str, list[CategorisedError]] = defaultdict(list)
            for e in errs2:
                by_item_2[e.item_id].append(e)

            y1: list[bool] = []
            y2: list[bool] = []
            for e1 in errs1:
                if e1.category == "true_positive":
                    continue
                # Find any e2 on the same item that overlaps e1
                for e2 in by_item_2.get(e1.item_id, []):
                    if e2.category == "true_positive":
                        continue
                    iou = _span_iou(e1.span_start, e1.span_end,
                                    e2.span_start, e2.span_end)
                    if iou >= iou_threshold:
                        y1.append(e1.category == "real_mt_error")
                        y2.append(e2.category == "real_mt_error")
                        break

            n = len(y1)
            agreement = sum(1 for a, b in zip(y1, y2) if a == b) / n if n else 0.0
            kappa_raw = _cohens_kappa(y1, y2) if n else 0.0
            # κ is undefined (NaN) when one rater gives a single label;
            # report None in that case so the JSON stays valid.
            import math as _math
            kappa_clean: float | None = (
                round(kappa_raw, 4)
                if isinstance(kappa_raw, (int, float)) and not _math.isnan(kappa_raw)
                else None
            )
            out[f"{a1}__{a2}"] = {
                "n_paired_fp_spans": n,
                "agreement": round(agreement, 4),
                "kappa": kappa_clean,
            }

    return out


# ── Aggregation + reporting ────────────────────────────────────────────────


def aggregate(
    all_categorised: list[CategorisedError],
    items_by_id: dict[str, AssessmentItem],
) -> dict[str, Any]:
    """Aggregate per-condition and per-category breakdowns."""
    by_condition: dict[str, Counter] = defaultdict(Counter)
    by_human_category: dict[str, Counter] = defaultdict(Counter)
    totals = Counter()

    for ce in all_categorised:
        totals[ce.category] += 1
        item = items_by_id.get(ce.item_id)
        condition = "unknown"
        if item is not None:
            metadata = item.metadata
            pathway = metadata.pathway if metadata else None
            if pathway is not None:
                condition = pathway.value if hasattr(pathway, "value") else str(pathway)
        by_condition[condition][ce.category] += 1
        by_human_category[ce.human_category][ce.category] += 1

    def _rate(d: Counter, key: str) -> float:
        total = sum(d.values())
        return d.get(key, 0) / max(1, total)

    fp_total = totals["real_mt_error"] + totals["genuine_false_alarm"]
    return {
        "totals": dict(totals),
        "n_errors_flagged": sum(totals.values()),
        "fp_total": fp_total,
        "real_mt_rate_among_fps": (
            totals["real_mt_error"] / max(1, fp_total)
        ),
        "by_condition": {
            cond: {
                **dict(counts),
                "n_total": sum(counts.values()),
                "real_mt_rate_among_fps": (
                    counts["real_mt_error"]
                    / max(1, counts["real_mt_error"] + counts["genuine_false_alarm"])
                ),
            }
            for cond, counts in by_condition.items()
        },
        "by_human_category": {
            cat: dict(counts) for cat, counts in by_human_category.items()
        },
    }


def save_results(
    payload: dict[str, Any],
    output_dir: Path | None = None,
) -> Path:
    """Save analysis results as JSON under ``results/track_c/``."""
    ensure_dirs()
    out_dir = output_dir or (RESULTS_DIR / "track_c")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "false_positive_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    logger.info("FP analysis written to %s", out_path)
    return out_path


# ── Top-level runner ────────────────────────────────────────────────────────


async def run_false_positive_analysis(
    batch_path: Path,
    annotations_dir: Path,
    llm_config: dict,
    annotator_ids: list[str] | None = None,
    iou_threshold: float = IOU_THRESHOLD,
    gemba_precompute: bool = True,
    force_refresh_gemba: bool = False,
    extra_batch_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Top-level orchestration: load → pre-compute → categorise → aggregate."""
    items_by_id = load_items_from_batch(batch_path)
    for extra in extra_batch_paths or []:
        for k, v in load_items_from_batch(extra).items():
            items_by_id.setdefault(k, v)

    annotations = load_human_annotations(annotations_dir, annotator_ids)
    if not annotations:
        logger.warning(
            "No annotators found under %s. "
            "Re-run after at least one annotator has saved annotations.",
            annotations_dir,
        )

    # Restrict GEMBA pre-compute to items that an annotator actually touched
    items_touched: dict[str, AssessmentItem] = {}
    for records in annotations.values():
        for rec in records:
            iid = rec.get("item_id")
            if iid in items_by_id:
                items_touched[iid] = items_by_id[iid]

    gemba_by_id: dict[str, list[dict]] = {}
    if gemba_precompute and items_touched:
        gemba_by_id = await precompute_gemba_annotations(
            items_touched, annotations_dir, llm_config, force_refresh_gemba,
        )
    elif not gemba_precompute:
        # Use only what's already cached
        for iid in items_touched:
            cached = _load_gemba_cache(annotations_dir, iid)
            if cached is not None:
                gemba_by_id[iid] = cached
        logger.info("GEMBA cache only: %d / %d items have cached annotations",
                    len(gemba_by_id), len(items_touched))

    per_annotator: dict[str, dict] = {}
    all_categorised: list[CategorisedError] = []
    by_annotator_cats: dict[str, list[CategorisedError]] = {}

    for annotator_id, records in annotations.items():
        stats, categorised = analyse_annotator(
            annotator_id, records, items_by_id, gemba_by_id, iou_threshold,
        )
        per_annotator[annotator_id] = {
            **asdict(stats),
            "true_positive_rate": round(stats.true_positive_rate, 4),
            "false_positive_rate": round(stats.false_positive_rate, 4),
            "real_mt_rate_among_fps": round(stats.real_mt_rate_among_fps, 4),
        }
        all_categorised.extend(categorised)
        by_annotator_cats[annotator_id] = categorised

    aggregate_payload = aggregate(all_categorised, items_by_id)
    pair_agreement = pairwise_fp_agreement(by_annotator_cats, iou_threshold)

    return {
        "iou_threshold": iou_threshold,
        "n_annotators": len(annotations),
        "annotators": sorted(annotations),
        "per_annotator": per_annotator,
        "pairwise_fp_agreement": pair_agreement,
        "aggregate": aggregate_payload,
        "categorised_errors": [asdict(c) for c in all_categorised],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="False-positive categorisation of human annotations "
                    "(annotation-tool spec §6.6).",
    )
    parser.add_argument(
        "--batch-path", type=Path,
        default=RESULTS_DIR / "batch_200.jsonl",
        help="Primary batch file (default: results/batch_200.jsonl).",
    )
    parser.add_argument(
        "--extra-batch", action="append", type=Path, default=[],
        help="Additional batch files to merge (e.g. baseline outputs).",
    )
    parser.add_argument(
        "--annotations-dir", type=Path,
        default=Path("data/annotations"),
        help="Annotations directory (default: data/annotations).",
    )
    parser.add_argument(
        "--annotators", type=str, default=None,
        help="Comma-separated annotator IDs to include "
             "(default: all annotator directories).",
    )
    parser.add_argument(
        "--iou-threshold", type=float, default=IOU_THRESHOLD,
        help=f"IoU threshold for span matching (default: {IOU_THRESHOLD}).",
    )
    parser.add_argument(
        "--no-gemba-precompute", action="store_true",
        help="Skip the GEMBA-MQM pre-compute step (use only cached entries).",
    )
    parser.add_argument(
        "--force-refresh-gemba", action="store_true",
        help="Re-run GEMBA even when a cache entry exists.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be done without running GEMBA or writing results.",
    )
    parser.add_argument(
        "--llm-provider", type=str, default=None)
    parser.add_argument(
        "--llm-model", type=str, default=None)
    args = parser.parse_args()

    config = dict(DEFAULT_LLM_CONFIG)
    if args.llm_provider:
        config["provider"] = args.llm_provider
    if args.llm_model:
        config["model"] = args.llm_model

    annotator_ids = None
    if args.annotators:
        annotator_ids = [a.strip() for a in args.annotators.split(",") if a.strip()]

    if args.dry_run:
        items = load_items_from_batch(args.batch_path)
        annotations = load_human_annotations(args.annotations_dir, annotator_ids)
        n_touched = sum(
            1 for records in annotations.values() for r in records
            if r.get("item_id") in items
        )
        print("=== DRY RUN ===")
        print(f"Batch loaded:        {len(items)} items")
        print(f"Annotators found:    {sorted(annotations)}")
        print(f"Annotation records:  {n_touched}")
        print(f"Would pre-compute:   {'no' if args.no_gemba_precompute else 'yes'}")
        print(f"IoU threshold:       {args.iou_threshold}")
        return

    payload = asyncio.run(run_false_positive_analysis(
        batch_path=args.batch_path,
        annotations_dir=args.annotations_dir,
        llm_config=config,
        annotator_ids=annotator_ids,
        iou_threshold=args.iou_threshold,
        gemba_precompute=not args.no_gemba_precompute,
        force_refresh_gemba=args.force_refresh_gemba,
        extra_batch_paths=list(args.extra_batch),
    ))

    out_path = save_results(payload)
    print(f"FP analysis written to {out_path}")


if __name__ == "__main__":
    main()
