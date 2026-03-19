"""Tests for the error injection module (v1.1 — two-step, XML-based).

Unit tests only — no API calls. Tests XML parsing, verification logic,
error planning, and profile handling.
"""

import random

import pytest

from tompe.pipeline.error_injector import (
    ErrorProfile,
    _parse_xml_tags,
    _plan_errors,
    _strip_xml_tags,
    _verify_injection,
    _get_span_positions,
)
from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel


# ============================================================================
# ErrorProfile tests
# ============================================================================

def test_error_profile_creation():
    """ErrorProfile should store all parameters."""
    profile = ErrorProfile(
        primary_tags=[PrimaryTag.MISTRANSLATION, PrimaryTag.GRAMMAR],
        severity_distribution={Severity.MINOR: 1, Severity.MAJOR: 2},
        tom_levels=[TOMLevel.FIRST_ORDER_MACHINE],
        direction="en_fr",
        use_few_shot=True,
    )
    assert len(profile.primary_tags) == 2
    assert profile.severity_distribution[Severity.MAJOR] == 2
    assert profile.direction == "en_fr"


def test_error_profile_defaults():
    """ErrorProfile should have sensible defaults."""
    profile = ErrorProfile(
        primary_tags=[PrimaryTag.MISTRANSLATION],
        severity_distribution={Severity.MAJOR: 1},
    )
    assert profile.tom_levels is None
    assert profile.direction == "both"
    assert profile.use_few_shot is True


# ============================================================================
# _plan_errors tests
# ============================================================================

def test_plan_errors_count():
    """Should produce correct number of error specs."""
    random.seed(42)
    profile = ErrorProfile(
        primary_tags=[PrimaryTag.MISTRANSLATION, PrimaryTag.GRAMMAR],
        severity_distribution={Severity.MINOR: 1, Severity.MAJOR: 2},
    )
    specs = _plan_errors(profile)
    assert len(specs) == 3


def test_plan_errors_tags_from_profile():
    """Planned errors should use tags from the profile only."""
    random.seed(42)
    profile = ErrorProfile(
        primary_tags=[PrimaryTag.TERMINOLOGY],
        severity_distribution={Severity.MAJOR: 5},
    )
    specs = _plan_errors(profile)
    for spec in specs:
        assert spec.primary_tag == PrimaryTag.TERMINOLOGY


def test_plan_errors_empty():
    """Zero-count distribution should produce nothing."""
    profile = ErrorProfile(
        primary_tags=[PrimaryTag.MISTRANSLATION],
        severity_distribution={Severity.MINOR: 0},
    )
    specs = _plan_errors(profile)
    assert len(specs) == 0


def test_plan_errors_direction_filter():
    """Direction filter should exclude direction-specific types."""
    random.seed(42)
    profile = ErrorProfile(
        primary_tags=[PrimaryTag.GRAMMAR],
        severity_distribution={Severity.MINOR: 20},
        direction="en_fr",
    )
    specs = _plan_errors(profile)
    # Should not include fr_en-only types like 'article'
    for spec in specs:
        assert spec.direction != "fr_en", f"Got fr_en type: {spec.error_type}"


# ============================================================================
# XML parsing tests
# ============================================================================

def test_parse_xml_tags_basic():
    """Should parse a single well-formed XML tag."""
    text = (
        'He has been <MISTRANSLATION type="false_cognate" severity="major" '
        'tom="1st_machine" desc="assister à ≠ assist; means attend">'
        'assisting at</MISTRANSLATION> the conference.'
    )
    tags = _parse_xml_tags(text)
    assert len(tags) == 1
    assert tags[0]["tag_name"] == "MISTRANSLATION"
    assert tags[0]["type"] == "false_cognate"
    assert tags[0]["severity"] == "major"
    assert tags[0]["tom"] == "1st_machine"
    assert tags[0]["span_text"] == "assisting at"


def test_parse_xml_tags_grammar():
    """Should parse GRAMMAR tags."""
    text = (
        'Elle est <GRAMMAR type="agreement_gender" severity="major" '
        'tom="1st_machine" desc="past participle must agree with elle">'
        'allé</GRAMMAR> à Paris hier.'
    )
    tags = _parse_xml_tags(text)
    assert len(tags) == 1
    assert tags[0]["tag_name"] == "GRAMMAR"
    assert tags[0]["type"] == "agreement_gender"
    assert tags[0]["span_text"] == "allé"


def test_parse_xml_tags_no_tags():
    """Text without tags should return empty list."""
    tags = _parse_xml_tags("Just plain text with no errors.")
    assert len(tags) == 0


