"""Tests for the segment selector pipeline stage."""

import json
import tempfile
from pathlib import Path

from tompe.pipeline.segment_selector import (
    _jaccard_tokens,
    compute_complexity,
    filter_segments,
    load_corpus,
    select_segments,
)


def _make_segment(source: str, target: str = "fr placeholder", origin: str = "europarl") -> dict:
    return {
        "segment_id": f"test-{hash(source) % 10000:04d}",
        "source_text": source,
        "reference_translation": target,
        "source_lang": "en",
        "target_lang": "fr",
        "corpus_origin": origin,
        "domain": "parliamentary",
        "register": "semi-formal",
    }


def test_compute_complexity_bounds():
    # Very short sentence (below 10 tokens) → length_score = 0
    assert compute_complexity("hello world") == 0.0
    # 30 tokens → length_score = 0.5
    text_30 = " ".join(["word"] * 30)
    assert abs(compute_complexity(text_30) - 0.25) < 0.01
    # 50 tokens → length_score = 1.0
    text_50 = " ".join(["word"] * 50)
    assert abs(compute_complexity(text_50) - 0.5) < 0.01
    # With terminology density
    assert compute_complexity(text_50, 0.5) == 0.75


def test_jaccard_tokens():
    assert _jaccard_tokens("the cat sat", "the cat sat") == 1.0
    assert _jaccard_tokens("the cat sat", "the dog sat") >= 0.5
    assert _jaccard_tokens("hello", "goodbye") == 0.0
    assert _jaccard_tokens("", "hello") == 0.0


def test_filter_segments_length():
    segments = [
        _make_segment("short"),  # 1 token — too short
        _make_segment(" ".join(["word"] * 15)),  # 15 tokens — OK
        _make_segment(" ".join(["word"] * 60)),  # 60 tokens — too long
        _make_segment(" ".join(["token"] * 25)),  # 25 tokens — OK
    ]
    filtered = filter_segments(segments, min_tokens=10, max_tokens=50)
    assert len(filtered) == 2


def test_filter_segments_dedup():
    segments = [
        _make_segment("The European Parliament has adopted this important regulation"),
        _make_segment("The European Parliament has adopted this important regulation"),  # exact dup
        _make_segment("Climate change policy requires immediate and coordinated international action"),
    ]
    filtered = filter_segments(segments, min_tokens=1, max_tokens=100)
    assert len(filtered) == 2


def test_load_corpus_from_jsonl(tmp_path: Path):
    corpus_dir = tmp_path / "europarl"
    corpus_dir.mkdir()
    jsonl = corpus_dir / "segments_en_fr.jsonl"

    segments = [
        _make_segment("This is a test sentence with enough tokens to pass."),
        _make_segment("Another sentence for the parallel corpus data file."),
    ]
    with open(jsonl, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg) + "\n")

    loaded = load_corpus(tmp_path, "europarl")
    assert len(loaded) == 2
    assert loaded[0]["source_text"] == segments[0]["source_text"]


def test_select_segments_from_jsonl(tmp_path: Path):
    corpus_dir = tmp_path / "europarl"
    corpus_dir.mkdir()
    jsonl = corpus_dir / "segments_en_fr.jsonl"

    # Generate diverse sentences so dedup doesn't collapse them
    topics = [
        "climate", "trade", "agriculture", "fisheries", "transport",
        "energy", "health", "education", "defense", "budget",
        "environment", "digital", "migration", "security", "culture",
    ]
    segments = [
        _make_segment(
            f"The committee discussed {topics[i % len(topics)]} policy reforms "
            f"during the {2000 + i} session and proposed new amendments to existing legislation."
        )
        for i in range(50)
    ]
    with open(jsonl, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg) + "\n")

    selected = select_segments(corpus_dir=tmp_path, n_segments=10)
    assert len(selected) == 10
    # All should be valid CorpusSegment objects
    for seg in selected:
        assert seg.source_lang == "en"
        assert seg.target_lang == "fr"
        assert seg.corpus_origin == "europarl"
        assert 0 <= seg.complexity_score <= 1


def test_load_missing_corpus(tmp_path: Path):
    loaded = load_corpus(tmp_path, "nonexistent")
    assert loaded == []
