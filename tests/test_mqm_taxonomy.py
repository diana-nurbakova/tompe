"""Tests for the MQM taxonomy module (v1.1 — 10 tags × ~37 types)."""

from tompe.pipeline.mqm_taxonomy import (
    ERROR_TYPE_SPECS,
    TAG_COLORS,
    VALID_TAG_TYPE_PAIRS,
    get_color,
    get_error_spec,
    get_specs_by_direction,
    get_specs_by_skill,
    get_specs_by_tom,
    get_types_for_tag,
    validate_tag_type,
)
from tompe.schemas.enums import PrimaryTag, SkillID, TOMLevel


def test_total_error_types():
    """Should have 37 error types in the mapping matrix."""
    assert len(ERROR_TYPE_SPECS) == 37


def test_all_primary_tags_have_types():
    """Every PrimaryTag must have at least one error type."""
    for tag in PrimaryTag:
        types = get_types_for_tag(tag)
        assert len(types) > 0, f"No types for {tag.value}"


def test_all_specs_have_required_fields():
    """Every ErrorTypeSpec must have all required fields populated."""
    for spec in ERROR_TYPE_SPECS:
        assert spec.primary_tag is not None
        assert spec.error_type
        assert len(spec.severity_range) > 0
        assert spec.tom_level is not None
        assert spec.primary_skill is not None
        assert spec.typical_difficulty
        assert spec.direction in ("en_fr", "fr_en", "both")


def test_validate_tag_type_valid():
    """Valid (tag, type) pairs should pass validation."""
    assert validate_tag_type("MISTRANSLATION", "false_cognate")
    assert validate_tag_type("GRAMMAR", "agreement_gender")
    assert validate_tag_type("OMISSION", "clause")
    assert validate_tag_type("SPELLING", "spelling")


def test_validate_tag_type_invalid():
    """Invalid pairs should fail."""
    assert not validate_tag_type("MISTRANSLATION", "agreement_gender")
    assert not validate_tag_type("GRAMMAR", "false_cognate")
    assert not validate_tag_type("NONEXISTENT", "test")


def test_get_error_spec():
    """Should return the correct spec for known pairs."""
    spec = get_error_spec(PrimaryTag.MISTRANSLATION, "false_cognate")
    assert spec.tom_level == TOMLevel.FIRST_ORDER_MACHINE
    assert spec.primary_skill == SkillID.S3

    spec = get_error_spec(PrimaryTag.GRAMMAR, "agreement_gender")
    assert spec.primary_skill == SkillID.S2
    assert spec.direction == "en_fr"


def test_get_error_spec_invalid():
    """Should raise KeyError for unknown pairs."""
    try:
        get_error_spec(PrimaryTag.MISTRANSLATION, "nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_tag_colors_completeness():
    """Every PrimaryTag must have a color."""
    for tag in PrimaryTag:
        assert tag in TAG_COLORS, f"Missing color for {tag.value}"
        assert TAG_COLORS[tag].startswith("#")


def test_get_specs_by_skill():
    """Should return all types for a given primary skill."""
    s2_specs = get_specs_by_skill(SkillID.S2)
    assert all(s.primary_skill == SkillID.S2 for s in s2_specs)
    # S2 = Grammar → should have 7 types
    assert len(s2_specs) == 7


def test_get_specs_by_tom():
    """Should return all types at a given ToM level."""
    machine_specs = get_specs_by_tom(TOMLevel.FIRST_ORDER_MACHINE)
    assert all(s.tom_level == TOMLevel.FIRST_ORDER_MACHINE for s in machine_specs)
    assert len(machine_specs) > 0


def test_get_specs_by_direction():
    """Should return types matching a direction."""
    en_fr = get_specs_by_direction("en_fr")
    # Should include en_fr-specific AND "both" types
    assert any(s.direction == "en_fr" for s in en_fr)
    assert any(s.direction == "both" for s in en_fr)
    # Should not include fr_en-only types
    assert all(s.direction != "fr_en" for s in en_fr)


def test_direction_specific_types():
    """Certain types should be direction-specific per spec §1.2.2."""
    gender = get_error_spec(PrimaryTag.GRAMMAR, "agreement_gender")
    assert gender.direction == "en_fr"

    article = get_error_spec(PrimaryTag.GRAMMAR, "article")
    assert article.direction == "fr_en"


def test_valid_tag_type_pairs_count():
    """Should have 37 valid pairs."""
    assert len(VALID_TAG_TYPE_PAIRS) == 37


def test_mistranslation_types():
    """MISTRANSLATION should have 9 type attributes."""
    types = get_types_for_tag(PrimaryTag.MISTRANSLATION)
    assert len(types) == 9
    assert "false_cognate" in types
    assert "negation" in types
