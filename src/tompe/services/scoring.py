"""Response evaluation and MQM scoring logic.

Implements IoU-based span matching for evaluation mode, HTER for post-editing mode,
and LLM-based justification assessment.
"""

from tompe.schemas.item import AssessmentItem
from tompe.schemas.response import StudentResponse
from tompe.schemas.scoring import ScoringResult


def compute_span_iou(span_a: tuple[int, int], span_b: tuple[int, int]) -> float:
    """Compute character-level Intersection over Union between two spans."""
    start = max(span_a[0], span_b[0])
    end = min(span_a[1], span_b[1])
    intersection = max(0, end - start)
    union = (span_a[1] - span_a[0]) + (span_b[1] - span_b[0]) - intersection
    return intersection / union if union > 0 else 0.0


def score_evaluation_response(
    response: StudentResponse,
    item: AssessmentItem,
    iou_threshold: float = 0.5,
) -> ScoringResult:
    """Score an evaluation-mode response using IoU-based span matching."""
    raise NotImplementedError


def score_postediting_response(
    response: StudentResponse,
    item: AssessmentItem,
) -> ScoringResult:
    """Score a post-editing response using HTER and edit analysis."""
    raise NotImplementedError


def score_navigator_response(
    response: StudentResponse,
    item: AssessmentItem,
) -> ScoringResult:
    """Score a navigator-mode response (verification + classification)."""
    raise NotImplementedError
