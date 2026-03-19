"""Multi-system MT generation pipeline stage.

Generates translations from configured MT backends for each selected corpus segment.
Supports three pathways:
  - Dedicated MT APIs (Google Translate, DeepL)
  - LLM-as-translator with configurable prompt strategies

See _translation_prompts.py for the 5 prompt strategies.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx

from tompe.pipeline._translation_prompts import build_translation_prompt
from tompe.pipeline.llm_client import LLMClient, make_client
from tompe.schemas.corpus import CorpusSegment, MTOutput

logger = logging.getLogger(__name__)


# ============================================================================
# Google Translate (REST API v2 via httpx)
# ============================================================================

_GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"


async def _translate_google(
    segment: CorpusSegment,
    api_key: str,
) -> MTOutput:
    """Translate a segment using Google Translate REST API v2."""
    params = {"key": api_key}
    payload = {
        "q": segment.source_text,
        "source": segment.source_lang,
        "target": segment.target_lang,
        "format": "text",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_GOOGLE_TRANSLATE_URL, params=params, json=payload)
        resp.raise_for_status()
        data = resp.json()

    translated = data["data"]["translations"][0]["translatedText"]

    return MTOutput(
        mt_id=str(uuid.uuid4()),
        segment_id=segment.segment_id,
        mt_system="google",
        mt_text=translated,
        system_type="dedicated_mt",
        generation_timestamp=datetime.now(timezone.utc),
    )


# ============================================================================
# DeepL (REST API via httpx) — prepared, requires DEEPL_AUTH_KEY
# ============================================================================

_DEEPL_API_URL_FREE = "https://api-free.deepl.com/v2/translate"
_DEEPL_API_URL_PRO = "https://api.deepl.com/v2/translate"

# DeepL language codes differ slightly from our internal codes
_DEEPL_LANG_MAP = {"en": "EN", "fr": "FR"}


async def _translate_deepl(
    segment: CorpusSegment,
    auth_key: str,
    use_pro: bool = False,
) -> MTOutput:
    """Translate a segment using the DeepL API."""
    url = _DEEPL_API_URL_PRO if use_pro else _DEEPL_API_URL_FREE
    headers = {
        "Authorization": f"DeepL-Auth-Key {auth_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": [segment.source_text],
        "source_lang": _DEEPL_LANG_MAP.get(segment.source_lang, segment.source_lang),
        "target_lang": _DEEPL_LANG_MAP.get(segment.target_lang, segment.target_lang),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    translated = data["translations"][0]["text"]

    return MTOutput(
        mt_id=str(uuid.uuid4()),
        segment_id=segment.segment_id,
        mt_system="deepl",
        mt_text=translated,
        system_type="dedicated_mt",
        generation_timestamp=datetime.now(timezone.utc),
    )


# ============================================================================
# LLM-as-translator (any provider via llm_client)
# ============================================================================

async def _translate_llm(
    segment: CorpusSegment,
    llm_client: LLMClient,
    mt_system_name: str,
    prompt_strategy: str = "zero_shot",
    examples: list[dict] | None = None,
    glossary_entries: list[dict] | None = None,
) -> MTOutput:
    """Translate a segment using an LLM with the specified prompt strategy."""
    system_prompt, user_prompt = build_translation_prompt(
        strategy=prompt_strategy,
        source_text=segment.source_text,
        source_lang=segment.source_lang,
        target_lang=segment.target_lang,
        domain=segment.domain,
        register=segment.text_register,
        examples=examples,
        glossary_entries=glossary_entries,
    )

    translated = await llm_client.complete_text(
        system=system_prompt,
        user=user_prompt,
        temperature=0.3,
    )

    # Clean up: remove quotes or extra whitespace the LLM might add
    translated = translated.strip().strip('"').strip("'")

    return MTOutput(
        mt_id=str(uuid.uuid4()),
        segment_id=segment.segment_id,
        mt_system=mt_system_name,
        mt_text=translated,
        system_type="general_llm",
        generation_timestamp=datetime.now(timezone.utc),
    )


# ============================================================================
# Public API
# ============================================================================

async def translate_segment(
    segment: CorpusSegment,
    mt_system: str,
    config: dict,
) -> MTOutput:
    """Translate a single segment using the specified MT system.

    Args:
        segment: The corpus segment to translate.
        mt_system: System name — "google", "deepl", or an LLM system name
                   (e.g., "gpt4", "claude", "ollama", "deepseek", "together").
        config: MT system config dict with provider-specific settings.
                For LLM systems: must include "provider", "model", and
                optionally "prompt_strategy".

    Returns:
        MTOutput with the translation.
    """
    if mt_system == "google":
        api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_TRANSLATE_API_KEY environment variable not set")
        return await _translate_google(segment, api_key)

    if mt_system == "deepl":
        auth_key = os.getenv("DEEPL_AUTH_KEY", "")
        if not auth_key:
            raise ValueError(
                "DEEPL_AUTH_KEY environment variable not set. "
                "DeepL is prepared but currently disabled."
            )
        use_pro = config.get("use_pro", False)
        return await _translate_deepl(segment, auth_key, use_pro)

    # LLM-as-translator pathway
    system_type = config.get("type", "general_llm")
    if system_type != "general_llm":
        raise ValueError(f"Unknown MT system: {mt_system}")

    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4.1")
    prompt_strategy = config.get("prompt_strategy", "zero_shot")

    llm_client = make_client(provider=provider, model=model)
    return await _translate_llm(
        segment=segment,
        llm_client=llm_client,
        mt_system_name=mt_system,
        prompt_strategy=prompt_strategy,
        examples=config.get("examples"),
        glossary_entries=config.get("glossary_entries"),
    )


async def generate_all_translations(
    segment: CorpusSegment,
    mt_systems: dict[str, dict],
    max_concurrent: int = 3,
) -> list[MTOutput]:
    """Generate translations from all configured MT systems for a segment.

    Args:
        segment: The corpus segment to translate.
        mt_systems: Dict mapping system names to their config dicts.
                    Only systems with "enabled: true" are used.
        max_concurrent: Max concurrent translation tasks.

    Returns:
        List of MTOutput objects (one per system that succeeded).
    """
    enabled_systems = {
        name: cfg for name, cfg in mt_systems.items()
        if cfg.get("enabled", False)
    }

    if not enabled_systems:
        logger.warning("No MT systems enabled in configuration")
        return []

    sem = asyncio.Semaphore(max_concurrent)

    async def _translate_with_sem(name: str, cfg: dict) -> MTOutput | None:
        async with sem:
            try:
                return await translate_segment(segment, name, cfg)
            except Exception as e:
                logger.warning("Translation failed for %s: %s", name, e)
                return None

    tasks = [
        _translate_with_sem(name, cfg)
        for name, cfg in enabled_systems.items()
    ]
    results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]
