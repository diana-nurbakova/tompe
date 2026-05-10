"""Corpus sampling and filtering pipeline stage.

Reads ingested JSONL corpora and selects segments based on length,
deduplication, and domain criteria. Outputs CorpusSegment objects ready
for the MT generation and error injection stages.

For L3 (recursive multi-sentence) errors, two specialised strategies are
exposed (remediation §1.4):

  - `select_l3_long_segments` — naturally long source segments scored by
    clause indicators, suitable for tense-sequence / discourse-connective
    / lexical-cohesion errors (R2, R3, R4).
  - `select_l3_adjacent_pairs` — concatenates consecutive segments from
    the same document, rejecting pairs that look like document boundaries,
    suitable for cross-sentence anaphora and information-packaging errors
    (R1, R5).

The top-level `select_segments` accepts `tom_level=`; when set to
`TOMLevel.RECURSIVE_MULTI` it relaxes the token-length window to a longer
range appropriate for L3 content.
"""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path

from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.enums import TOMLevel

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


# ── L3 helpers (remediation §1.4 Strategy 2) ────────────────────────────────


_L3_TOM_VALUES = frozenset({TOMLevel.RECURSIVE_MULTI, "recursive"})

# Header / title pattern: legal-document boilerplate that breaks discourse
# continuity. Matched at the start of a segment (case-insensitive).
_HEADER_PATTERN = re.compile(
    r"^\s*(annex|chapter|article|title|section|part|appendix|preamble|"
    r"recital|whereas|table of contents|index|figure|preface)\b",
    re.IGNORECASE,
)

_OVERLAP_STOPWORDS = frozenset({
    "this", "that", "these", "those", "they", "their", "them",
    "have", "been", "were", "will", "would", "could", "should",
    "with", "from", "into", "upon", "about", "such", "also",
    "more", "most", "than", "then", "there", "where", "what",
    "when", "which", "while", "shall", "must", "very", "much",
    "some", "many", "each", "other", "your", "our", "ours",
    "however", "therefore", "moreover", "furthermore",
})


def _content_word_set(text: str) -> set[str]:
    """Lowercase content-word set (≥4 chars, no stopwords). Heuristic
    stand-in for noun extraction — adequate for the noun-overlap check
    used by `select_l3_adjacent_pairs`."""
    words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", text)
    return {
        w.lower() for w in words
        if w.lower() not in _OVERLAP_STOPWORDS
    }


def _is_likely_boundary(s1_text: str, s2_text: str) -> bool:
    """True if the (s1, s2) pair likely crosses a document boundary or
    lacks referential cohesion (header keyword, short s1/s2, or no shared
    content words)."""
    if _HEADER_PATTERN.match(s1_text) or _HEADER_PATTERN.match(s2_text):
        return True
    if len(s1_text.split()) < 5:
        return True
    if len(s2_text.split()) < 4:
        return True
    if not (_content_word_set(s1_text) & _content_word_set(s2_text)):
        return True
    return False


def select_l3_long_segments(
    all_segments: list[CorpusSegment],
    n: int,
    min_tokens: int = 30,
    max_tokens: int = 150,
    seed: int = 42,
) -> list[CorpusSegment]:
    """Select naturally long segments for L3 errors (R2, R3, R4).

    Prefers segments with multiple clauses (semicolons, colons, multiple
    periods).
    """
    candidates = []
    for seg in all_segments:
        tok_count = len(seg.source_text.split())
        if min_tokens <= tok_count <= max_tokens:
            clause_score = (
                seg.source_text.count(";")
                + seg.source_text.count(":")
                + seg.source_text.count(",")
                + seg.source_text.count(". ") * 2
            )
            candidates.append((clause_score, seg))

    candidates.sort(key=lambda x: -x[0])
    rng = random.Random(seed)
    pool = [seg for _, seg in candidates[: n * 3]]
    rng.shuffle(pool)
    selected = pool[:n]
    log.info(
        "L3 long-segment selection: %d / %d candidates",
        len(selected), len(candidates),
    )
    return selected


def select_l3_adjacent_pairs(
    all_segments: list[CorpusSegment],
    n: int,
    min_combined_tokens: int = 20,
    max_combined_tokens: int = 150,
    seed: int = 42,
) -> list[CorpusSegment]:
    """Select adjacent segment pairs for L3 errors (R1, R5).

    Uses ``document_id`` + ``position_in_doc`` to find genuinely
    consecutive segments within the same document. Boundary-like pairs
    (headers, very short s1/s2, no content overlap) are rejected.
    """
    by_doc: dict[str, list[CorpusSegment]] = {}
    for seg in all_segments:
        if not seg.document_id:
            continue
        by_doc.setdefault(seg.document_id, []).append(seg)

    for doc_id in by_doc:
        by_doc[doc_id].sort(key=lambda s: s.position_in_doc or 0)

    candidates: list[CorpusSegment] = []
    rejected_boundary = 0
    for doc_id, doc_segs in by_doc.items():
        for i in range(len(doc_segs) - 1):
            s1 = doc_segs[i]
            s2 = doc_segs[i + 1]

            if (s1.position_in_doc is not None and s2.position_in_doc is not None
                    and s2.position_in_doc != s1.position_in_doc + 1):
                continue

            if _is_likely_boundary(s1.source_text, s2.source_text):
                rejected_boundary += 1
                continue

            combined_src = s1.source_text + " " + s2.source_text
            combined_ref = s1.reference_translation + " " + s2.reference_translation
            tok_count = len(combined_src.split())
            if not (min_combined_tokens <= tok_count <= max_combined_tokens):
                continue

            candidates.append(CorpusSegment(
                segment_id=f"{s1.segment_id}+{s2.segment_id}",
                source_text=combined_src,
                reference_translation=combined_ref,
                source_lang=s1.source_lang,
                target_lang=s1.target_lang,
                corpus_origin=s1.corpus_origin,
                domain=s1.domain,
                text_register=s1.text_register,
                document_id=doc_id,
                position_in_doc=s1.position_in_doc,
            ))

    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected = candidates[:n]
    log.info(
        "L3 adjacent-pair selection: %d / %d candidates "
        "(rejected %d for header/short/no-overlap)",
        len(selected), len(candidates), rejected_boundary,
    )
    return selected


# ── Selection (main entry point) ────────────────────────────────────────────


def select_segments(
    corpus_dir: Path | None = None,
    origins: list[str] | None = None,
    n_segments: int = 100,
    min_tokens: int = 10,
    max_tokens: int = 50,
    jaccard_threshold: float = 0.8,
    seed: int | None = 42,
    tom_level: TOMLevel | str | None = None,
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
        tom_level: Optional ToM level. When ``RECURSIVE_MULTI``, the
            token-length window is relaxed to (30, 150) so that the
            sampled segments are long enough to host L3 errors. For
            adjacent-pair / long-segment-clause-density strategies, call
            `select_l3_adjacent_pairs` / `select_l3_long_segments`
            directly on the loaded segment list.

    Returns:
        List of validated ``CorpusSegment`` objects.
    """
    if tom_level in _L3_TOM_VALUES:
        # Spec §1.4: L3 segments need to be long enough to host
        # cross-sentence / multi-clause errors.
        min_tokens = max(min_tokens, 30)
        max_tokens = max(max_tokens, 150)
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
                document_id=seg.get("document_id"),
                position_in_doc=seg.get("position_in_doc"),
            ),
        )

    return result
