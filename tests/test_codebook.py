"""Tests for the codebook loader and query functions."""

from pathlib import Path

from tompe.pipeline.codebook import Codebook, load_codebook

# Path to the seed codebook
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "codebook"
_CODEBOOK_PATH = _DATA_DIR / "error_codebook_fr_en.json"
_SCHEMA_PATH = _DATA_DIR / "tag_schema.json"


def test_load_codebook():
    """Should load the seed codebook without errors."""
    codebook = load_codebook(_CODEBOOK_PATH, _SCHEMA_PATH)
    assert codebook.entry_count == 3  # 3 seed entries


def test_codebook_example_count():
    """Should have the expected number of examples."""
    codebook = load_codebook(_CODEBOOK_PATH)
    # false_cognate: 3, agreement_gender: 2, omission/clause: 2 = 7 total
    assert codebook.example_count == 7


def test_get_entry():
    """Should retrieve a specific entry by tag and type."""
    codebook = load_codebook(_CODEBOOK_PATH)
    entry = codebook.get_entry("MISTRANSLATION", "false_cognate")
    assert entry is not None
    assert entry.codebook_id == "ACC-MIST-FC-001"
    assert entry.primary_skill == "S3"
    assert "cognate" in entry.definition.lower()


def test_get_entry_missing():
    """Should return None for unknown tag/type pair."""
    codebook = load_codebook(_CODEBOOK_PATH)
    entry = codebook.get_entry("MISTRANSLATION", "nonexistent")
    assert entry is None


def test_get_entries_by_tag():
    """Should return all entries for a given tag."""
    codebook = load_codebook(_CODEBOOK_PATH)
    entries = codebook.get_entries_by_tag("MISTRANSLATION")
    assert len(entries) == 1  # Only false_cognate in seed


def test_get_few_shot_examples():
    """Should return examples for a specific error type."""
    codebook = load_codebook(_CODEBOOK_PATH)
    examples = codebook.get_few_shot_examples("MISTRANSLATION", "false_cognate")
    assert len(examples) == 3
    assert "assisting" in examples[0].injected.lower() or "sensible" in examples[0].injected.lower()


def test_get_few_shot_examples_with_direction():
    """Should filter examples by direction."""
    codebook = load_codebook(_CODEBOOK_PATH)
    examples = codebook.get_few_shot_examples(
        "GRAMMAR", "agreement_gender", direction="en_to_fr"
    )
    assert len(examples) == 2
    for ex in examples:
        assert ex.direction == "en_to_fr"


def test_get_few_shot_examples_fallback():
    """Should fall back to tag-level examples for unknown type."""
    codebook = load_codebook(_CODEBOOK_PATH)
    examples = codebook.get_few_shot_examples("MISTRANSLATION", "word_sense")
    # Should fall back to false_cognate examples
    assert len(examples) > 0


def test_validate_tag_type_with_schema():
    """Should validate against the tag schema."""
    codebook = load_codebook(_CODEBOOK_PATH, _SCHEMA_PATH)
    assert codebook.validate_tag_type("MISTRANSLATION", "false_cognate") is True
    assert codebook.validate_tag_type("GRAMMAR", "agreement_gender") is True
    assert codebook.validate_tag_type("MISTRANSLATION", "nonexistent") is False
    assert codebook.validate_tag_type("NONEXISTENT", "test") is False


def test_get_definition():
    """Should return the definition for an error type."""
    codebook = load_codebook(_CODEBOOK_PATH)
    defn = codebook.get_definition("OMISSION", "clause")
    assert "subordinate clause" in defn.lower()


def test_get_boundary_not():
    """Should return the boundary disambiguation text."""
    codebook = load_codebook(_CODEBOOK_PATH)
    boundary = codebook.get_boundary_not("MISTRANSLATION", "false_cognate")
    assert "word_sense" in boundary.lower()


def test_load_missing_codebook():
    """Should return empty codebook for nonexistent path."""
    codebook = load_codebook("/nonexistent/path/codebook.json")
    assert codebook.entry_count == 0
    assert codebook.example_count == 0


def test_codebook_all_tags():
    """Should list all tags with entries."""
    codebook = load_codebook(_CODEBOOK_PATH)
    tags = codebook.all_tags
    assert "MISTRANSLATION" in tags
    assert "GRAMMAR" in tags
    assert "OMISSION" in tags
