"""ToM-informed explanation generation pipeline stage.

Generates three layers of explanations:
- Layer 1: Error-specific contrastive explanation (per error instance)
- Layer 2a: Popular science MT behavior explanation (per error type, accessible)
- Layer 2b: Technical NLP explanation (per error type, optional depth)

From spec v1.1 §5.4.

Layer 2a / 2b are inherently per-error-type (not per-instance), so a
JSON cache (`data/codebook/layer2a_explanations.json` /
`layer2b_explanations.json`) is consulted before the LLM is called.
Cache misses fall back to LLM generation.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
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

# ── Layer 2 cache ───────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LAYER2A_CACHE_PATH = _PROJECT_ROOT / "data" / "codebook" / "layer2a_explanations.json"
_LAYER2B_CACHE_PATH = _PROJECT_ROOT / "data" / "codebook" / "layer2b_explanations.json"


@lru_cache(maxsize=2)
def _load_explanation_cache(path_str: str) -> list[dict]:
    """Load and return the `entries` list from a layer-2 cache file."""
    path = Path(path_str)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("entries", []) or []
    except Exception as exc:
        logger.warning("Failed to load explanation cache %s: %s", path, exc)
        return []


def _lookup_explanation(
    entries: list[dict],
    primary_tag: str,
    error_type: str,
    mt_system: str | None,
) -> dict | None:
    """Find the best-matching cache entry. System-specific match wins over
    a wildcard (mt_system=None) match."""
    wildcard: dict | None = None
    for entry in entries:
        if entry.get("primary_tag") != primary_tag:
            continue
        if entry.get("error_type") != error_type:
            continue
        entry_system = entry.get("mt_system")
        if entry_system == mt_system:
            return entry
        if entry_system is None and wildcard is None:
            wildcard = entry
    return wildcard


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

    Consults `data/codebook/layer2a_explanations.json` first; on a cache
    miss, calls the LLM. Accessible to translation students without NLP
    background.
    """
    primary_tag = error.primary_tag.value
    cached = _lookup_explanation(
        _load_explanation_cache(str(_LAYER2A_CACHE_PATH)),
        primary_tag, error.error_type, mt_system,
    )
    if cached is not None:
        try:
            return SystemBehaviorExplanation(
                error_mechanism=cached["error_mechanism"],
                architectural_cause=cached["architectural_cause"],
                pattern_generalization=cached["pattern_generalization"],
                mt_system_specific=cached["mt_system_specific"],
            )
        except (KeyError, TypeError) as exc:
            logger.warning(
                "Layer 2a cache entry malformed for %s/%s: %s — falling back to LLM",
                primary_tag, error.error_type, exc,
            )

    llm_client = make_client_from_config(llm_config)

    if isinstance(error, InjectedError):
        brief = error.brief_explanation or f"'{error.original_text}' → '{error.injected_text}'"
    else:
        brief = f"Detected error at [{error.span_start}:{error.span_end}]"

    user_prompt = build_layer2a_user_prompt(
        primary_tag=primary_tag,
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

    Consults `data/codebook/layer2b_explanations.json` first; on a cache
    miss, calls the LLM. For advanced students who want deeper
    understanding (progressive disclosure).
    """
    primary_tag = error.primary_tag.value
    cached = _lookup_explanation(
        _load_explanation_cache(str(_LAYER2B_CACHE_PATH)),
        primary_tag, error.error_type, mt_system,
    )
    if cached is not None:
        try:
            return TechnicalExplanation(
                technical_description=cached["technical_description"],
                key_concepts=list(cached.get("key_concepts", [])),
                references=list(cached.get("references", [])),
            )
        except (KeyError, TypeError) as exc:
            logger.warning(
                "Layer 2b cache entry malformed for %s/%s: %s — falling back to LLM",
                primary_tag, error.error_type, exc,
            )

    llm_client = make_client_from_config(llm_config)

    if isinstance(error, InjectedError):
        brief = error.brief_explanation or f"'{error.original_text}' → '{error.injected_text}'"
    else:
        brief = f"Detected error at [{error.span_start}:{error.span_end}]"

    user_prompt = build_layer2b_user_prompt(
        primary_tag=primary_tag,
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
