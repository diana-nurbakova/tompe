"""Performance aggregation and blind spot detection."""

from tompe.schemas.scoring import BlindSpot, StudentProfile


def update_student_profile(
    profile: StudentProfile,
    session_results: list[dict],
) -> StudentProfile:
    """Update a student's longitudinal profile with new session results."""
    raise NotImplementedError


def detect_blind_spots(
    profile: StudentProfile,
    threshold: float = 0.5,
    min_sessions: int = 3,
) -> list[BlindSpot]:
    """Identify systematic weaknesses across sessions."""
    raise NotImplementedError


def compute_class_analytics(
    profiles: list[StudentProfile],
) -> dict:
    """Compute aggregated class-level analytics."""
    raise NotImplementedError
