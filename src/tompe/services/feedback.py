"""Feedback selection logic.

Implements the cognitive forcing protocol: explanations are revealed only after
the student submits their justification.
"""

from tompe.schemas.item import AssessmentItem
from tompe.schemas.response import StudentResponse
from tompe.schemas.scoring import ScoringResult


def prepare_feedback(
    response: StudentResponse,
    item: AssessmentItem,
    scoring: ScoringResult,
) -> dict:
    """Prepare the feedback payload for a scored response.

    Includes: detection results, student justification (displayed first),
    system contrastive explanation (displayed second), ToM perspective labels.
    """
    raise NotImplementedError
