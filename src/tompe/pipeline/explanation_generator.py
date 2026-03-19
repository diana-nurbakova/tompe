"""ToM-informed explanation generation pipeline stage.

Generates three layers of explanations:
- Layer 1: Error-specific contrastive explanation (per error instance)
- Layer 2a: Popular science MT behavior explanation (per error type, accessible)
- Layer 2b: Technical NLP explanation (per error type, optional depth)

From spec v1.1 §5.4.
"""

from __future__ import annotations

import logging
from typing import Optional

from tompe.pipeline._injection_prompts import (
    CONTRASTIVE_EXPLANATION_SCHEMA,
    LAYER2A_SCHEMA,
    LAYER2B_SCHEMA,
    SYSTEM_PROMPT_CONTRASTIVE,
    SYSTEM_PROMPT_LAYER2A,
    SYSTEM_PROMPT_LAYER2B,
    build_contrastive_user_prompt,
    build_layer2a_user_prompt,
    build_layer2b_user_prompt,
)
from tompe.pipeline.llm_client import LLMClient, make_client_from_config
from tompe.schemas.error import (
    ContrastiveExplanation,
    DetectedError,
    InjectedError,
    SystemBehaviorExplanation,
    TechnicalExplanation,
)

logger = logging.getLogger(__name__)


async def generate_contrastive_explanation(
    source_text: str,
    reference: str,
    error: InjectedError | DetectedError,
    llm_config: dict,
) -> ContrastiveExplanation:
    """Generate Layer 1: error-specific contrastive explanation."""
    llm_client = make_client_from_config(llm_config)

    if isinstance(error, InjectedError):
        original_text = error.original_text
        injected_text = error.injected_text
        brief = error.brief_explanation or f"{error.primary_tag.value}/{error.error_type} error"
    else:
        original_text = ""
        injected_text = ""
        brief = f"Detected {error.primary_tag.value}/{error.error_type} error"

    user_prompt = build_contrastive_user_prompt(
        source_text=source_text,
        reference=reference,
        original_text=original_text,
        injected_text=injected_text,
        primary_tag=error.primary_tag.value,
        error_type=error.error_type,
        severity=error.severity.value,
        brief_explanation=brief,
    )

    data = await llm_client.complete_json(
        system=SYSTEM_PROMPT_CONTRASTIVE,
        user=user_prompt,
        schema=CONTRASTIVE_EXPLANATION_SCHEMA,
        temperature=0.5,
    )

    return ContrastiveExplanation(**data)


async def generate_layer2a_explanation(
    error: InjectedError | DetectedError,
    mt_system: str,
    llm_config: dict,
) -> SystemBehaviorExplanation:
    """Generate Layer 2a: popular science MT behavior explanation.

    Accessible to translation students without NLP background.
    """
    llm_client = make_client_from_config(llm_config)

    if isinstance(error, InjectedError):
        brief = error.brief_explanation or f"'{error.original_text}' → '{error.injected_text}'"
    else:
        brief = f"Detected error at [{error.span_start}:{error.span_end}]"

    user_prompt = build_layer2a_user_prompt(
        primary_tag=error.primary_tag.value,
        error_type=error.error_type,
        mt_system=mt_system,
        brief_explanation=brief,
    )

    data = await llm_client.complete_json(
        system=SYSTEM_PROMPT_LAYER2A,
        user=user_prompt,
        schema=LAYER2A_SCHEMA,
        temperature=0.5,
    )

    return SystemBehaviorExplanation(**data)


async def generate_layer2b_explanation(
    error: InjectedError | DetectedError,
    mt_system: str,
    llm_config: dict,
) -> TechnicalExplanation:
    """Generate Layer 2b: technical NLP explanation.

    For advanced students who want deeper understanding (progressive disclosure).
    """
    llm_client = make_client_from_config(llm_config)

    if isinstance(error, InjectedError):
        brief = error.brief_explanation or f"'{error.original_text}' → '{error.injected_text}'"
    else:
        brief = f"Detected error at [{error.span_start}:{error.span_end}]"

    user_prompt = build_layer2b_user_prompt(
        primary_tag=error.primary_tag.value,
        error_type=error.error_type,
        mt_system=mt_system,
        brief_explanation=brief,
    )

    data = await llm_client.complete_json(
        system=SYSTEM_PROMPT_LAYER2B,
        user=user_prompt,
        schema=LAYER2B_SCHEMA,
        temperature=0.5,
    )

    return TechnicalExplanation(**data)


async def generate_all_explanations(
    source_text: str,
    reference: str,
    errors: list[InjectedError],
    mt_system: str,
    llm_config: dict,
    include_layer2b: bool = False,
) -> list[tuple[ContrastiveExplanation, SystemBehaviorExplanation, Optional[TechnicalExplanation]]]:
    """Generate all explanation layers for a list of errors.

    Returns a list of (Layer1, Layer2a, Layer2b) tuples per error.
    Layer2b is None unless include_layer2b=True.
    """
    results = []

    for i, error in enumerate(errors):
        logger.info(
            "Generating explanations for error %d/%d: %s/%s",
            i + 1, len(errors), error.primary_tag.value, error.error_type,
        )

        layer1 = await generate_contrastive_explanation(
            source_text=source_text,
            reference=reference,
            error=error,
            llm_config=llm_config,
        )

        layer2a = await generate_layer2a_explanation(
            error=error,
            mt_system=mt_system,
            llm_config=llm_config,
        )

        layer2b = None
        if include_layer2b:
            layer2b = await generate_layer2b_explanation(
                error=error,
                mt_system=mt_system,
                llm_config=llm_config,
            )

        results.append((layer1, layer2a, layer2b))

    return results
