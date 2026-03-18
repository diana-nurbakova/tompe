"""Difficulty and scaffolding stage management.

v1: Teacher-controlled progression with system recommendations.
v2 (future): Adaptive progression based on mastery thresholds.
"""

from tompe.schemas.enums import AnnotationLevel
from tompe.schemas.scoring import StudentProfile


def recommend_next_level(
    profile: StudentProfile,
    mastery_threshold: float = 0.8,
    sustained_sessions: int = 3,
) -> AnnotationLevel | None:
    """Recommend next scaffolding level based on performance.

    Returns None if student should stay at current level.
    """
    raise NotImplementedError


def recommend_exercises(
    profile: StudentProfile,
    available_items: list[dict],
) -> list[str]:
    """Recommend exercises targeting the student's blind spots."""
    raise NotImplementedError
