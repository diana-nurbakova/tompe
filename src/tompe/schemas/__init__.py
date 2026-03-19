"""ToM-PE data models (Pydantic schemas)."""

from tompe.schemas.annotation import AnnotationConfig, ErrorAnnotation, RegionHint
from tompe.schemas.competency import (
    MasteryThreshold,
    SkillDefinition,
    StageDefinition,
)
from tompe.schemas.corpus import CorpusSegment, IATETerm, MTOutput
from tompe.schemas.enums import (
    AnnotationLevel,
    ComparisonType,
    ItemPathway,
    MQMCategory,
    PrimaryTag,
    Severity,
    SkillID,
    TOMLevel,
)
from tompe.schemas.error import (
    AuthenticErrorDetection,
    ContrastiveExplanation,
    DetectedError,
    InjectedError,
    SystemBehaviorExplanation,
    TechnicalExplanation,
)
from tompe.schemas.item import AssessmentItem, ItemMetadata
from tompe.schemas.response import (
    IdentifiedError,
    Justification,
    PEWorthinessVerdict,
    PerSystemEvaluation,
    StudentResponse,
    SystemRanking,
    VerificationResponse,
)
from tompe.schemas.scoring import (
    BlindSpot,
    CategoryScore,
    JustificationScore,
    PerformanceTimeSeries,
    ScoringResult,
    StudentProfile,
)
from tompe.schemas.session import (
    ClassGroup,
    Exercise,
    ExerciseAssignment,
    ResearchConsent,
    SessionToken,
    StudentAccount,
)

__all__ = [
    "AnnotationConfig",
    "AnnotationLevel",
    "AssessmentItem",
    "AuthenticErrorDetection",
    "BlindSpot",
    "CategoryScore",
    "ComparisonType",
    "ContrastiveExplanation",
    "CorpusSegment",
    "DetectedError",
    "ErrorAnnotation",
    "IATETerm",
    "IdentifiedError",
    "InjectedError",
    "ItemMetadata",
    "ItemPathway",
    "Justification",
    "JustificationScore",
    "MQMCategory",
    "MasteryThreshold",
    "MTOutput",
    "PEWorthinessVerdict",
    "PerSystemEvaluation",
    "PerformanceTimeSeries",
    "PrimaryTag",
    "RegionHint",
    "ScoringResult",
    "Severity",
    "SkillDefinition",
    "SkillID",
    "StageDefinition",
    "StudentProfile",
    "StudentResponse",
    "SystemBehaviorExplanation",
    "SystemRanking",
    "TechnicalExplanation",
    "TOMLevel",
    "VerificationResponse",
    # Session models
    "ClassGroup",
    "Exercise",
    "ExerciseAssignment",
    "ResearchConsent",
    "SessionToken",
    "StudentAccount",
]
