"""Corpus sampling and filtering pipeline stage.

Selects segments from EU/UN parallel corpora based on length, alignment quality,
terminology density, domain, and complexity criteria.
"""

from pathlib import Path

from tompe.schemas.corpus import CorpusSegment


def load_corpus(corpus_dir: Path, origin: str) -> list[dict]:
    """Load raw parallel segments from a corpus directory."""
    raise NotImplementedError


def compute_complexity(source_text: str, terminology_density: float) -> float:
    """Compute complexity score from sentence length and terminology density."""
    token_count = len(source_text.split())
    # Normalize token count to 0-1 range (10-50 token window)
    length_score = min(max((token_count - 10) / 40, 0.0), 1.0)
    return (length_score + terminology_density) / 2


def filter_segments(
    segments: list[dict],
    min_tokens: int = 10,
    max_tokens: int = 50,
    jaccard_threshold: float = 0.8,
) -> list[dict]:
    """Apply selection criteria: length, alignment, deduplication."""
    raise NotImplementedError


def select_segments(
    corpus_dir: Path,
    origins: list[str],
    n_segments: int = 100,
) -> list[CorpusSegment]:
    """Main entry point: load, filter, and sample corpus segments."""
    raise NotImplementedError
