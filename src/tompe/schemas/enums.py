"""Shared enumerations for the ToM-PE platform."""

from enum import Enum


class PrimaryTag(str, Enum):
    """Primary error tags — 10 tags mapped to MQM dimensions.

    From spec v1.1 §1.3. Tag names are semantically meaningful (UPPER_SNAKE_CASE)
    to activate LLM pre-trained knowledge during injection.
    """

    MISTRANSLATION = "MISTRANSLATION"  # Accuracy: mistranslation, sense, cognate
    OMISSION = "OMISSION"  # Accuracy: content dropped
    ADDITION = "ADDITION"  # Accuracy: content fabricated/added
    UNTRANSLATED = "UNTRANSLATED"  # Accuracy: source left untranslated
    GRAMMAR = "GRAMMAR"  # Linguistic conventions: morphosyntax
    TERMINOLOGY = "TERMINOLOGY"  # Domain-specific term errors
    STYLE = "STYLE"  # Awkward, unidiomatic, register
    LOCALE = "LOCALE"  # Date, number, currency format
    SPELLING = "SPELLING"  # Surface form: diacritics, capitalization
    PUNCTUATION = "PUNCTUATION"  # Punctuation errors (weight 0.1 for minor)


# Backward compatibility — maps old 5-category MQM to the new 10-tag system
class MQMCategory(str, Enum):
    """Legacy 5-category MQM dimensions. Use PrimaryTag for new code."""

    ACCURACY = "accuracy"
    FLUENCY = "fluency"
    TERMINOLOGY = "terminology"
    STYLE = "style"
    LOCALE = "locale"


class TOMLevel(str, Enum):
    """Maps error detection to Theory of Mind demand."""

    FIRST_ORDER_MACHINE = "1st_machine"  # What did the MT "think"?
    FIRST_ORDER_AUTHOR = "1st_author"  # What did the author intend?
    SECOND_ORDER_READER = "2nd_reader"  # What will the reader infer?
    RECURSIVE_MULTI = "recursive"  # Multi-agent reasoning required


class SkillID(str, Enum):
    """7 core PE competency skills — from spec v1.1 §3.2.

    Ordered by empirical difficulty gradient (S1 easiest → S7 hardest),
    following Temnikova 2010 and Daems et al. 2017.
    """

    S1 = "S1"  # Surface Error Detection (spelling, punctuation)
    S2 = "S2"  # Grammatical Error Detection (agreement, tense, word order)
    S3 = "S3"  # Meaning Transfer Verification (mistranslation, false cognates)
    S4 = "S4"  # Completeness Verification (omission, addition, untranslated)
    S5 = "S5"  # Terminology Verification (domain terms, IATE)
    S6 = "S6"  # Pragmatic & Style Evaluation (register, idiom, locale)
    S7 = "S7"  # Coherence & Discourse Evaluation (cross-sentence, anaphora)


class AnnotationLevel(str, Enum):
    """Progressive scaffolding levels — maps to CCL stages."""

    NAVIGATOR = "navigator"  # Level 0: Full annotations visible
    SCOUT = "scout"  # Level 1: Location hints, no labels
    ANALYST = "analyst"  # Level 2: No annotations
    EXPERT = "expert"  # Level 3: No annotations + clean spans + multi-system


class ItemPathway(str, Enum):
    CONTROLLED = "controlled"  # Errors injected into human reference
    AUTHENTIC = "authentic"  # Real MT errors detected via QE pipeline


class ComparisonType(str, Enum):
    """Two distinct skills exercised through comparison tasks."""

    INDEPENDENT_EVAL = "independent_eval"
    COMPARATIVE_RANKING = "comparative_ranking"


class Severity(str, Enum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
