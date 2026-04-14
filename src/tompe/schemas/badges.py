"""Badge and XP data models for the gamification system.

From fluency-trap-badges-spec.md §9 — defines badge definitions, earned badges,
and student XP records.
"""

import math
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BadgeCategory(str, Enum):
    PROGRESSION = "progression"
    SPECIALISATION = "specialisation"
    BEHAVIOUR = "behaviour"


class BadgeTier(str, Enum):
    NONE = "none"       # For progression/behaviour (no tiers)
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class BadgeDefinition(BaseModel):
    """Static badge definition stored in config."""
    badge_id: str               # e.g. "grammar_guard"
    display_name: str           # e.g. "Grammar Guard"
    category: BadgeCategory
    description: str            # Displayed in tooltip
    icon_path: str              # Path to badge icon asset
    tier: BadgeTier = BadgeTier.NONE
    threshold: Optional[int] = None  # For specialisation badges
    mqm_tag: Optional[str] = None    # For specialisation badges


class EarnedBadge(BaseModel):
    """Record of a badge earned by a student."""
    badge_id: str
    student_id: str
    tier: BadgeTier = BadgeTier.NONE
    earned_at: datetime = Field(default_factory=datetime.now)
    exercise_id: Optional[str] = None  # Exercise where badge was earned
    count: int = 1              # For repeatable badges (Clean Sheet)


class StudentBadges(BaseModel):
    """All badges and XP for a single student. Stored as one file per student."""
    student_id: str
    earned_badges: list[EarnedBadge] = []
    total_xp: int = 0
    xp_history: list[dict] = []  # [{exercise_id, xp_earned, timestamp, breakdown}]

    # Specialisation detection counters (category -> count at L1+)
    detection_counts: dict[str, int] = {}

    # Behaviour counters
    clean_sheet_count: int = 0
    correct_disputes: int = 0

    def has_badge(self, badge_id: str, tier: BadgeTier = BadgeTier.NONE) -> bool:
        """Check if student has a specific badge (optionally at a specific tier)."""
        for b in self.earned_badges:
            if b.badge_id == badge_id:
                if tier == BadgeTier.NONE or b.tier == tier:
                    return True
        return False

    def get_highest_tier(self, badge_id: str) -> Optional[BadgeTier]:
        """Get the highest tier earned for a badge."""
        tier_order = [BadgeTier.BRONZE, BadgeTier.SILVER, BadgeTier.GOLD]
        highest = None
        for b in self.earned_badges:
            if b.badge_id == badge_id:
                if b.tier == BadgeTier.NONE:
                    return BadgeTier.NONE
                if highest is None or tier_order.index(b.tier) > tier_order.index(highest):
                    highest = b.tier
        return highest

    def add_badge(
        self,
        badge_id: str,
        tier: BadgeTier = BadgeTier.NONE,
        exercise_id: Optional[str] = None,
    ) -> EarnedBadge:
        """Add a newly earned badge."""
        badge = EarnedBadge(
            badge_id=badge_id,
            student_id=self.student_id,
            tier=tier,
            exercise_id=exercise_id,
        )
        self.earned_badges.append(badge)
        return badge

    def add_xp(self, xp: int, exercise_id: str, breakdown: Optional[dict] = None):
        """Add XP from an exercise."""
        self.total_xp += xp
        self.xp_history.append({
            "exercise_id": exercise_id,
            "xp_earned": xp,
            "timestamp": datetime.now().isoformat(),
            "breakdown": breakdown or {},
        })


# ── XP Calculation ──────────────────────────────────────────────────────────

TOM_MULTIPLIERS = {
    "1st_machine": 1.0,   # L0 surface fluency
    "1st_author": 1.25,   # L1 source comparison
    "2nd_reader": 1.5,    # L2 bilingual analysis
    "recursive": 2.0,     # L3 recursive/contextual
}

SCAFFOLDING_MULTIPLIERS = {
    "navigator": 0.5,  # L0 pre-annotations visible
    "scout": 1.0,      # L1
    "analyst": 1.5,     # L2
    "expert": 2.0,      # L3
}

# Base XP values
XP_DETECTION = 10
XP_CATEGORY_MATCH = 5
XP_SEVERITY_MATCH = 3
XP_FALSE_POSITIVE = -5


def compute_item_xp(
    true_positives: int,
    false_positives: int,
    category_matches: int,
    severity_matches: int,
    tom_level: str,
    scaffolding_level: str,
) -> tuple[int, dict]:
    """Compute XP for a single item response.

    Returns (total_xp, breakdown_dict).
    """
    tom_mult = TOM_MULTIPLIERS.get(tom_level, 1.0)
    scaff_mult = SCAFFOLDING_MULTIPLIERS.get(scaffolding_level, 1.0)

    detection_xp = math.ceil(true_positives * XP_DETECTION * tom_mult * scaff_mult)
    category_xp = math.ceil(category_matches * XP_CATEGORY_MATCH * tom_mult * scaff_mult)
    severity_xp = math.ceil(severity_matches * XP_SEVERITY_MATCH * tom_mult * scaff_mult)
    fp_penalty = math.ceil(false_positives * abs(XP_FALSE_POSITIVE) * tom_mult * scaff_mult)

    total = max(0, detection_xp + category_xp + severity_xp - fp_penalty)

    breakdown = {
        "detection_xp": detection_xp,
        "category_xp": category_xp,
        "severity_xp": severity_xp,
        "fp_penalty": fp_penalty,
        "tom_multiplier": tom_mult,
        "scaffolding_multiplier": scaff_mult,
    }
    return total, breakdown


# ── Specialisation thresholds ───────────────────────────────────────────────

CATEGORY_THRESHOLDS: dict[str, list[int]] = {
    "MISTRANSLATION": [10, 25, 50],
    "OMISSION":       [10, 25, 50],
    "ADDITION":       [8,  20, 40],
    "UNTRANSLATED":   [5,  15, 30],
    "GRAMMAR":        [10, 25, 50],
    "SPELLING":       [8,  20, 40],
    "PUNCTUATION":    [8,  20, 40],
    "TERMINOLOGY":    [8,  20, 40],
    "STYLE":          [8,  20, 40],
    "LOCALE":         [5,  15, 30],
}

CATEGORY_BADGE_NAMES: dict[str, str] = {
    "MISTRANSLATION": "accuracy_hunter",
    "OMISSION":       "gap_finder",
    "ADDITION":       "surplus_spotter",
    "UNTRANSLATED":   "code_switcher",
    "GRAMMAR":        "grammar_guard",
    "SPELLING":       "sharp_eye",
    "PUNCTUATION":    "punctuation_pro",
    "TERMINOLOGY":    "term_specialist",
    "STYLE":          "style_sentinel",
    "LOCALE":         "locale_expert",
}

CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "MISTRANSLATION": "Accuracy Hunter",
    "OMISSION":       "Gap Finder",
    "ADDITION":       "Surplus Spotter",
    "UNTRANSLATED":   "Code Switcher",
    "GRAMMAR":        "Grammar Guard",
    "SPELLING":       "Sharp Eye",
    "PUNCTUATION":    "Punctuation Pro",
    "TERMINOLOGY":    "Term Specialist",
    "STYLE":          "Style Sentinel",
    "LOCALE":         "Locale Expert",
}

PROGRESSION_BADGES = {
    0: ("navigator", "Navigator"),
    1: ("scout", "Scout"),
    2: ("analyst", "Analyst"),
    3: ("expert", "Expert"),
}

LEVEL_TO_INT: dict[str, int] = {
    "navigator": 0,
    "scout": 1,
    "analyst": 2,
    "expert": 3,
}
