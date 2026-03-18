"""MQM-guided error injection pipeline stage.

Injects controlled, categorized errors into human reference translations (or augments
real MT output) using LLM-based generation with MQM taxonomy constraints.
"""

from tompe.schemas.corpus import CorpusSegment, MTOutput
from tompe.schemas.enums import MQMCategory, Severity, TOMLevel
from tompe.schemas.error import InjectedError


class ErrorProfile:
    """Target error profile for injection."""

    def __init__(
        self,
        mqm_categories: list[MQMCategory],
        severity_distribution: dict[Severity, int],
        tom_levels: list[TOMLevel],
        include_clean_spans: bool = True,
    ):
        self.mqm_categories = mqm_categories
        self.severity_distribution = severity_distribution
        self.tom_levels = tom_levels
        self.include_clean_spans = include_clean_spans


async def inject_errors_reference_based(
    segment: CorpusSegment,
    error_profile: ErrorProfile,
    llm_config: dict,
) -> tuple[str, list[InjectedError]]:
    """Inject errors into the human reference translation.

    Returns the modified text and the error manifest.
    """
    raise NotImplementedError


async def inject_errors_mt_based(
    segment: CorpusSegment,
    mt_output: MTOutput,
    error_profile: ErrorProfile,
    llm_config: dict,
) -> tuple[str, list[InjectedError]]:
    """Augment real MT output with additional controlled errors.

    Returns the modified text and the error manifest.
    """
    raise NotImplementedError
