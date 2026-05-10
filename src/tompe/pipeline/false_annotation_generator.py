"""Generate plausible-but-incorrect MQM annotations for L0 (Navigator) items.

Three modes (selectable per-exercise):
  - "llm"    : LLM generates plausible decoys via _false_annotation_prompts.
  - "rule"   : random spans + random MQM tag (cheap, weak distractors).
  - "manual" : no auto-generation; teacher authors via review-queue UI.
  - "none"   : disabled; item gets zero false annotations.

Storage convention (locked design):
  - True errors live in `item.errors`.
  - False annotations live in `item.annotations` (or, for per-exercise
    overrides, on `Exercise.false_annotations[item_id]`).

Output schema: list of dicts with at minimum:
  span_start, span_end, primary_tag (UPPER), severity, plausible_reasoning
"""

from __future__ import annotations

import logging
import random
import uuid
from typing import Optional

from tompe.pipeline._false_annotation_prompts import (
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from tompe.pipeline.llm_client import LLMClient
from tompe.schemas.enums import PrimaryTag, Severity

logger = logging.getLogger(__name__)


# Default tag weights for rule-based mode. Reflects rough class frequency
# from MQM-annotated data; adjust later if needed.
_DEFAULT_TAG_WEIGHTS: dict[PrimaryTag, float] = {
    PrimaryTag.MISTRANSLATION: 0.30,
    PrimaryTag.GRAMMAR: 0.20,
    PrimaryTag.STYLE: 0.15,
    PrimaryTag.SPELLING: 0.10,
    PrimaryTag.PUNCTUATION: 0.10,
    PrimaryTag.TERMINOLOGY: 0.07,
    PrimaryTag.OMISSION: 0.04,
    PrimaryTag.ADDITION: 0.02,
    PrimaryTag.UNTRANSLATED: 0.01,
    PrimaryTag.LOCALE: 0.01,
}


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or b[1] <= a[0])


def _make_annotation(
    span_start: int,
    span_end: int,
    primary_tag: str,
    severity: str,
    reasoning: str,
) -> dict:
    """Shape one false annotation dict to match the existing item.annotations format."""
    return {
        "annotation_id": str(uuid.uuid4()),
        "error_id": str(uuid.uuid4()),  # alias used by some readers
        "span_start": span_start,
        "span_end": span_end,
        "primary_tag": primary_tag.upper(),
        "severity": severity.lower(),
        "severity_label": severity.lower(),
        "mqm_label": primary_tag.upper(),
        "plausible_reasoning": reasoning,
        "is_false": True,  # explicit flag for safety; convention also covers it
    }


# ── Rule-based mode ──────────────────────────────────────────────────────────


def generate_rule_false_annotations(
    translation: str,
    excluded_ranges: list[tuple[int, int]],
    n: int,
    seed: Optional[int] = None,
    min_len: int = 5,
    max_len: int = 25,
) -> list[dict]:
    """Pick random non-overlapping spans, assign random MQM tags.

    Cheap and offline; produces obviously-suspicious distractors.
    """
    rng = random.Random(seed)
    text_len = len(translation)
    if text_len < min_len:
        return []

    out: list[dict] = []
    attempts = 0
    while len(out) < n and attempts < n * 30:
        attempts += 1
        span_len = rng.randint(min_len, min(max_len, text_len))
        start = rng.randint(0, text_len - span_len)
        end = start + span_len
        # Snap to word boundaries to avoid mid-word spans
        while start > 0 and translation[start - 1].isalnum():
            start -= 1
        while end < text_len and translation[end].isalnum():
            end += 1
        if end - start < min_len or end - start > max_len * 2:
            continue
        candidate = (start, end)
        if any(_ranges_overlap(candidate, ex) for ex in excluded_ranges):
            continue
        if any(_ranges_overlap(candidate, (a["span_start"], a["span_end"])) for a in out):
            continue

        tags = list(_DEFAULT_TAG_WEIGHTS.keys())
        weights = list(_DEFAULT_TAG_WEIGHTS.values())
        tag = rng.choices(tags, weights=weights, k=1)[0]
        severity = rng.choices(
            [Severity.MINOR.value, Severity.MAJOR.value],
            weights=[0.7, 0.3],
            k=1,
        )[0]
        out.append(_make_annotation(
            span_start=start,
            span_end=end,
            primary_tag=tag.value,
            severity=severity,
            reasoning="rule-based decoy: random span flagged for pedagogical contrast",
        ))

    return out


