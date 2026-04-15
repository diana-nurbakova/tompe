"""Quality estimation validation pipeline stage.

Uses GEMBA-MQM (LLM-based) to validate that injected errors are detectable
and that the error-injected text shows measurable quality degradation.

xCOMET-XL is optional (requires GPU + large model) — skipped if unavailable.

GEMBA-MQM approach (Kocmi & Federmann, 2023): asks an LLM to identify
MQM errors in the translation, then compares LLM-detected errors against
the injected error manifest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from tompe.pipeline.llm_client import LLMClient, make_client_from_config
from tompe.schemas.error import InjectedError

logger = logging.getLogger(__name__)

# ── GEMBA-MQM Prompts ──────────────────────────────────────────────────────

GEMBA_SYSTEM_PROMPT = """You are an expert translation quality evaluator. Given a source text and its translation, identify all translation errors using the MQM (Multidimensional Quality Metrics) framework.

For each error found, provide:
- category: one of Accuracy, Fluency, Terminology, Style, Locale
- subcategory: specific error type (e.g., Mistranslation, Omission, Grammar, Spelling)
- severity: minor, major, or critical
- span: the exact text span in the translation that contains the error
- explanation: brief explanation of what's wrong

If the translation is perfect, return an empty errors list."""

GEMBA_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_quality": {
            "type": "string",
            "enum": ["perfect", "good", "acceptable", "poor", "terrible"],
        },
        "overall_score": {
            "type": "number",
        },
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "subcategory": {"type": "string"},
                    "severity": {"type": "string", "enum": ["minor", "major", "critical"]},
                    "span": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["category", "subcategory", "severity", "span", "explanation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_quality", "overall_score", "errors"],
    "additionalProperties": False,
}


def _build_gemba_user_prompt(
    source_text: str,
    translation: str,
    source_lang: str = "en",
    target_lang: str = "fr",
) -> str:
    """Build the GEMBA-MQM user prompt."""
    lang_names = {"en": "English", "fr": "French", "de": "German", "es": "Spanish"}
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    return f"""Evaluate the following {src_name} to {tgt_name} translation for quality errors.

Source ({src_name}):
{source_text}

Translation ({tgt_name}):
{translation}

