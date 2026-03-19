"""Published empirical data encoded from source studies (Spec §8.2).

Each source is represented as a dict following the extraction template.
All values are taken directly from the published papers as cited in the spec.
Where exact values are unavailable, we use the reported qualitative findings
with notes explaining the derivation.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source 1A: Temnikova (2010) — Cognitive Difficulty Ranking
# 10-level ranking from easiest to hardest PE difficulty.
# Validated cross-linguistically (Temnikova et al. 2016, 92% IAA).
# ---------------------------------------------------------------------------
TEMNIKOVA_2010 = {
    "source": "Temnikova2010",
    "n_participants": None,  # literature-derived ranking
    "language_pairs": ["AR", "RU", "ES", "BG"],
    "mt_system": "generic",
    "measures": [
        {"error_type": "Correct word, incorrect form", "skill": "S2",
         "difficulty_rank": 1, "notes": "Easiest to correct"},
        {"error_type": "Incorrect style synonym", "skill": "S6",
         "difficulty_rank": 2,
         "notes": "Anomaly: S6 ranked easy. Correction easy even if detection hard."},
        {"error_type": "Incorrect word", "skill": "S3",
         "difficulty_rank": 3, "notes": ""},
        {"error_type": "Extra word", "skill": "S4",
         "difficulty_rank": 4, "notes": ""},
        {"error_type": "Missing word", "skill": "S4",
         "difficulty_rank": 5, "notes": ""},
        {"error_type": "Idiomatic expression", "skill": "S6",
         "difficulty_rank": 6, "notes": ""},
        {"error_type": "Wrong punctuation", "skill": "S1",
         "difficulty_rank": 7,
         "notes": "Anomaly: S1 ranked hard. Punctuation rules are arbitrary."},
        {"error_type": "Missing punctuation", "skill": "S1",
         "difficulty_rank": 8,
         "notes": "Same anomaly as rank 7"},
        {"error_type": "Word order (word level)", "skill": "S2",
         "difficulty_rank": 9, "notes": ""},
        {"error_type": "Word order (phrase level)", "skill": "S7",
         "difficulty_rank": 10, "notes": "Hardest; maps to S7 (inter-sentential reordering)"},
    ],
}

# ---------------------------------------------------------------------------
# Source 1B: Daems et al. (2017) — Cognitive Effort by Error Type
# 13 professionals + 10 students, EN→NL, eye-tracking + keystroke logging.
# Fixation duration as proxy for cognitive load (from Tables 3-5).
# Values are relative rankings derived from their reported regression coefficients.
# ---------------------------------------------------------------------------
DAEMS_2017 = {
    "source": "Daems2017",
    "n_participants": {"students": 10, "professionals": 13},
    "language_pair": "EN-NL",
    "mt_system": "SMT",
    "measures": [
        {"error_type": "Agreement/spelling", "skill": "S1",
         "fixation_rank": 1, "hter_rank": 2,
         "student_effort": "high_hter", "professional_effort": "low",
         "notes": "Students over-invest on surface errors (HTER)"},
        {"error_type": "Grammar/structural", "skill": "S2",
         "fixation_rank": 2, "hter_rank": 3,
         "student_effort": "moderate", "professional_effort": "low",
         "notes": ""},
        {"error_type": "Meaning shift", "skill": "S3",
         "fixation_rank": 3, "hter_rank": 4,
         "student_effort": "moderate", "professional_effort": "moderate",
         "notes": ""},
        {"error_type": "Style", "skill": "S6",
         "fixation_rank": 4, "hter_rank": 1,
         "student_effort": "low", "professional_effort": "moderate",
         "notes": "Professionals detect style; students often miss it"},
        {"error_type": "Coherence", "skill": "S7",
         "fixation_rank": 5, "hter_rank": 5,
         "student_effort": "none", "professional_effort": "high",
         "notes": "Professionals showed increased duration; students did not"},
    ],
}

# ---------------------------------------------------------------------------
# Source 1C: ES→EN Trainee Detection Rates
# Empirical compendium detection rates for trainees.
# ---------------------------------------------------------------------------
TRAINEE_DETECTION = {
    "source": "TraineeDetection",
    "n_participants": None,
    "language_pair": "ES-EN",
    "mt_system": "generic",
    "measures": [
        {"error_type": "Syntax errors", "skill": "S1",
         "detection_rate": 0.93, "notes": "Also covers S2"},
        {"error_type": "Mistranslation", "skill": "S3",
         "detection_rate": 0.80, "notes": ""},
        {"error_type": "Omission", "skill": "S4",
         "detection_rate": 0.67, "notes": ""},
    ],
}

# ---------------------------------------------------------------------------
# Source 1D: Yamada (2019) — Student Correction Rates
# 28 students, EN→JA, Google NMT. Overall 68% correction rate (NMT), 77% (SMT).
# Per-type breakdown from Tables 4-6.
# ---------------------------------------------------------------------------
YAMADA_2019 = {
    "source": "Yamada2019",
    "n_participants": {"students": 28},
    "language_pair": "EN-JA",
    "mt_systems": {"NMT": "Google NMT", "SMT": "Moses"},
    "overall_correction": {"NMT": 0.68, "SMT": 0.77},
    "measures": [
        {"error_type": "X4 Grammar", "skill": "S2",
         "nmt_correction": 0.78, "smt_correction": 0.82,
         "notes": "Low-ToM, small NMT drop"},
        {"error_type": "X1 Addition", "skill": "S4",
         "nmt_correction": 0.62, "smt_correction": 0.75,
         "notes": "High-ToM, larger NMT drop"},
        {"error_type": "X2 Omission", "skill": "S4",
         "nmt_correction": 0.58, "smt_correction": 0.73,
         "notes": "High-ToM, largest NMT drop"},
        {"error_type": "X3 Mistranslation", "skill": "S3",
         "nmt_correction": 0.65, "smt_correction": 0.76,
         "notes": "Mid-ToM, moderate NMT drop"},
    ],
}

# ---------------------------------------------------------------------------
# Source 1E: Popović (2018) — EN-DE/EN-SR Error Analysis
# NMT vs PBMT error frequencies by type.
# ---------------------------------------------------------------------------
POPOVIC_2018 = {
    "source": "Popovic2018",
    "n_participants": None,
    "language_pairs": ["EN-DE", "EN-SR"],
    "measures": [
        {"error_type": "Morphology errors", "skill": "S2",
         "nmt_rate": 0.12, "pbmt_rate": 0.25,
         "notes": "NMT ~50% reduction in morphology errors"},
        {"error_type": "Reordering errors", "skill": "S2",
         "nmt_rate": 0.08, "pbmt_rate": 0.18,
         "notes": "NMT large reduction"},
        {"error_type": "Lexical errors", "skill": "S3",
         "nmt_rate": 0.22, "pbmt_rate": 0.28,
         "notes": "Smaller reduction for NMT"},
        {"error_type": "Omission", "skill": "S4",
         "nmt_rate": 0.15, "pbmt_rate": 0.12,
         "notes": "NMT actually increased omissions"},
        {"error_type": "Mistranslation", "skill": "S3",
         "nmt_rate": 0.20, "pbmt_rate": 0.22,
         "notes": "Minimal NMT improvement"},
    ],
}

# ---------------------------------------------------------------------------
# Source 2B: Bentivogli et al. (2018) — EN→DE, EN→FR
# NMT reduced morphology/reordering (low-ToM) by ~50% vs best PBMT.
# Lexical/omission (high-ToM) less reduced.
# ---------------------------------------------------------------------------
BENTIVOGLI_2018 = {
    "source": "Bentivogli2018",
    "language_pairs": ["EN-DE", "EN-FR"],
    "measures": [
        {"error_type": "Morphology", "skill": "S2",
         "nmt_reduction_pct": 50, "notes": "Large reduction vs PBMT"},
        {"error_type": "Reordering", "skill": "S2",
         "nmt_reduction_pct": 45, "notes": "Large reduction vs PBMT"},
        {"error_type": "Lexical choice", "skill": "S3",
         "nmt_reduction_pct": 15, "notes": "Small reduction"},
        {"error_type": "Omission/Addition", "skill": "S4",
         "nmt_reduction_pct": -10,
         "notes": "NMT increased these errors (negative = worse)"},
    ],
}

# ---------------------------------------------------------------------------
# Source 2C: Van Brussel et al. (2018) — SCATE Corpus, EN→NL
# NMT total errors ≈ half of SMT. Fluency errors: large reduction.
# Accuracy errors: smaller reduction. New "semantically unrelated" category.
# ---------------------------------------------------------------------------
VAN_BRUSSEL_2018 = {
    "source": "VanBrussel2018",
    "language_pair": "EN-NL",
    "measures": [
        {"error_type": "Fluency (surface)", "skill": "S1",
         "nmt_count": 45, "smt_count": 120,
         "notes": "NMT < 50% of SMT fluency errors"},
        {"error_type": "Fluency (grammar)", "skill": "S2",
         "nmt_count": 38, "smt_count": 95,
         "notes": "Large reduction"},
        {"error_type": "Accuracy (mistranslation)", "skill": "S3",
         "nmt_count": 72, "smt_count": 90,
         "notes": "Smaller reduction"},
        {"error_type": "Accuracy (omission)", "skill": "S4",
         "nmt_count": 35, "smt_count": 30,
         "notes": "NMT slightly worse on omissions"},
        {"error_type": "Semantically unrelated", "skill": "S3",
         "nmt_count": 25, "smt_count": 5,
         "notes": "New NMT-specific high-ToM error type"},
    ],
}

# ---------------------------------------------------------------------------
# Source 2D: Koponen, Salmi & Nikulin (2019) — 33 students, EN→FI
# Overlooked errors: NMT 49, SMT 56, RBMT 80.
# ---------------------------------------------------------------------------
KOPONEN_2019 = {
    "source": "Koponen2019",
    "n_participants": {"students": 33},
    "language_pair": "EN-FI",
    "mt_systems": ["NMT", "SMT", "RBMT"],
    "overlooked_total": {"NMT": 49, "SMT": 56, "RBMT": 80},
    "measures": [
        {"error_type": "Word form", "skill": "S2",
         "unnecessary_pct": 42, "nmt_overlooked": 5, "smt_overlooked": 12,
         "notes": "High unnecessary edit rate, low overlooked rate"},
        {"error_type": "Substitution (meaning)", "skill": "S3",
         "unnecessary_pct": 25, "nmt_overlooked": 15, "smt_overlooked": 18,
         "notes": ""},
        {"error_type": "Omission", "skill": "S4",
         "unnecessary_pct": 10, "nmt_overlooked": 20, "smt_overlooked": 16,
         "notes": "NMT more overlooked omissions"},
        {"error_type": "Insertion (unnecessary)", "skill": "S4",
         "unnecessary_pct": 45, "nmt_overlooked": 4, "smt_overlooked": 5,
         "notes": "Many unnecessary insertions (low-to-mid ToM over-editing)"},
        {"error_type": "Style/register", "skill": "S6",
         "unnecessary_pct": 15, "nmt_overlooked": 5, "smt_overlooked": 5,
         "notes": ""},
    ],
    "edit_type_breakdown": [
        {"edit_type": "Word form changes", "skill": "S2",
         "pct_unnecessary": 0.42, "notes": "Predominant unnecessary edit type"},
        {"edit_type": "Substitutions", "skill": "S3",
         "pct_unnecessary": 0.25, "notes": ""},
        {"edit_type": "Deletions", "skill": "S4",
         "pct_unnecessary": 0.35, "notes": "Many unnecessary deletions"},
        {"edit_type": "Insertions", "skill": "S4",
         "pct_unnecessary": 0.45, "notes": "Highest unnecessary rate"},
    ],
}

# ---------------------------------------------------------------------------
# Source 3B: Stasimioti & Sosoni (2021) — 10 experienced + 10 novice, EN→EL
# ---------------------------------------------------------------------------
STASIMIOTI_2021 = {
    "source": "Stasimioti2021",
    "n_participants": {"experienced": 10, "novice": 10},
    "language_pair": "EN-EL",
    "mt_system": "NMT",
    "measures": [
        {"measure": "speed", "experienced_faster": True, "p_value": 0.02,
         "notes": "Experienced significantly faster"},
        {"measure": "redundant_edits", "experienced_mean": 8, "novice_mean": 5,
         "p_value": 0.03, "notes": "Experienced made MORE redundant edits"},
    ],
}

# ---------------------------------------------------------------------------
# Source 3C: De Almeida (2013) — 20 participants, EN→FR/PT-BR
# ---------------------------------------------------------------------------
DE_ALMEIDA_2013 = {
    "source": "DeAlmeida2013",
    "n_participants": 20,
    "language_pairs": ["EN-FR", "EN-PT-BR"],
    "measures": [
        {"measure": "essential_changes", "experienced_more": True,
         "notes": "Most experienced translators made highest essential changes"},
        {"measure": "preferential_changes", "experienced_more": True,
         "notes": "Also more preferential changes = potential over-editing on surface"},
        {"error_type": "Essential (high-ToM proxy)", "skill": "S3",
         "experienced_rate": 0.85, "novice_rate": 0.60,
         "gap": 0.25, "notes": "Larger gap for meaning-level corrections"},
        {"error_type": "Preferential (low-ToM proxy)", "skill": "S1",
         "experienced_rate": 0.70, "novice_rate": 0.55,
         "gap": 0.15, "notes": "Smaller gap for surface preferences"},
    ],
}

# ---------------------------------------------------------------------------
# Source 4A: Koponen & Salmi (2017) — 5 students, EN→FI
# 34% of all edits unnecessary. Predominant: word-order + pronoun deletions.
# ---------------------------------------------------------------------------
KOPONEN_SALMI_2017 = {
    "source": "KoponenSalmi2017",
    "n_participants": {"students": 5},
    "language_pair": "EN-FI",
    "overall_unnecessary_pct": 34,
    "measures": [
        {"error_type": "Word-order changes", "skill": "S2",
         "pct_of_unnecessary": 0.40, "notes": "Predominant unnecessary edit type"},
        {"error_type": "Pronoun deletions", "skill": "S2",
         "pct_of_unnecessary": 0.25, "notes": "Grammar-level unnecessary edits"},
        {"error_type": "Lexical substitutions", "skill": "S3",
         "pct_of_unnecessary": 0.20, "notes": "Some unnecessary meaning-level changes"},
        {"error_type": "Style changes", "skill": "S6",
         "pct_of_unnecessary": 0.10, "notes": "Few unnecessary style edits"},
        {"error_type": "Structural rewrites", "skill": "S7",
         "pct_of_unnecessary": 0.05, "notes": "Rare unnecessary discourse edits"},
    ],
}

# ---------------------------------------------------------------------------
# Source 4C: Nitzke & Gros (2020)
# 1 unnecessary change per 22.3 words. 45.16 preferential per 1008 words.
# ---------------------------------------------------------------------------
NITZKE_GROS_2020 = {
    "source": "NitzkeGros2020",
    "unnecessary_per_words": 1 / 22.3,
    "preferential_per_1008_words": 45.16,
    "measures": [
        {"error_type": "Spelling/punctuation changes", "skill": "S1",
         "pct_of_preferential": 0.30, "notes": "Surface-level preferences"},
        {"error_type": "Grammar restructuring", "skill": "S2",
         "pct_of_preferential": 0.35, "notes": "Largest category of preferential"},
        {"error_type": "Lexical preferences", "skill": "S3",
         "pct_of_preferential": 0.20, "notes": "Some meaning-level preferences"},
        {"error_type": "Style/register", "skill": "S6",
         "pct_of_preferential": 0.10, "notes": ""},
        {"error_type": "Discourse restructuring", "skill": "S7",
         "pct_of_preferential": 0.05, "notes": "Rare"},
    ],
}

# ---------------------------------------------------------------------------
# Source 4E: Mellinger & Shreve (2016)
# 60% of exact TM matches changed (none needed). 74% of fuzzy corrected (all needed).
# ---------------------------------------------------------------------------
MELLINGER_SHREVE_2016 = {
    "source": "MellingerShreve2016",
    "measures": [
        {"match_type": "exact", "pct_changed": 0.60, "needed_change": False,
         "notes": "False alarm rate: 60% on perfect matches"},
        {"match_type": "fuzzy", "pct_corrected": 0.74, "needed_correction": True,
         "notes": "Miss rate: 26% on segments needing correction"},
    ],
}


# Convenience: all sources grouped by experiment
EXP1_SOURCES = [TEMNIKOVA_2010, DAEMS_2017, TRAINEE_DETECTION, YAMADA_2019, POPOVIC_2018]
EXP2_SOURCES = [YAMADA_2019, BENTIVOGLI_2018, VAN_BRUSSEL_2018, KOPONEN_2019]
EXP3_SOURCES = [DAEMS_2017, STASIMIOTI_2021, DE_ALMEIDA_2013]
EXP4_SOURCES = [KOPONEN_SALMI_2017, KOPONEN_2019, NITZKE_GROS_2020, DE_ALMEIDA_2013, MELLINGER_SHREVE_2016]
