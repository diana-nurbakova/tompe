"""Error manifest models — core of the controlled environment."""

from typing import Optional

from pydantic import BaseModel

from tompe.schemas.enums import MQMCategory, Severity, TOMLevel


class ContrastiveExplanation(BaseModel):
    """Layer 1: Error-specific ToM-informed contrastive explanation."""

    mt_interpretation: str  # "The MT system likely interpreted X as..."
    actual_meaning: str  # "The source actually means..."
    reader_impact: str  # "A target reader would understand this as..."
    correction_rationale: str  # "The correct translation is Y because..."


class SystemBehaviorExplanation(BaseModel):
    """Layer 2: Educational explanation of WHY MT systems make this type of error."""

    error_mechanism: str  # "NMT systems commonly make this error because..."
    architectural_cause: str  # "This relates to how transformers process..."
    pattern_generalization: str  # "You can expect similar errors when you see..."
    mt_system_specific: Optional[str] = None  # "General-purpose LLMs additionally tend to..."


class InjectedError(BaseModel):
    error_id: str
    span_start: int  # Character offset in modified text
    span_end: int
    original_text: str  # What was there before injection
    injected_text: str  # What replaced it
    mqm_category: MQMCategory
    mqm_subcategory: str  # Specific MQM issue type
    severity: Severity
    tom_level: TOMLevel
    explanation: ContrastiveExplanation


class DetectedError(BaseModel):
    """Error detected in authentic MT output (not injected)."""

    span_start: int
    span_end: int
    mqm_category: MQMCategory
    mqm_subcategory: str
    severity: Severity
    tom_level: TOMLevel
    detection_confidence: float
    explanation: ContrastiveExplanation
    system_behavior: SystemBehaviorExplanation
    human_validated: bool = False


class AuthenticErrorDetection(BaseModel):
    """For authentic pathway: errors found by comparing MT output to reference."""

    detection_method: str  # "xcomet", "gemba_mqm", "human_expert"
    mt_output: str
    reference: str
    detected_errors: list[DetectedError]
    confidence_score: float
