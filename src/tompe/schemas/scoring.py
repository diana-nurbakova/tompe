"""Scoring and analytics models."""

from typing import Literal, Optional

from pydantic import BaseModel

from tompe.schemas.enums import MQMCategory, SkillID, TOMLevel


class CategoryScore(BaseModel):
    detected: int
    total: int
    detection_rate: float


class JustificationScore(BaseModel):
    justification_id: str
    tom_perspective_correct: bool
    reasoning_quality: Literal["surface", "partial", "deep"]


class ScoringResult(BaseModel):
    response_id: str
    item_id: str

    # Detection metrics
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float

    # Per-category breakdown
    detection_by_mqm: dict[MQMCategory, CategoryScore]
    detection_by_tom: dict[TOMLevel, CategoryScore]
    detection_by_skill: dict[SkillID, CategoryScore] = {}

    # Post-editing metrics (if PE mode)
    hter: Optional[float] = None
    unnecessary_edits: Optional[int] = None
    edit_quality: Optional[float] = None

    # Justification quality
    justification_scores: list[JustificationScore] = []


class PerformanceTimeSeries(BaseModel):
    """Rolling detection rate over sessions."""

    session_ids: list[str]
    detection_rates: list[float]
    trend: Literal["improving", "stable", "declining"]


class BlindSpot(BaseModel):
    """Systematic weakness identified across sessions."""

    mqm_category: MQMCategory
    tom_level: TOMLevel
    detection_rate: float
    sessions_observed: int
    example_item_ids: list[str]


class StudentProfile(BaseModel):
    student_id: str
    display_name: str
    sessions_completed: int = 0
    current_difficulty_level: int = 1

    mqm_performance: dict[MQMCategory, PerformanceTimeSeries] = {}
    tom_performance: dict[TOMLevel, PerformanceTimeSeries] = {}
    blind_spots: list[BlindSpot] = []
    false_positive_rate_history: list[float] = []
