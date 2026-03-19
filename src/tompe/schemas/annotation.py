"""Annotation scaffolding models.

Defines the annotation data model consumed by the student interface at
each scaffolding level (L0-L3). From spec v1.1 §4.2-4.4.
"""

from typing import Optional

from pydantic import BaseModel

from tompe.schemas.enums import (
    AnnotationLevel,
    PrimaryTag,
    Severity,
    SkillID,
    TOMLevel,
)


class RegionHint(BaseModel):
    """Approximate location hint for L1 Guided level.

    Deliberately imprecise — marks a region wider than the actual error span,
    so the student must identify the exact error within the region.
    """

    hint_start: int  # Wider than actual span (approx -10 chars)
    hint_end: int  # Wider than actual span (approx +10 chars)
    hint_label: str  # e.g., "Look for an accuracy issue in this region"


class ErrorAnnotation(BaseModel):
    """Complete annotation for one error in an item.

    Different fields are revealed at different scaffolding levels (L0-L3).
    From spec v1.1 §4.2.
    """

    # === Always stored (ground truth) ===
    error_id: str
    span_start: int  # Character offset in target text
    span_end: int
    span_text: str  # The error span content
    original_text: str  # What should be there (reference)

    # === Error classification ===
    primary_tag: PrimaryTag  # e.g., MISTRANSLATION
    error_type: str  # e.g., false_cognate
    severity: Severity
    tom_level: TOMLevel
    primary_skill: SkillID  # S1-S7
    secondary_skills: list[SkillID] = []

    # === Annotation display metadata ===
    highlight_color: str  # Computed from primary_tag via TAG_COLORS

    # === L0 Navigator: additional fields ===
    mqm_label: str = ""  # "Accuracy > Mistranslation"
    severity_label: str = ""  # "Major"
    tom_perspective_hint: str = ""  # "Think about what the MT system understood"
    guiding_question: str = ""  # "Does this phrase match the source meaning?"

    # === L1 Guided: region hint ===
    region_hint: Optional[RegionHint] = None

    # === Explanation layers (revealed after student justification) ===
    # These are stored but NOT shown until after submission (cognitive forcing)
    # Layer 1 and Layer 2 explanations are on the InjectedError/DetectedError model


class AnnotationConfig(BaseModel):
    """Per-exercise annotation configuration set by teacher."""

    level: AnnotationLevel
    show_mqm_labels: bool = False  # Level 0 only
    show_severity: bool = False  # Level 0 only
    show_tom_hints: bool = False  # Level 0 only
    show_guiding_questions: bool = False  # Level 0 only
    show_region_highlights: bool = False  # Level 0 + 1
    show_hint_text: bool = False  # Level 1 only
    include_clean_spans: bool = False  # Level 2+, required at Level 3
    include_multi_system: bool = False  # Level 3 only
