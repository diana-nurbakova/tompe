"""Corpus segment and MT output models."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CorpusSegment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    segment_id: str
    source_text: str
    reference_translation: str
    source_lang: Literal["fr", "en"]
    target_lang: Literal["fr", "en"]
    corpus_origin: Literal["europarl", "dgt_tm", "eurlex", "unpc"]
    domain: str  # e.g., "legal", "parliamentary", "institutional"
    complexity_score: float
    terminology_density: float  # IATE term count / total tokens
    text_register: Literal["formal", "semi-formal", "informal"] = Field(alias="register")


class MTOutput(BaseModel):
    mt_id: str
    segment_id: str  # FK to CorpusSegment
    mt_system: Literal["google", "deepl", "nllb", "gpt4", "claude", "deepseek"]
    mt_text: str
    system_type: Literal["dedicated_mt", "general_llm"]
    generation_timestamp: datetime
    bleu_score: Optional[float] = None
    comet_score: Optional[float] = None


class IATETerm(BaseModel):
    term_id: str
    source_term: str
    target_term: str
    domain: str
    reliability: Optional[float] = None
