"""B0 — Random word-level perturbation baseline (no LLM).

Applies one of three random corruptions to the reference translation:
  - Word deletion (simulates omission)
  - Adjacent word swap (simulates word-order error)
  - Synonym replacement via WordNet (simulates mistranslation)

No codebook guidance, no ToM reasoning.  Serves as the lower bound for
injection quality in the ablation study.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from typing import Optional

import nltk
from nltk.corpus import wordnet

from tompe.schemas.corpus import CorpusSegment
from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel
from tompe.schemas.error import ContrastiveExplanation, InjectedError

logger = logging.getLogger(__name__)

# Ensure WordNet data is available (idempotent)
try:
    wordnet.synsets("test")
except LookupError:
    nltk.download("wordnet", quiet=True)
    nltk.download("omw-1.4", quiet=True)

# Simple stop-word list for French — skip these when choosing a content word
_FR_STOPWORDS = frozenset(
    "le la les un une des de du d l au aux en et ou mais ni car que qui "
    "je tu il elle on nous vous ils elles se ce cette ces mon ma mes ton "
    "ta tes son sa ses notre nos votre vos leur leurs ne pas plus est a "
    "sont ont pour par avec dans sur entre".split()
)

_OPERATIONS = ("delete", "swap", "synonym")


def _content_word_indices(words: list[str]) -> list[int]:
    """Return indices of content words (non-stopword, alphabetic, len >= 3)."""
    return [
        i for i, w in enumerate(words)
        if w.lower() not in _FR_STOPWORDS and w.isalpha() and len(w) >= 3
    ]


def _get_synonym(word: str) -> Optional[str]:
    """Try to find a WordNet synonym for *word* (English or French)."""
    for lang in ("fra", "eng"):
        synsets = wordnet.synsets(word, lang=lang)
        for syn in synsets:
            for lemma in syn.lemmas(lang):
                name = lemma.name().replace("_", " ")
                if name.lower() != word.lower():
                    return name
    return None


def _delete_word(words: list[str]) -> tuple[list[str], int, str, str, PrimaryTag]:
    """Delete one content word."""
    candidates = _content_word_indices(words)
    if not candidates:
        candidates = list(range(len(words)))
    idx = random.choice(candidates)
    original = words[idx]
    new_words = words[:idx] + words[idx + 1:]
    return new_words, idx, original, "", PrimaryTag.OMISSION


def _swap_words(words: list[str]) -> tuple[list[str], int, str, str, PrimaryTag]:
    """Swap two adjacent words."""
    if len(words) < 2:
        return _delete_word(words)
    idx = random.randint(0, len(words) - 2)
    original = f"{words[idx]} {words[idx + 1]}"
    new_words = list(words)
    new_words[idx], new_words[idx + 1] = new_words[idx + 1], new_words[idx]
    injected = f"{new_words[idx]} {new_words[idx + 1]}"
    return new_words, idx, original, injected, PrimaryTag.GRAMMAR


def _synonym_replace(words: list[str]) -> tuple[list[str], int, str, str, PrimaryTag]:
    """Replace one content word with a synonym."""
    candidates = _content_word_indices(words)
    random.shuffle(candidates)
    for idx in candidates:
        syn = _get_synonym(words[idx])
        if syn is not None:
            original = words[idx]
            new_words = list(words)
            new_words[idx] = syn
            return new_words, idx, original, syn, PrimaryTag.MISTRANSLATION
    # Fallback: no synonym found, do a swap instead
    return _swap_words(words)


async def inject_random(
    segment: CorpusSegment,
    target_tom: TOMLevel | None = None,
) -> tuple[str, list[InjectedError]]:
    """Apply a single random perturbation to the reference translation.

    Args:
        segment: Corpus segment whose ``reference_translation`` will be perturbed.
        target_tom: Optional ToM level to assign. Defaults to ``1st_machine``.

    Returns:
        ``(modified_text, [InjectedError])``
    """
    text = segment.reference_translation
    words = text.split()

    if len(words) < 2:
        logger.warning("Segment %s too short for perturbation", segment.segment_id)
        return text, []

    op = random.choice(_OPERATIONS)
    logger.info("B0 random perturbation [%s] on segment %s", op, segment.segment_id)

    if op == "delete":
        new_words, idx, original, injected, tag = _delete_word(words)
    elif op == "swap":
        new_words, idx, original, injected, tag = _swap_words(words)
    else:
        new_words, idx, original, injected, tag = _synonym_replace(words)

    modified_text = " ".join(new_words)

    # Compute character-level span in modified text
    if injected:
        span_start = modified_text.find(injected)
        span_end = span_start + len(injected) if span_start >= 0 else 0
    else:
        # Deletion: span is at the position where the word was removed
        span_start = sum(len(w) + 1 for w in new_words[:idx])
        span_end = span_start  # zero-width span for omission

    tom = target_tom or TOMLevel.FIRST_ORDER_MACHINE

    error = InjectedError(
        error_id=str(uuid.uuid4()),
        span_start=max(span_start, 0),
        span_end=max(span_end, 0),
        original_text=original,
        injected_text=injected,
        primary_tag=tag,
        error_type=f"random_{op}",
        severity=Severity.MINOR,
        tom_level=tom,
        primary_skill=SkillID.S1 if tag == PrimaryTag.GRAMMAR else SkillID.S4,
        secondary_skills=[],
        severity_range=[Severity.MINOR],
        direction="both",
        explanation=ContrastiveExplanation(
            mt_interpretation=f"Random {op} applied — no MT reasoning involved.",
            actual_meaning=f"Original word/phrase: '{original}'",
            reader_impact=f"Reader sees '{injected or '[deleted]'}' instead of '{original}'.",
            correction_rationale=f"Restore the original text: '{original}'.",
        ),
        brief_explanation=f"B0 random {op}",
    )

    return modified_text, [error]


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    dummy = CorpusSegment(
        segment_id="test-b0-001",
        source_text="The European Commission has proposed new regulations.",
        reference_translation="La Commission europeenne a propose de nouvelles reglementations.",
        source_lang="en",
        target_lang="fr",
        corpus_origin="europarl",
        domain="parliamentary",
        complexity_score=0.4,
        terminology_density=0.1,
        register="formal",
    )

    async def _run() -> None:
        modified, errors = await inject_random(dummy)
        print(f"Original:  {dummy.reference_translation}")
        print(f"Modified:  {modified}")
        for e in errors:
            print(f"  -> {e.primary_tag.value}/{e.error_type} "
                  f"[{e.span_start}:{e.span_end}] "
                  f"'{e.original_text}' -> '{e.injected_text}'")

    asyncio.run(_run())
