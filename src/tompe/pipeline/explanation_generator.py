"""ToM-informed explanation generation pipeline stage.

Generates two layers of explanations for each error:
- Layer 1: Error-specific contrastive explanation (per error)
- Layer 2: System behavior explanation (per error type)
"""

from tompe.schemas.error import (
    ContrastiveExplanation,
    DetectedError,
    InjectedError,
    SystemBehaviorExplanation,
)


async def generate_contrastive_explanation(
    source_text: str,
    reference: str,
    error: InjectedError | DetectedError,
    llm_config: dict,
) -> ContrastiveExplanation:
    """Generate Layer 1: error-specific contrastive explanation.

    Template: "The MT system likely interpreted [source phrase] as [wrong interpretation]
    rather than [correct interpretation], because [plausible reason]..."
    """
    raise NotImplementedError


async def generate_system_behavior_explanation(
    error: InjectedError | DetectedError,
    mt_system: str,
    llm_config: dict,
) -> SystemBehaviorExplanation:
    """Generate Layer 2: educational explanation of why MT systems make this error type."""
    raise NotImplementedError
