"""Error manifest models — core of the controlled environment.

Updated for spec v1.1: primary tags, skills, severity ranges, Layer 2a/2b split.
"""

from typing import Optional

from pydantic import BaseModel

from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel


class ContrastiveExplanation(BaseModel):
    """Layer 1: Error-specific ToM-informed contrastive explanation."""

    mt_interpretation: str  # "The MT system likely interpreted X as..."
    actual_meaning: str  # "The source actually means..."
    reader_impact: str  # "A target reader would understand this as..."
    correction_rationale: str  # "The correct translation is Y because..."


class SystemBehaviorExplanation(BaseModel):
    """Layer 2a: Popular science explanation of WHY MT systems make this error.

    Accessible to translation students without NLP background.
    From spec v1.1 §5.4.
    """

    error_mechanism: str  # "NMT systems commonly make this error because..."
    architectural_cause: str  # "This relates to how transformers process..."
    pattern_generalization: str  # "You can expect similar errors when you see..."
    mt_system_specific: Optional[str] = None  # "General-purpose LLMs additionally..."


class TechnicalExplanation(BaseModel):
    """Layer 2b: Technical NLP explanation (optional, progressive disclosure).

    Precise explanations for students who want deeper understanding.
    Citable and technically accurate. From spec v1.1 §5.4.
    """

    technical_description: str  # NLP-level explanation with proper terminology
    key_concepts: list[str]  # e.g., ["BPE splits", "shared subword vocabularies"]
    references: list[str]  # e.g., ["Koehn & Knowles 2017", "Sennrich et al. 2016"]


class InjectedError(BaseModel):
    """An error injected into a reference translation via the controlled pipeline."""

    error_id: str

    # Span information
    span_start: int  # Character offset in modified text
    span_end: int
    original_text: str  # What was there before injection
    injected_text: str  # What replaced it

    # Classification (v1.1 primary tag system)
    primary_tag: PrimaryTag  # e.g., MISTRANSLATION
    error_type: str  # e.g., false_cognate (type attribute value)
    severity: Severity
    tom_level: TOMLevel

    # Competency mapping (v1.1 §3)
    primary_skill: SkillID  # e.g., S3
    secondary_skills: list[SkillID] = []

    # Context-dependent severity info
    severity_range: list[Severity] = []  # Plausible range from codebook

    # Direction specificity
    direction: str = "both"  # "en_fr", "fr_en", or "both"

    # Explanation layers
    explanation: ContrastiveExplanation  # Layer 1: per-error contrastive
    system_behavior: Optional[SystemBehaviorExplanation] = None  # Layer 2a
    technical_explanation: Optional[TechnicalExplanation] = None  # Layer 2b

    # Inline XML representation (from two-step injection)
    xml_tag: Optional[str] = None  # The full XML tag string as produced by the LLM

    # Brief explanation from injection LLM (desc attribute in XML tag)
    brief_explanation: str = ""


class DetectedError(BaseModel):
    """Error detected in authentic MT output (not injected)."""

    span_start: int
    span_end: int
    primary_tag: PrimaryTag
    error_type: str
    severity: Severity
    tom_level: TOMLevel
    primary_skill: SkillID
    secondary_skills: list[SkillID] = []
    detection_confidence: float
    explanation: ContrastiveExplanation
    system_behavior: Optional[SystemBehaviorExplanation] = None
    technical_explanation: Optional[TechnicalExplanation] = None
    human_validated: bool = False


class AuthenticErrorDetection(BaseModel):
    """For authentic pathway: errors found by comparing MT output to reference."""

    detection_method: str  # "xcomet", "gemba_mqm", "human_expert"
    mt_output: str
    reference: str
    detected_errors: list[DetectedError]
    confidence_score: float