def test_strip_xml_tags():
    """Should remove tags but keep the error span content."""
    text = (
        'He has been <MISTRANSLATION type="false_cognate" severity="major" '
        'tom="1st_machine" desc="test">assisting at</MISTRANSLATION> the conference.'
    )
    clean = _strip_xml_tags(text)
    assert clean == "He has been assisting at the conference."


def test_get_span_positions():
    """Should compute correct character offsets in clean text."""
    text = (
        'He has been <MISTRANSLATION type="false_cognate" severity="major" '
        'tom="1st_machine" desc="test">assisting at</MISTRANSLATION> the conference.'
    )
    tags = _parse_xml_tags(text)
    span_start, span_end = _get_span_positions(text, tags[0])
    clean = _strip_xml_tags(text)
    assert clean[span_start:span_end] == "assisting at"


# ============================================================================
# _verify_injection tests
# ============================================================================

def test_verify_valid_injection():
    """A well-formed injection should pass verification."""
    reference = "He has been attending the conference since this morning."
    response = {
        "injected_translation": (
            'He has been <MISTRANSLATION type="false_cognate" severity="major" '
            'tom="1st_machine" desc="assister à means attend not assist">'
            'assisting at</MISTRANSLATION> the conference since this morning.'
        ),
        "error_span_text": "assisting at",
        "original_span_text": "attending",
        "explanation": {
            "mt_interpretation": "The MT mapped assiste à to assist at due to surface similarity.",
            "actual_meaning": "In French assister à means to attend or be present at.",
            "reader_impact": "A reader would think the subject is helping not attending.",
            "correction_rationale": "Assister à translates to attend not assist.",
        },
    }
    errors = _verify_injection(reference, response)
    assert errors == [], f"Unexpected errors: {errors}"


def test_verify_no_xml_tag():
    """Missing XML tag should fail."""
    response = {
        "injected_translation": "Just plain text with no tags.",
        "error_span_text": "test",
        "original_span_text": "test",
        "explanation": {
            "mt_interpretation": "x" * 20,
            "actual_meaning": "x" * 20,
            "reader_impact": "x" * 20,
            "correction_rationale": "x" * 20,
        },
    }
    errors = _verify_injection("Just plain text.", response)
    assert any("No valid XML" in e for e in errors)


def test_verify_invalid_tag_type():
    """Invalid tag/type pair should fail."""
    reference = "Test text here."
    response = {
        "injected_translation": (
            '<MISTRANSLATION type="agreement_gender" severity="major" '
            'tom="1st_machine" desc="wrong type for this tag">bad</MISTRANSLATION> text here.'
        ),
        "error_span_text": "bad",
        "original_span_text": "Test",
        "explanation": {
            "mt_interpretation": "The MT system did something wrong here.",
            "actual_meaning": "The source actually means something else here.",
            "reader_impact": "A reader would be confused by this translation.",
            "correction_rationale": "The correct translation should be different here.",
        },
    }
    errors = _verify_injection(reference, response)
    assert any("Invalid tag/type" in e for e in errors)


def test_verify_no_actual_change():
    """Same span text as original should fail."""
    reference = "The translation is correct."
    response = {
        "injected_translation": (
            '<MISTRANSLATION type="false_cognate" severity="major" '
            'tom="1st_machine" desc="this should be different">correct</MISTRANSLATION>.'
        ),
        "error_span_text": "correct",
        "original_span_text": "correct",
        "explanation": {
            "mt_interpretation": "The MT system did something wrong here.",
            "actual_meaning": "The source actually means something else here.",
            "reader_impact": "A reader would be confused by this translation.",
            "correction_rationale": "The correct translation should be different here.",
        },
    }
    errors = _verify_injection(reference, response)
    assert any("No actual change" in e for e in errors)


def test_verify_short_explanation():
    """Explanation fields that are too short should fail."""
    reference = "He attended the conference."
    response = {
        "injected_translation": (
            'He <MISTRANSLATION type="false_cognate" severity="major" '
            'tom="1st_machine" desc="false cognate error">assisted at</MISTRANSLATION> '
            'the conference.'
        ),
        "error_span_text": "assisted at",
        "original_span_text": "attended",
        "explanation": {
            "mt_interpretation": "Short",  # Too short
            "actual_meaning": "Also short",  # Too short
            "reader_impact": "Tiny",
            "correction_rationale": "Brief",
        },
    }
    errors = _verify_injection(reference, response)
    assert any("too short" in e for e in errors)
