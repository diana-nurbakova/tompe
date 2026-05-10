"""MQM error taxonomy — 10 primary tags × ~37 error types.

Complete mapping matrix from spec v1.1 §3.3, linking each error type to:
- Primary tag and type attribute
- ToM level (cognitive demand for detection)
- Primary skill (S1-S7) and secondary skills
- Severity range (context-dependent, not fixed)
- Typical difficulty level
- Translation direction specificity

This module is the single source of truth for error classification.
"""

from __future__ import annotations

from dataclasses import dataclass

from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel


@dataclass(frozen=True)
class ErrorTypeSpec:
    """Specification for a single error type in the taxonomy."""

    primary_tag: PrimaryTag
    error_type: str  # type attribute value (lowercase_snake_case)
    severity_range: tuple[Severity, ...]  # Plausible severities for this type
    tom_level: TOMLevel
    primary_skill: SkillID
    secondary_skills: tuple[SkillID, ...]  # May be empty
    typical_difficulty: str  # Low, Medium, High, etc.
    direction: str  # "en_fr", "fr_en", "both"


# ============================================================================
# Full mapping matrix — all 37 error types (spec v1.1 §3.3)
# ============================================================================

ERROR_TYPE_SPECS: list[ErrorTypeSpec] = [
    # --- MISTRANSLATION (9 types) ---
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "false_cognate",
        (Severity.MAJOR, Severity.CRITICAL), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "word_sense",
        (Severity.MAJOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (SkillID.S5,), "Medium-High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "number",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (), "Low-Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "entity",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (), "Low-Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "overly_literal",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (SkillID.S6,), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "overtranslation",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_AUTHOR,
        SkillID.S3, (SkillID.S4,), "Medium-High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "undertranslation",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_AUTHOR,
        SkillID.S3, (SkillID.S4,), "Medium-High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "ambiguity",
        (Severity.MAJOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (), "High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "negation",
        (Severity.CRITICAL,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S3, (), "Medium", "both",
    ),

    # --- OMISSION (4 types) ---
    ErrorTypeSpec(
        PrimaryTag.OMISSION, "clause",
        (Severity.MAJOR, Severity.CRITICAL), TOMLevel.FIRST_ORDER_AUTHOR,
        SkillID.S4, (), "Medium-High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.OMISSION, "modifier",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_AUTHOR,
        SkillID.S4, (), "High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.OMISSION, "discourse_marker",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_AUTHOR,
        SkillID.S4, (SkillID.S7,), "High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.OMISSION, "partial",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_AUTHOR,
        SkillID.S4, (), "Medium", "both",
    ),

    # --- ADDITION (3 types) ---
    ErrorTypeSpec(
        PrimaryTag.ADDITION, "hallucination",
        (Severity.MAJOR, Severity.CRITICAL), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S4, (SkillID.S3,), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.ADDITION, "explicitation",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S4, (SkillID.S6,), "High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.ADDITION, "qualifier",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S4, (SkillID.S6,), "High", "both",
    ),

    # --- UNTRANSLATED (1 type) ---
    ErrorTypeSpec(
        PrimaryTag.UNTRANSLATED, "untranslated",
        (Severity.MAJOR, Severity.CRITICAL), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S4, (), "Low", "both",
    ),

    # --- GRAMMAR (7 types) ---
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "agreement_gender",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (), "Low", "en_fr",  # Critical for EN→FR
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "agreement_number",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (), "Low", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "tense",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (SkillID.S3,), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "article",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (), "Low", "fr_en",  # Critical for FR→EN
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "preposition",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (SkillID.S3,), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "word_order",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "relative_pronoun",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S2, (SkillID.S3,), "Medium", "both",
    ),

    # --- TERMINOLOGY (3 types) ---
    ErrorTypeSpec(
        PrimaryTag.TERMINOLOGY, "wrong_term",
        (Severity.MAJOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S5, (SkillID.S3,), "Medium-High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.TERMINOLOGY, "inconsistent",
        (Severity.MINOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S5, (SkillID.S7,), "High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.TERMINOLOGY, "institutional",
        (Severity.MAJOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S5, (), "High", "both",
    ),

    # --- STYLE (4 types) ---
    ErrorTypeSpec(
        PrimaryTag.STYLE, "awkward",
        (Severity.MINOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.STYLE, "unidiomatic",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Medium-High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.STYLE, "register_formal",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Medium", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.STYLE, "register_informal",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Medium", "both",
    ),

    # --- LOCALE (4 types) ---
    ErrorTypeSpec(
        PrimaryTag.LOCALE, "date_format",
        (Severity.MINOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Low", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.LOCALE, "number_format",
        (Severity.MINOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Low", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.LOCALE, "currency_format",
        (Severity.MINOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Low", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.LOCALE, "time_format",
        (Severity.MINOR,), TOMLevel.SECOND_ORDER_READER,
        SkillID.S6, (), "Low", "both",
    ),

    # --- SPELLING (1 type) ---
    ErrorTypeSpec(
        PrimaryTag.SPELLING, "spelling",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S1, (), "Low", "both",
    ),

    # --- PUNCTUATION (1 type) ---
    ErrorTypeSpec(
        PrimaryTag.PUNCTUATION, "punctuation",
        (Severity.MINOR,), TOMLevel.FIRST_ORDER_MACHINE,
        SkillID.S1, (SkillID.S6,), "Low", "both",
    ),

    # --- L3 RECURSIVE / DISCOURSE (5 types) ---
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "anaphora_resolution",
        (Severity.MAJOR, Severity.CRITICAL), TOMLevel.RECURSIVE_MULTI,
        SkillID.S7, (SkillID.S3,), "Very High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.MISTRANSLATION, "discourse_connective",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.RECURSIVE_MULTI,
        SkillID.S7, (SkillID.S3,), "Very High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.GRAMMAR, "tense_sequence",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.RECURSIVE_MULTI,
        SkillID.S7, (SkillID.S2,), "High", "en_fr",
    ),
    ErrorTypeSpec(
        PrimaryTag.TERMINOLOGY, "lexical_cohesion",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.RECURSIVE_MULTI,
        SkillID.S7, (SkillID.S5,), "Very High", "both",
    ),
    ErrorTypeSpec(
        PrimaryTag.STYLE, "information_packaging",
        (Severity.MINOR, Severity.MAJOR), TOMLevel.RECURSIVE_MULTI,
        SkillID.S7, (SkillID.S6,), "Very High", "both",
    ),
]

# ============================================================================
# Lookup indices — built from ERROR_TYPE_SPECS
# ============================================================================

# (primary_tag, error_type) → ErrorTypeSpec
_SPEC_INDEX: dict[tuple[PrimaryTag, str], ErrorTypeSpec] = {
    (s.primary_tag, s.error_type): s for s in ERROR_TYPE_SPECS
}

# primary_tag → list of valid error_type values
TAG_TYPES: dict[PrimaryTag, list[str]] = {}
for _spec in ERROR_TYPE_SPECS:
    TAG_TYPES.setdefault(_spec.primary_tag, []).append(_spec.error_type)

# All valid (tag, type) pairs as a set for fast validation
VALID_TAG_TYPE_PAIRS: frozenset[tuple[str, str]] = frozenset(
    (s.primary_tag.value, s.error_type) for s in ERROR_TYPE_SPECS
)

# ============================================================================
# Annotation color scheme per primary tag (spec v1.1 §4.4, colorblind-safe)
# ============================================================================

TAG_COLORS: dict[PrimaryTag, str] = {
    PrimaryTag.MISTRANSLATION: "#E84855",  # Red — meaning is wrong
    PrimaryTag.OMISSION: "#7B2D8E",  # Purple — something is missing
    PrimaryTag.ADDITION: "#F18F01",  # Orange — something extra
    PrimaryTag.UNTRANSLATED: "#9B2335",  # Dark red — source left in
    PrimaryTag.GRAMMAR: "#2E86AB",  # Blue — structure is wrong
    PrimaryTag.TERMINOLOGY: "#0B7A75",  # Teal — domain term wrong
    PrimaryTag.STYLE: "#8DB580",  # Yellow-green — reads unnaturally
    PrimaryTag.LOCALE: "#A0522D",  # Brown — format is wrong
    PrimaryTag.SPELLING: "#6BAED6",  # Light blue — surface form wrong
    PrimaryTag.PUNCTUATION: "#999999",  # Gray — punctuation issue
}

# Clean segment indicator color (L3 Expert only)
CLEAN_SPAN_COLOR = "#44AF69"  # Green border

# ============================================================================
# MQM severity weights (spec v1.1 Appendix B)
# ============================================================================

SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.MINOR: 1.0,
    Severity.MAJOR: 5.0,
    Severity.CRITICAL: 25.0,
}

# Special weight for minor punctuation errors
PUNCTUATION_MINOR_WEIGHT = 0.1

# ============================================================================
# Human-readable ToM level descriptions for prompts
# ============================================================================

TOM_LEVEL_DESCRIPTIONS: dict[TOMLevel, str] = {
    TOMLevel.FIRST_ORDER_MACHINE: (
        "1st-order Machine ToM: The student must reason about what the MT system "
        "'thought' or how it processed the source text to produce this error."
    ),
    TOMLevel.FIRST_ORDER_AUTHOR: (
        "1st-order Author ToM: The student must understand what the original author "
        "intended to communicate, which the translation fails to convey."
    ),
    TOMLevel.SECOND_ORDER_READER: (
        "2nd-order Reader ToM: The student must consider how a target-language reader "
        "would interpret the erroneous translation and what wrong inference they'd draw."
    ),
    TOMLevel.RECURSIVE_MULTI: (
        "Recursive multi-agent ToM: The student must coordinate reasoning across "
        "multiple perspectives (author intent, MT processing, reader interpretation) "
        "simultaneously."
    ),
}

# ============================================================================
# Public API
# ============================================================================


def get_error_spec(primary_tag: PrimaryTag, error_type: str) -> ErrorTypeSpec:
    """Get the full specification for a (primary_tag, error_type) pair.

    Raises KeyError if the pair is not in the taxonomy.
    """
    return _SPEC_INDEX[(primary_tag, error_type)]


def validate_tag_type(primary_tag: str, error_type: str) -> bool:
    """Check if a (tag, type) pair is valid."""
    return (primary_tag, error_type) in VALID_TAG_TYPE_PAIRS


def get_types_for_tag(primary_tag: PrimaryTag) -> list[str]:
    """Get all valid error_type values for a primary tag."""
    return TAG_TYPES.get(primary_tag, [])


def get_specs_by_skill(skill_id: SkillID) -> list[ErrorTypeSpec]:
    """Get all error types that map to a given primary skill."""
    return [s for s in ERROR_TYPE_SPECS if s.primary_skill == skill_id]


def get_specs_by_tom(tom_level: TOMLevel) -> list[ErrorTypeSpec]:
    """Get all error types at a given ToM level."""
    return [s for s in ERROR_TYPE_SPECS if s.tom_level == tom_level]


def get_specs_by_direction(direction: str) -> list[ErrorTypeSpec]:
    """Get error types relevant for a translation direction.

    Args:
        direction: "en_fr", "fr_en", or "both"

    Returns all types that match the given direction or are "both".
    """
    return [
        s for s in ERROR_TYPE_SPECS
        if s.direction == direction or s.direction == "both"
    ]


def get_color(primary_tag: PrimaryTag) -> str:
    """Get the annotation highlight color for a primary tag."""
    return TAG_COLORS.get(primary_tag, "#999999")