Identify ALL translation errors using MQM categories. Be thorough — check for accuracy, fluency, terminology, and style issues."""


# ── Validation Result ──────────────────────────────────────────────────────


@dataclass
class GEMBAError:
    """A single error detected by GEMBA-MQM."""
    category: str
    subcategory: str
    severity: str
    span: str
    explanation: str


@dataclass
class QEValidationResult:
    """Result of QE validation for an item."""

    # GEMBA-MQM results
    overall_quality: str = "unknown"
    overall_score: float = 0.0
    gemba_errors: list[GEMBAError] = field(default_factory=list)

    # Comparison with injected errors
    total_injected: int = 0
    gemba_detected: int = 0  # How many injected errors GEMBA also found
    gemba_extra: int = 0  # Errors GEMBA found that weren't injected (pre-existing?)

    # Clean translation score (reference without errors)
    clean_score: Optional[float] = None
    score_degradation: Optional[float] = None

    @property
    def detection_rate(self) -> float:
        """Fraction of injected errors detected by GEMBA."""
        return self.gemba_detected / max(self.total_injected, 1)

    @property
    def passes_validation(self) -> bool:
        """Item passes if >=50% of injected errors are independently detected."""
        return self.detection_rate >= 0.5

    @property
    def status(self) -> str:
        if self.total_injected == 0:
            return "no_errors"
        if self.passes_validation:
            return "passed"
        return "failed"


# ── Matching Logic ─────────────────────────────────────────────────────────


def _match_gemba_to_injected(
    gemba_errors: list[GEMBAError],
    injected_errors: list[InjectedError],
    translation: str,
) -> tuple[int, int]:
    """Match GEMBA-detected errors to injected errors.

    Returns (detected_count, extra_count).
    """
    injected_matched = [False] * len(injected_errors)

    for g_err in gemba_errors:
        g_span = g_err.span.lower().strip()
        matched = False

        for i, inj in enumerate(injected_errors):
            if injected_matched[i]:
                continue

            # Check text overlap
            inj_text = (inj.injected_text or "").lower().strip()
            orig_text = (inj.original_text or "").lower().strip()

            if not g_span:
                continue

            # Match if GEMBA span overlaps with injected or original text
            if (g_span in inj_text or inj_text in g_span
                    or g_span in orig_text or orig_text in g_span):
                injected_matched[i] = True
                matched = True
                break

            # Also try position-based matching
            g_pos = translation.lower().find(g_span)
            if g_pos >= 0:
                g_start, g_end = g_pos, g_pos + len(g_span)
                # Check IoU with injected span
                i_start, i_end = inj.span_start, inj.span_end
                intersection = max(0, min(g_end, i_end) - max(g_start, i_start))
                union = (g_end - g_start) + (i_end - i_start) - intersection
                if union > 0 and intersection / union >= 0.3:
                    injected_matched[i] = True
                    matched = True
                    break

    detected = sum(injected_matched)
    extra = len(gemba_errors) - detected
    return detected, max(0, extra)


# ── Public API ─────────────────────────────────────────────────────────────


async def validate_item_gemba(
    source_text: str,
    reference: str,
    injected_text: str,
    injected_errors: list[InjectedError],
    llm_config: dict,
    source_lang: str = "en",
    target_lang: str = "fr",
) -> QEValidationResult:
    """Run GEMBA-MQM validation on an error-injected item.

    1. Asks LLM to evaluate the injected translation (finds errors)
    2. Optionally evaluates the clean reference (baseline score)
    3. Matches LLM-detected errors against injected manifest
    """
    llm_client = make_client_from_config(llm_config)

    # 1. Evaluate injected translation
    user_prompt = _build_gemba_user_prompt(source_text, injected_text, source_lang, target_lang)

    try:
        data = await llm_client.complete_json(
            system=GEMBA_SYSTEM_PROMPT,
            user=user_prompt,
            schema=GEMBA_RESPONSE_SCHEMA,
            temperature=0.3,
        )
    except Exception as e:
        logger.error("GEMBA-MQM evaluation failed: %s", e)
        return QEValidationResult(
            overall_quality="error",
            total_injected=len(injected_errors),
        )

    gemba_errors = [
        GEMBAError(
            category=e.get("category", ""),
            subcategory=e.get("subcategory", ""),
            severity=e.get("severity", "minor"),
            span=e.get("span", ""),
            explanation=e.get("explanation", ""),
        )
        for e in data.get("errors", [])
    ]

    overall_quality = data.get("overall_quality", "unknown")
    overall_score = data.get("overall_score", 0)

    # 2. Optionally evaluate clean reference for score comparison
    clean_score = None
    score_degradation = None
    try:
        clean_prompt = _build_gemba_user_prompt(source_text, reference, source_lang, target_lang)
        clean_data = await llm_client.complete_json(
            system=GEMBA_SYSTEM_PROMPT,
            user=clean_prompt,
            schema=GEMBA_RESPONSE_SCHEMA,
            temperature=0.3,
        )
        clean_score = clean_data.get("overall_score", 100)
        score_degradation = clean_score - overall_score
    except Exception as e:
        logger.warning("Clean reference evaluation failed: %s", e)

    # 3. Match GEMBA errors to injected errors
    detected, extra = _match_gemba_to_injected(gemba_errors, injected_errors, injected_text)

    return QEValidationResult(
        overall_quality=overall_quality,
        overall_score=overall_score,
        gemba_errors=gemba_errors,
        total_injected=len(injected_errors),
        gemba_detected=detected,
        gemba_extra=extra,
        clean_score=clean_score,
        score_degradation=score_degradation,
    )
