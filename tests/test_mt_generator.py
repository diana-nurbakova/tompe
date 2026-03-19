"""Tests for the MT generator module.

Unit tests with mocked HTTP responses — no API keys needed.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tompe.pipeline._translation_prompts import (
    PROMPT_STRATEGIES,
    build_translation_prompt,
)
from tompe.schemas.corpus import CorpusSegment


# ============================================================================
# Helper: sample segment
# ============================================================================

def _sample_segment() -> CorpusSegment:
    return CorpusSegment(
        segment_id="test-001",
        source_text="The European Parliament has adopted the resolution.",
        reference_translation="Le Parlement européen a adopté la résolution.",
        source_lang="en",
        target_lang="fr",
        corpus_origin="europarl",
        domain="parliamentary",
        complexity_score=0.3,
        terminology_density=0.1,
        register="semi-formal",
    )


# ============================================================================
# Translation prompt tests
# ============================================================================

def test_prompt_strategies_registry():
    """All 5 prompt strategies should be registered."""
    assert "zero_shot" in PROMPT_STRATEGIES
    assert "domain_context" in PROMPT_STRATEGIES
    assert "glossary_guided" in PROMPT_STRATEGIES
    assert "few_shot" in PROMPT_STRATEGIES
    assert "few_shot_glossary" in PROMPT_STRATEGIES
    assert len(PROMPT_STRATEGIES) == 5


def test_zero_shot_prompt():
    """Zero-shot prompt should contain source text and language names."""
    system, user = build_translation_prompt(
        strategy="zero_shot",
        source_text="Hello world",
        source_lang="en",
        target_lang="fr",
    )
    assert "English" in user
    assert "French" in user
    assert "Hello world" in user
    assert "translator" in system.lower()


def test_domain_context_prompt():
    """Domain context prompt should include domain and register info."""
    system, user = build_translation_prompt(
        strategy="domain_context",
        source_text="The regulation applies.",
        source_lang="en",
        target_lang="fr",
        domain="legal",
        register="formal",
    )
    assert "legal" in system.lower() or "legal" in user.lower()
    assert "formal" in system.lower() or "formal" in user.lower()


def test_glossary_guided_prompt():
    """Glossary prompt should include terminology entries."""
    glossary = [
        {"source_term": "regulation", "target_term": "règlement"},
        {"source_term": "directive", "target_term": "directive"},
    ]
    system, user = build_translation_prompt(
        strategy="glossary_guided",
        source_text="The regulation and directive apply.",
        source_lang="en",
        target_lang="fr",
        glossary_entries=glossary,
    )
    assert "règlement" in user
    assert "directive" in user
    assert "glossary" in system.lower()


def test_few_shot_prompt():
    """Few-shot prompt should include examples and the target segment."""
    examples = [
        {
            "source_text": "The committee met yesterday.",
            "reference_translation": "Le comité s'est réuni hier.",
        },
    ]
    system, user = build_translation_prompt(
        strategy="few_shot",
        source_text="The Parliament voted.",
        source_lang="en",
        target_lang="fr",
        examples=examples,
    )
    assert "Example 1" in user
    assert "Le comité" in user
    assert "The Parliament voted." in user


def test_few_shot_glossary_prompt():
    """Few-shot + glossary should combine both examples and terminology."""
    examples = [
        {
            "source_text": "The regulation applies.",
            "reference_translation": "Le règlement s'applique.",
        },
    ]
    glossary = [{"source_term": "directive", "target_term": "directive"}]
    system, user = build_translation_prompt(
        strategy="few_shot_glossary",
        source_text="The directive was adopted.",
        source_lang="en",
        target_lang="fr",
        examples=examples,
        glossary_entries=glossary,
    )
    assert "Example 1" in user
    assert "directive" in user
    assert "glossary" in system.lower()


def test_unknown_strategy_raises():
    """Unknown strategy should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown prompt strategy"):
        build_translation_prompt(
            strategy="nonexistent",
            source_text="Hello",
            source_lang="en",
            target_lang="fr",
        )


# ============================================================================
# MT generator function tests (mocked HTTP)
# ============================================================================

@pytest.mark.asyncio
async def test_translate_google_success():
    """Google Translate should return MTOutput on success."""
    from unittest.mock import MagicMock

    from tompe.pipeline.mt_generator import translate_segment

    mock_json_data = {
        "data": {
            "translations": [{"translatedText": "Le Parlement européen a adopté la résolution."}]
        }
    }

    segment = _sample_segment()

    with patch.dict("os.environ", {"GOOGLE_TRANSLATE_API_KEY": "test-key"}):
        with patch("tompe.pipeline.mt_generator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()  # httpx Response is sync
            mock_response_obj.json.return_value = mock_json_data
            mock_response_obj.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response_obj)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await translate_segment(segment, "google", {})

    assert result.mt_system == "google"
    assert result.system_type == "dedicated_mt"
    assert result.segment_id == "test-001"
    assert "Parlement" in result.mt_text


@pytest.mark.asyncio
async def test_translate_google_no_key():
    """Google Translate should raise if API key not set."""
    from tompe.pipeline.mt_generator import translate_segment

    segment = _sample_segment()

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="GOOGLE_TRANSLATE_API_KEY"):
            await translate_segment(segment, "google", {})


@pytest.mark.asyncio
async def test_translate_deepl_no_key():
    """DeepL should raise if auth key not set."""
    from tompe.pipeline.mt_generator import translate_segment

    segment = _sample_segment()

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="DEEPL_AUTH_KEY"):
            await translate_segment(segment, "deepl", {})
