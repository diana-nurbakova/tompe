"""Session, authentication, and exercise management models.

From UI Spec v1.0 section 2.3 — data models for student accounts, class groups,
exercises, and exercise assignments.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from tompe.schemas.enums import AnnotationLevel


class ResearchConsent(BaseModel):
    """Records a student's research data consent decision.

    Two-tier consent: Tier 1 (interaction data for research) is independent
    of platform access. Tier 2 (anonymized text excerpts in publications)
    is optional. Refusal does not affect grades or platform access.
    """

    consent_version: str  # e.g., "1.0" — tracks which form version was shown
    tier1_research_data: bool = False  # Use interaction/annotation data for research
    tier2_publication_excerpts: bool = False  # Use anonymized justification excerpts
    timestamp: Optional[datetime] = None  # When consent was given/updated
    withdrawn: bool = False  # True if student later withdrew consent
    withdrawn_at: Optional[datetime] = None


class StudentAccount(BaseModel):
    """A student user account created by the teacher."""

    student_id: str  # UUID
    username: str  # Unique, for login
    display_name: str  # Shown in UI and analytics
    password_hash: str  # bcrypt
    class_id: str  # FK to ClassGroup
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True
    current_level: AnnotationLevel = AnnotationLevel.NAVIGATOR
    allowed_levels: list[AnnotationLevel] = Field(
        default_factory=lambda: [AnnotationLevel.NAVIGATOR]
    )

    # Research consent
    consent: Optional[ResearchConsent] = None  # None = not yet shown the form


class ClassGroup(BaseModel):
    """A class group managed by a teacher."""

    class_id: str  # UUID
    class_name: str  # e.g., "MT Post-Editing 2026 — Group A"
    teacher_id: str = "default"  # v1: single teacher
    default_levels: list[AnnotationLevel] = Field(
        default_factory=lambda: [AnnotationLevel.NAVIGATOR]
    )
    created_at: datetime = Field(default_factory=datetime.now)


class Exercise(BaseModel):
    """An exercise composed of assessment items, configured by the teacher."""

    exercise_id: str  # UUID
    name: str
    description: str = ""
    mode: Literal["evaluation", "postediting", "both"] = "evaluation"
    level: AnnotationLevel = AnnotationLevel.ANALYST
    item_ids: list[str] = []  # FK to AssessmentItem
    justification_type: Literal["free_text", "structured", "both"] = "free_text"
    clean_segment_ratio: float = 0.0  # L3 only: fraction of items that are error-free
    false_annotation_ratio: float = 0.0  # L0 only: ratio of false to true annotations
    item_ordering: Literal["manual", "difficulty", "random"] = "manual"
    assigned_to_class: Optional[str] = None  # FK to ClassGroup
    assigned_to_students: list[str] = []  # FK to StudentAccount
    domain: str = ""
    direction: str = ""  # e.g., "EN→FR"
    created_at: datetime = Field(default_factory=datetime.now)


class ExerciseAssignment(BaseModel):
    """Tracks a student's progress through an assigned exercise."""

    assignment_id: str  # UUID
    exercise_id: str  # FK to Exercise
    student_id: str  # FK to StudentAccount
    status: Literal["not_started", "in_progress", "completed"] = "not_started"
    current_item_index: int = 0
    score: Optional[float] = None  # Overall score once completed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    response_ids: list[str] = []  # FK to StudentResponse, one per item


class SessionToken(BaseModel):
    """An active authentication session."""

    token: str
    student_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
