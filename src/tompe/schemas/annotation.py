"""Annotation scaffolding models."""

from typing import Optional

from pydantic import BaseModel

from tompe.schemas.enums import AnnotationLevel


class ErrorAnnotation(BaseModel):
    """Annotation overlay for a single error — visibility depends on scaffolding level."""

    error_id: str  # FK to InjectedError
    span_start: int
    span_end: int

    # Level 0 (Navigator): ALL fields visible
    highlight_color: str  # Visual cue mapped to MQM category
    mqm_label: str  # "Accuracy > Mistranslation"
    severity_label: str  # "Major"
    tom_perspective_hint: str  # "Think about what the MT system understood"
    guiding_question: str  # "Does this phrase match the source meaning?"

    # Level 1 (Guided): Only these fields visible
    region_highlight: bool = True
    hint_text: Optional[str] = None  # "There may be an accuracy issue here"


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


# MQM Category → Annotation Color Mapping
MQM_COLORS: dict[str, str] = {
    "accuracy": "#E74C3C",  # Red — critical meaning errors
    "fluency": "#3498DB",  # Blue — language form errors
    "terminology": "#9B59B6",  # Purple — domain-specific
    "style": "#E67E22",  # Orange — subjective/register
    "locale": "#95A5A6",  # Gray — convention-based
}
