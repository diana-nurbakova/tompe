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
    complexity_score: float = 0.0
    terminology_density: float = 0.0  # IATE term count / total tokens
    text_register: Literal["formal", "semi-formal", "informal"] = Field(
        default="formal", alias="register"
    )
    document_id: Optional[str] = None  # Original document filename from OPUS
    position_in_doc: Optional[int] = None  # 0-based sentence position within document


class MTOutput(BaseModel):
    mt_id: str
    segment_id: str  # FK to CorpusSegment
    mt_system: str  # "google", "deepl", "nllb", "gpt4", "claude", "deepseek", or "human"
    mt_text: str
    system_type: Literal["dedicated_mt", "general_llm", "human"]
    generation_timestamp: datetime
    bleu_score: Optional[float] = None
    comet_score: Optional[float] = None
    # Optional aggregate quality score in [0, 1] used by comparison-mode scoring
    # to derive the expert ranking. Populated by the teacher pipeline (e.g. from
    # COMET, GEMBA-MQM, or expert ratings). Leave None if unknown.
    quality_score: Optional[float] = None
    # True when this output is the human reference translation (used in
    # human-vs-MT discrimination at L3). Always exactly one True per comparison
    # item; False on every machine-produced output.
    is_human_reference: bool = False


class IATETerm(BaseModel):
    term_id: str
    source_term: str
    target_term: str
    domain: str
    reliability: Optional[float] = None
