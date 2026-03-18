"""Corpus sampling and filtering pipeline stage.

Reads ingested JSONL corpora and selects segments based on length,
deduplication, and domain criteria. Outputs CorpusSegment objects ready
for the MT generation and error injection stages.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from tompe.schemas.corpus import CorpusSegment

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CORPORA_DIR = PROJECT_ROOT / "data" / "corpora"


# ── Loading ─────────────────────────────────────────────────────────────────


def load_corpus(corpus_dir: Path, origin: str) -> list[dict]:
    """Load raw parallel segments from a corpus JSONL file.

    Looks for ``{corpus_dir}/{origin}/segments_en_fr.jsonl``.
    """
    jsonl_path = corpus_dir / origin / "segments_en_fr.jsonl"
    if not jsonl_path.exists():
        log.warning("No JSONL file for corpus '%s' at %s", origin, jsonl_path)
        return []

    segments: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(json.loads(line))

    log.info("Loaded %d raw segments from %s", len(segments), origin)
    return segments


# ── Metrics ─────────────────────────────────────────────────────────────────


def compute_complexity(source_text: str, terminology_density: float = 0.0) -> float:
    """Compute complexity score from sentence length and terminology density.

    Returns a float in [0, 1].
    """
    token_count = len(source_text.split())
    # Normalize token count to 0-1 range (10-50 token window)
    length_score = min(max((token_count - 10) / 40, 0.0), 1.0)
    return (length_score + terminology_density) / 2


def _jaccard_tokens(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


# ── Filtering ───────────────────────────────────────────────────────────────


def filter_segments(
    segments: list[dict],
    min_tokens: int = 10,
    max_tokens: int = 50,
    jaccard_threshold: float = 0.8,
) -> list[dict]:
    """Apply selection criteria: token-length window and near-duplicate removal.

    Args:
        segments: Raw segment dicts (from JSONL).
        min_tokens: Minimum source-side token count (inclusive).
        max_tokens: Maximum source-side token count (inclusive).
        jaccard_threshold: Jaccard similarity above which a segment is
            considered a near-duplicate and dropped.
    """
    # 1) Length filter
    length_ok: list[dict] = []
    for seg in segments:
        n_tokens = len(seg["source_text"].split())
        if min_tokens <= n_tokens <= max_tokens:
            length_ok.append(seg)

    log.info(
        "Length filter (%d-%d tokens): %d → %d segments",
        min_tokens,
        max_tokens,
        len(segments),
        len(length_ok),
    )

    # 2) Near-duplicate removal using token-set fingerprinting.
    #    First pass: exact-set dedup (O(n), catches most duplicates).
    #    Second pass: Jaccard on a random sample if needed.
    seen_fingerprints: set[frozenset[str]] = set()
    deduped: list[dict] = []
    for seg in length_ok:
        fp = frozenset(seg["source_text"].lower().split())
        if fp not in seen_fingerprints:
            seen_fingerprints.add(fp)
            deduped.append(seg)

    log.info(
        "Deduplication (exact token-set): %d → %d segments",
        len(length_ok),
        len(deduped),
    )
    return deduped


# ── Selection (main entry point) ────────────────────────────────────────────


def select_segments(
    corpus_dir: Path | None = None,
    origins: list[str] | None = None,
    n_segments: int = 100,
    min_tokens: int = 10,
    max_tokens: int = 50,
    jaccard_threshold: float = 0.8,
    seed: int | None = 42,
) -> list[CorpusSegment]:
    """Load, filter, and sample corpus segments.

    Args:
        corpus_dir: Root corpora directory (default: ``data/corpora/``).
        origins: Corpus names to include (default: all available).
        n_segments: Total number of segments to return (stratified across origins).
        min_tokens: Minimum source-side tokens.
        max_tokens: Maximum source-side tokens.
        jaccard_threshold: Deduplication threshold.
        seed: Random seed for reproducible sampling.

    Returns:
        List of validated ``CorpusSegment`` objects.
    """
    if corpus_dir is None:
        corpus_dir = DEFAULT_CORPORA_DIR

    if origins is None:
        # Auto-detect: any subdirectory with a segments file
        origins = [
            d.name
            for d in corpus_dir.iterdir()
            if d.is_dir() and (d / "segments_en_fr.jsonl").exists()
        ]

    if not origins:
        log.warning("No corpora found in %s", corpus_dir)
        return []

    # Load and filter per corpus
    per_corpus: dict[str, list[dict]] = {}
    for origin in origins:
        raw = load_corpus(corpus_dir, origin)
        if raw:
            per_corpus[origin] = filter_segments(
                raw,
                min_tokens=min_tokens,
                max_tokens=max_tokens,
                jaccard_threshold=jaccard_threshold,
            )

    total_available = sum(len(v) for v in per_corpus.values())
    if total_available == 0:
        log.warning("No segments remaining after filtering")
        return []

    # Stratified sampling: proportional to each corpus's filtered size
    rng = random.Random(seed)
    sampled: list[dict] = []
    for origin, segs in per_corpus.items():
        quota = max(1, round(n_segments * len(segs) / total_available))
        quota = min(quota, len(segs))
        sampled.extend(rng.sample(segs, quota))

    # Trim to exact count if rounding gave us extra
    if len(sampled) > n_segments:
        sampled = rng.sample(sampled, n_segments)

    rng.shuffle(sampled)

    log.info(
        "Selected %d segments from %d corpora (%d available after filtering)",
        len(sampled),
        len(per_corpus),
        total_available,
    )

    # Convert to CorpusSegment models
    result: list[CorpusSegment] = []
    for seg in sampled:
        complexity = compute_complexity(seg["source_text"])
        result.append(
            CorpusSegment(
                segment_id=seg["segment_id"],
                source_text=seg["source_text"],
                reference_translation=seg["reference_translation"],
                source_lang=seg.get("source_lang", "en"),
                target_lang=seg.get("target_lang", "fr"),
                corpus_origin=seg["corpus_origin"],
                domain=seg.get("domain", "general"),
                complexity_score=complexity,
                terminology_density=0.0,  # Set later by IATE lookup
                text_register=seg.get("register", "formal"),
            ),
        )

    return result
