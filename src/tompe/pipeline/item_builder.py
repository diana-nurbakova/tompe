"""Final item assembly pipeline stage.

Orchestrates the full pipeline: segment selection → MT generation → error injection →
QE validation → explanation generation → item manifest creation.
"""

from tompe.schemas.item import AssessmentItem


async def build_item(
    segment_id: str,
    mt_system: str,
    error_profile: dict,
    llm_config: dict,
) -> AssessmentItem:
    """Build a complete assessment item through the full pipeline."""
    raise NotImplementedError


async def build_batch(
    n_items: int,
    corpus_origins: list[str],
    mt_systems: list[str],
    error_profile: dict,
    llm_config: dict,
) -> list[AssessmentItem]:
    """Build a batch of assessment items."""
    raise NotImplementedError
