"""Student response models."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from tompe.schemas.enums import ComparisonType, MQMCategory, Severity, TOMLevel


class IdentifiedError(BaseModel):
    span_start: int
    span_end: int
    student_mqm_category: MQMCategory
    student_severity: Severity
    confidence: Literal["low", "medium", "high"]


class VerificationResponse(BaseModel):
    """Navigator level: student verifies pre-annotated errors."""

    error_id: str
    agrees_is_error: bool
    student_classification: Optional[MQMCategory] = None
    suggested_correction: Optional[str] = None


class SystemRanking(BaseModel):
    """Comparison Skill B: student ranks MT outputs holistically."""

    mt_system: str
    rank: int  # 1 = best
    rationale: str


class PerSystemEvaluation(BaseModel):
    """Comparison Skill A: student evaluates each system independently."""

    mt_system: str
    identified_errors: list[IdentifiedError]
    overall_quality: Literal["good", "acceptable", "poor"]
    cross_system_note: Optional[str] = None


class PEWorthinessVerdict(BaseModel):
    """Professional triage decision: is this MT output worth post-editing?"""

    verdict: Literal["pe_light", "pe_full", "retranslate"]
    rationale: str
    estimated_effort: Literal["low", "medium", "high"]


class Justification(BaseModel):
    """Student-generated ToM reasoning."""

    error_id: Optional[str] = None
    format: Literal["free_text", "structured", "per_error_short", "per_error_structured"]

    # Free-text format (global or per-error short)
    text: Optional[str] = None

    # Structured format (guided ToM prompts)
    mt_misunderstanding: Optional[str] = None
    author_intent: Optional[str] = None
    reader_impact: Optional[str] = None
    tom_perspective: Optional[TOMLevel] = None

    # Adaptive prompt that was shown to the student
    prompt_shown: Optional[str] = None


class StudentResponse(BaseModel):
    response_id: str
    session_id: str
    item_id: str
    student_id: str
    mode: Literal["evaluation", "postediting", "navigator", "comparison"]
    timestamp: datetime
    time_spent_seconds: float

    # Evaluation mode
    identified_errors: Optional[list[IdentifiedError]] = None

    # Post-editing mode
    edited_text: Optional[str] = None

    # Navigator mode (Level 0)
    verification_responses: Optional[list[VerificationResponse]] = None

    # Comparison mode
    comparison_type: Optional[ComparisonType] = None
    per_system_evaluations: Optional[list[PerSystemEvaluation]] = None
    system_rankings: Optional[list[SystemRanking]] = None
    pe_worthiness: Optional[dict[str, PEWorthinessVerdict]] = None

    # Justification (required before seeing feedback)
    justification_format: Literal[
        "free_text", "structured", "both",  # legacy
        "none", "per_error_short", "per_error_structured", "global_free_text",
    ] = "per_error_short"
    justifications: list[Justification] = []