# ── LLM mode ─────────────────────────────────────────────────────────────────


async def generate_llm_false_annotations(
    source_text: str,
    translation: str,
    excluded_ranges: list[tuple[int, int]],
    n: int,
    llm_client: LLMClient,
) -> list[dict]:
    """Use an LLM to generate plausible-but-wrong MQM annotations."""
    if n <= 0:
        return []

    user_prompt = build_user_prompt(source_text, translation, excluded_ranges, n)
    try:
        result = await llm_client.complete_json(
            system=SYSTEM_PROMPT,
            user=user_prompt,
            schema=RESPONSE_SCHEMA,
        )
    except Exception as exc:
        logger.warning("LLM false-annotation generation failed: %s", exc)
        return []

    decoys = result.get("decoys", []) if isinstance(result, dict) else []
    out: list[dict] = []
    for d in decoys:
        try:
            start = int(d["span_start"])
            end = int(d["span_end"])
        except (KeyError, ValueError, TypeError):
            continue
        # Validate span bounds
        if not (0 <= start < end <= len(translation)):
            logger.debug("LLM decoy out of bounds: [%d, %d) in text of len %d",
                         start, end, len(translation))
            continue
        # Validate span text matches what the LLM claimed (best effort)
        claimed = d.get("span_text", "")
        actual = translation[start:end]
        if claimed and claimed.strip() and actual.strip() != claimed.strip():
            # Try to find the claimed text — LLMs sometimes drift on offsets
            idx = translation.find(claimed)
            if idx >= 0:
                start, end = idx, idx + len(claimed)
            else:
                logger.debug("LLM decoy span_text mismatch and not found: %r", claimed)
                continue
        # Drop overlaps with excluded ranges
        if any(_ranges_overlap((start, end), ex) for ex in excluded_ranges):
            continue
        # Drop overlaps with already-accepted decoys
        if any(_ranges_overlap((start, end), (a["span_start"], a["span_end"])) for a in out):
            continue
        out.append(_make_annotation(
            span_start=start,
            span_end=end,
            primary_tag=d.get("primary_tag", "MISTRANSLATION"),
            severity=d.get("severity", "minor"),
            reasoning=d.get("plausible_reasoning", "")
                or "LLM-generated decoy",
        ))
        if len(out) >= n:
            break

    return out


# ── Unified entry point ──────────────────────────────────────────────────────


async def generate_false_annotations(
    mode: str,
    source_text: str,
    translation: str,
    excluded_ranges: list[tuple[int, int]],
    n: int,
    llm_client: Optional[LLMClient] = None,
    seed: Optional[int] = None,
) -> list[dict]:
    """Dispatch to the requested mode.

    Returns a list of false-annotation dicts ready to attach to an item.

    For "manual" and "none": returns []. Manual decoys are added by the
    teacher via the review queue (separate code path).
    """
    if n <= 0 or mode in ("none", "manual"):
        return []
    if mode == "rule":
        return generate_rule_false_annotations(
            translation, excluded_ranges, n, seed=seed,
        )
    if mode == "llm":
        if llm_client is None:
            logger.warning("LLM mode requested but no llm_client supplied; "
                           "falling back to rule-based")
            return generate_rule_false_annotations(
                translation, excluded_ranges, n, seed=seed,
            )
        return await generate_llm_false_annotations(
            source_text, translation, excluded_ranges, n, llm_client,
        )
    logger.warning("Unknown false-annotation mode %r; returning []", mode)
    return []
