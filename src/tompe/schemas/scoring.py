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

    # Navigator mode breakdown (L0 Confirm/Dispute)
    correct_confirms: int = 0
    correct_disputes: int = 0
    incorrect_confirms: int = 0  # student accepted a false annotation
    incorrect_disputes: int = 0  # student rejected a real error

    # Comparison mode (L3) — System §7.4
    # Skill B (COMPARATIVE_RANKING):
    ranking_kendall_tau: Optional[float] = None  # [-1, 1]
    expert_ranking: list[str] = []  # mt_system ids in expected order
    # Human-vs-MT discrimination:
    human_pick_correct: Optional[bool] = None  # None if no choice was made

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


class BKTSkillState(BaseModel):
    """Per-skill Bayesian Knowledge Tracing state for one student.

    BKT models the latent probability that the student has mastered the skill
    (p_mastery). On each observation (correct=True/False), we apply Bayes' rule
    given p_slip and p_guess, then transition forward via p_transit.
    """

    p_mastery: float = 0.1  # Prior probability of mastery (p_init)
    n_observations: int = 0
    n_correct: int = 0
    # Compact history for diagnostics: list of (timestamp_iso, correct, p_after).
    # Capped at HISTORY_CAP entries on update.
    history: list[tuple[str, bool, float]] = []


class StudentBKT(BaseModel):
    """Per-student BKT state across all S1–S7 skills."""

    student_id: str
    per_skill: dict[str, BKTSkillState] = {}  # SkillID.value -> state
