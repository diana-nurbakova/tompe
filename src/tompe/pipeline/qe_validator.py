"""Quality estimation validation pipeline stage.

Uses xCOMET-XL and GEMBA-MQM to validate that injected errors are detectable
and that the error-injected text shows measurable quality degradation.
"""

from tompe.schemas.error import InjectedError


class QEValidationResult:
    """Result of QE validation for an item."""

    def __init__(
        self,
        xcomet_score_clean: float,
        xcomet_score_injected: float,
        gemba_detected_errors: int,
        total_injected_errors: int,
    ):
        self.xcomet_score_clean = xcomet_score_clean
        self.xcomet_score_injected = xcomet_score_injected
        self.score_degradation = xcomet_score_clean - xcomet_score_injected
        self.gemba_detection_rate = gemba_detected_errors / max(total_injected_errors, 1)

    @property
    def passes_validation(self) -> bool:
        """Item passes if score degrades and >=80% of errors are detected by GEMBA."""
        return self.score_degradation > 0 and self.gemba_detection_rate >= 0.8


async def validate_item(
    source_text: str,
    reference: str,
    injected_text: str,
    injected_errors: list[InjectedError],
) -> QEValidationResult:
    """Run xCOMET and GEMBA validation on an error-injected item."""
    raise NotImplementedError
