"""Expert annotation models for pipeline validation (Track C).

Stores per-item annotations from expert annotators and GEMBA-MQM,
enabling three-way agreement analysis (Pipeline x Human x GEMBA).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from tompe.schemas.enums import PrimaryTag, Severity


class AnnotatedError(BaseModel):
    """A single error annotation from the expert annotator."""

    span_start: int  # Character offset in presented_text
    span_end: int
    span_text: str  # Selected text
    category: PrimaryTag  # MQM primary tag
    severity: Severity


class GEMBAAnnotatedError(BaseModel):
    """A single error detected by GEMBA-MQM."""

    span_start: int
    span_end: int
    span_text: str
    category: str  # GEMBA MQM category (may not map 1:1 to PrimaryTag)
    subcategory: str
    severity: str  # "minor", "major", "critical"
    explanation: str
    confidence: Optional[float] = None


class ExpertAnnotation(BaseModel):
    """Full annotation record for one item by one annotator."""

    annotation_id: str
    annotator_id: str
    item_id: str
    item_source: str  # "full_pipeline" | "baseline_B0" | "baseline_B1" |
    #                    "baseline_B2" | "authentic" | "clean"
    tom_level: Optional[int] = None  # Target ToM level (hidden from annotator)
    timestamp_start: datetime
    timestamp_end: datetime
    duration_seconds: float
    errors: list[AnnotatedError]
    no_errors_found: bool  # True if annotator clicked "No Errors Found"
    confidence: str  # "low", "medium", "high"
    notes: Optional[str] = None
    is_practice: bool = False


class GEMBAAnnotation(BaseModel):
    """GEMBA-MQM annotation record for one item (automated)."""

    item_id: str
    overall_quality: str
    overall_score: float
    errors: list[GEMBAAnnotatedError]
    timestamp: datetime


class ExplanationRating(BaseModel):
    """Rating of a generated explanation by the expert annotator (Phase B).

    Three dimensions on a 3-point scale, plus optional free-text comment.
    """

    rating_id: str
    annotator_id: str
    item_id: str  # Links to AssessmentItem
    error_index: int  # Which error in the item (0-indexed)
    tom_level: Optional[int] = None  # ToM level of the error (for analysis)
    factual_accuracy: str  # "incorrect", "partially_correct", "correct"
    pedagogical_clarity: str  # "unclear", "somewhat_clear", "clear"
    completeness: str  # "incomplete", "adequate", "thorough"
    comment: Optional[str] = None  # Optional free text
    timestamp_start: datetime
    timestamp_end: datetime
    duration_seconds: float


class AnnotationSetItem(BaseModel):
    """An item in the annotation set with metadata hidden from the annotator."""

    item_id: str
    source_text: str
    presented_text: str  # Translation to annotate
    reference_translation: str  # Hidden from annotator, used in analysis
    item_source: str  # Hidden from annotator
    tom_level: Optional[int] = None  # Hidden from annotator
    condition: str  # "full_pipeline" | "baseline_B0" | etc.
    display_order: int  # Randomised position
    is_practice: bool = False


class ExplanationReviewItem(BaseModel):
    """An item for Phase B explanation quality review."""

    item_id: str
    error_index: int  # Which error in the item
    source_text: str
    presented_text: str
    error_span_text: str  # The error span highlighted
    error_category: str  # e.g., "MISTRANSLATION"
    error_severity: str  # e.g., "major"
    original_text: str  # Correct text before injection
    tom_level: Optional[int] = None
    layer1_explanation: Optional[dict] = None  # ContrastiveExplanation fields
    layer2a_explanation: Optional[dict] = None  # SystemBehaviorExplanation fields
    display_order: int
