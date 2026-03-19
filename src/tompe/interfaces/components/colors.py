"""Annotation color scheme — consistent across all levels and interfaces.

From UI Spec v1.0 section 3.3.7. Colorblind-safe palette verified against
Deuteranopia, Protanopia, and Tritanopia simulations.
"""

from tompe.schemas.enums import PrimaryTag

# Maps PrimaryTag → (highlight_color for background, dot_color for labels/pills)
TAG_COLORS: dict[str, dict[str, str]] = {
    PrimaryTag.MISTRANSLATION: {"highlight": "#FEE2E2", "dot": "#E84855"},
    PrimaryTag.OMISSION: {"highlight": "#F3E8FF", "dot": "#7B2D8E"},
    PrimaryTag.ADDITION: {"highlight": "#FFF7ED", "dot": "#F18F01"},
    PrimaryTag.GRAMMAR: {"highlight": "#DBEAFE", "dot": "#2E86AB"},
    PrimaryTag.TERMINOLOGY: {"highlight": "#CCFBF1", "dot": "#0B7A75"},
    PrimaryTag.STYLE: {"highlight": "#ECFCCB", "dot": "#8DB580"},
    PrimaryTag.LOCALE: {"highlight": "#FEF3C7", "dot": "#A0522D"},
    PrimaryTag.UNTRANSLATED: {"highlight": "#FDE8E8", "dot": "#9B2335"},
    PrimaryTag.SPELLING: {"highlight": "#F0F0F0", "dot": "#6B7280"},
    PrimaryTag.PUNCTUATION: {"highlight": "#F5F5F5", "dot": "#9CA3AF"},
}

# Special colors (not tied to PrimaryTag)
CLEAN_SPAN_COLOR = {"highlight": "#D1FAE5", "dot": "#44AF69"}
REGION_HINT_COLOR = {"highlight": "#FEF9C3", "dot": "#D97706"}

# Student-facing label for each PrimaryTag
TAG_LABELS: dict[str, str] = {
    PrimaryTag.MISTRANSLATION: "Mistranslation",
    PrimaryTag.OMISSION: "Omission",
    PrimaryTag.ADDITION: "Addition",
    PrimaryTag.GRAMMAR: "Grammar",
    PrimaryTag.TERMINOLOGY: "Terminology",
    PrimaryTag.STYLE: "Style / Register",
    PrimaryTag.LOCALE: "Locale Convention",
    PrimaryTag.UNTRANSLATED: "Untranslated",
    PrimaryTag.SPELLING: "Spelling",
    PrimaryTag.PUNCTUATION: "Punctuation",
}

# Primary categories shown in the student classification UI (pills)
# Excludes Spelling and Punctuation which are sub-categories of surface errors
STUDENT_PILL_CATEGORIES: list[str] = [
    PrimaryTag.MISTRANSLATION,
    PrimaryTag.OMISSION,
    PrimaryTag.ADDITION,
    PrimaryTag.GRAMMAR,
    PrimaryTag.TERMINOLOGY,
    PrimaryTag.STYLE,
    PrimaryTag.LOCALE,
    PrimaryTag.UNTRANSLATED,
]
