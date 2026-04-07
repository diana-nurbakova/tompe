"""Configuration for ToM validation experiment.

Paths, thresholds, and the MQM-to-ToM mapping table (Spec §3).
"""

from __future__ import annotations

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "wmt-mqm"
MQM_TSV = DATA_DIR / "mqm_newstest2020_ende.tsv"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "tom_validation"

# ── Span alignment ──────────────────────────────────────────────────
IOU_THRESHOLD = 0.5          # default for cross-rater span matching
IOU_THRESHOLD_LENIENT = 0.3  # sensitivity S5
IOU_THRESHOLD_STRICT = 0.7   # sensitivity S6

# ── MQM → ToM mapping (Spec §3.1) ──────────────────────────────────
# Keys are exact category strings from the WMT 2020 TSV.
MQM_TO_TOM: dict[str, int] = {
    # L0 — target-only pattern matching
    "Fluency/Spelling":                         0,
    "Fluency/Punctuation":                      0,
    "Fluency/Character encoding":               0,
    "Non-translation!":                         0,
    "Fluency/Grammar":                          0,  # conservative (Option 1, §3.3)

    # L1 — source consultation needed
    "Accuracy/Untranslated text":               1,

    # L2 — source-author model required
    "Terminology/Inappropriate for context":    2,
    "Terminology/Inconsistent use of terminology": 2,
    "Accuracy/Omission":                        2,
    "Accuracy/Addition":                        2,
    "Accuracy/Mistranslation":                  2,  # Strategy A (default, §3.2)

    # L3 — reader-facing impact
    "Style/Awkward":                            3,
    "Fluency/Register":                         3,
    "Locale convention/Currency format":        3,
    "Locale convention/Address format":         3,
    "Locale convention/Date format":            3,
    "Locale convention/Time format":            3,
}

# Categories to exclude from analysis (unmappable)
UNMAPPED_CATEGORIES = {"No-error", "Other", "Fluency/Inconsistency"}

# Severity weights (for reference)
SEVERITY_WEIGHTS = {"Major": 5, "Minor": 1, "Neutral": 0}

# ToM level labels for display
TOM_LABELS = {0: "L0", 1: "L1", 2: "L2", 3: "L3"}
