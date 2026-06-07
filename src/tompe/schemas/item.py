"""Assessment item models."""

from typing import Literal, Optional, Union

from pydantic import BaseModel

from tompe.schemas.annotation import AnnotationConfig, ErrorAnnotation
from tompe.schemas.corpus import IATETerm, MTOutput
from tompe.schemas.enums import (
    AnnotationLevel,
    ComparisonType,
    ItemPathway,
    MQMCategory,
    TOMLevel,
)
from tompe.schemas.error import (
    ContrastiveExplanation,
    DetectedError,
    InjectedError,
    SystemBehaviorExplanation,
    TechnicalExplanation,
)


class ItemMetadata(BaseModel):
    tom_profile: dict[TOMLevel, int]  # Count of errors per ToM level
    mqm_profile: dict[MQMCategory, int]  # Count of errors per MQM category
    estimated_time_minutes: float
    has_clean_segments: bool
    scaffolding_level: AnnotationLevel
    pathway: ItemPathway
    translation_direction: str  # "en→fr" or "fr→en"


class AssessmentItem(BaseModel):
    item_id: str
    segment_id: str  # FK to CorpusSegment
    source_text: str
    source_lang: Literal["fr", "en"]
    target_lang: Literal["fr", "en"]
    presented_text: str  # MT output WITH injected/detected errors
    reference_translation: str  # Clean human reference (hidden from student)
    mt_system: str
    pathway: ItemPathway
    errors: list[Union[InjectedError, DetectedError]]
    clean_spans: list[tuple[int, int]]  # Spans with NO errors
    annotations: list[ErrorAnnotation]
    annotation_config: AnnotationConfig
    difficulty_level: int  # 1-5
    domain: str
    item_status: Literal["draft", "reviewed", "published", "retired"] = "draft"
    teacher_notes: Optional[str] = None
    iate_terms: list[IATETerm] = []
    explanations_layer1: list[ContrastiveExplanation] = []
    explanations_layer2: list[SystemBehaviorExplanation] = []
    explanations_layer2b: list[TechnicalExplanation] = []
    metadata: ItemMetadata

    # For comparison exercises
    comparison_outputs: Optional[list[MTOutput]] = None
    comparison_type: Optional[ComparisonType] = None
