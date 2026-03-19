"""MQM-to-ToM mapping (ECTEL Spec §2).

Defines the 7-skill / ToM-level model and mapping rules for external studies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Optional


class TomRank(IntEnum):
    """Ordinal ToM rank for rank-correlation tests (Spec §2.3).

    S4, S5, S6 are tied at rank 4 (all require 2nd+ order ToM).
    """
    S1 = 1
    S2 = 2
    S3 = 3
    S4 = 4
    S5 = 4
    S6 = 4
    S7 = 5


# Mapping as a plain dict for convenience
SKILL_TO_TOM_RANK: Dict[str, int] = {
    "S1": 1, "S2": 2, "S3": 3,
    "S4": 4, "S5": 4, "S6": 4,
    "S7": 5,
}

SKILL_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]

TOM_LEVEL_LABELS = {
    "S1": "1st_machine (form)",
    "S2": "1st_machine (form)",
    "S3": "1st_machine (meaning)",
    "S4": "1st_author",
    "S5": "2nd_reader",
    "S6": "2nd_reader",
    "S7": "recursive",
}


@dataclass
class SkillMapping:
    """A single error-type-to-skill mapping from an external study."""
    error_type: str
    skill: str
    tom_rank: int
    notes: str = ""

    def __post_init__(self):
        self.tom_rank = SKILL_TO_TOM_RANK[self.skill]


# --- MQM direct mapping (Spec §2.1) ---

MQM_TO_SKILL: Dict[str, str] = {
    "Spelling": "S1",
    "Punctuation": "S1",
    "Grammar": "S2",
    "Word form": "S2",
    "Mistranslation": "S3",
    "Wrong sense": "S3",
    "False cognate": "S3",
    "Number": "S3",
    "Omission": "S4",
    "Addition": "S4",
    "Untranslated": "S4",
    "Terminology": "S5",
    "Register": "S6",
    "Style": "S6",
    "Locale": "S6",
    "Coherence": "S7",
    "Cohesion": "S7",
    "Connectives": "S7",
}

# --- Broad-category mapping (Spec §2.2, rule 3) ---

BROAD_TO_SKILLS: Dict[str, List[str]] = {
    "fluency": ["S1", "S2"],
    "accuracy": ["S3", "S4"],
}


def map_error_type(error_type: str, taxonomy: str = "mqm") -> Optional[str]:
    """Map an error type string to a skill ID.

    Args:
        error_type: The error type label from the source study.
        taxonomy: One of 'mqm', 'broad', or 'temnikova'.

    Returns:
        Skill ID (e.g. 'S3') or None if unmappable.
    """
    if taxonomy == "mqm":
        return MQM_TO_SKILL.get(error_type)
    elif taxonomy == "broad":
        skills = BROAD_TO_SKILLS.get(error_type.lower())
        return skills[0] if skills else None  # return lowest skill
    return None


def tom_rank(skill: str) -> int:
    """Return the ordinal ToM rank for a skill."""
    return SKILL_TO_TOM_RANK[skill]


def is_low_tom(skill: str) -> bool:
    """True if S1 or S2 (1st-order machine form)."""
    return skill in ("S1", "S2")


def is_high_tom(skill: str) -> bool:
    """True if S3+ (requires meaning comparison or higher)."""
    return skill in ("S3", "S4", "S5", "S6", "S7")


def tom_group(skill: str) -> str:
    """Return 'low' for S1-S2, 'high' for S3+."""
    return "low" if is_low_tom(skill) else "high"
