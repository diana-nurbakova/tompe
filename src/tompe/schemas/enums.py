"""Shared enumerations for the ToM-PE platform."""

from enum import Enum


class MQMCategory(str, Enum):
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


class AnnotationLevel(str, Enum):
    """Progressive scaffolding levels — maps to CCL stages."""

    NAVIGATOR = "navigator"  # Level 0: Full annotations visible
    GUIDED = "guided"  # Level 1: Location hints, no labels
    INDEPENDENT = "independent"  # Level 2: No annotations
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
