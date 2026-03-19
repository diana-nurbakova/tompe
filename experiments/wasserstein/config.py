"""Central configuration for all Wasserstein experiment parameters.

All archetype parameters, BKT priors, target profiles, and regularization
values live here so that Track A findings can update them in one place.
"""

from __future__ import annotations

import numpy as np

# =============================================================================
# Skill labels
# =============================================================================

SKILL_LABELS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
SKILL_NAMES = {
    "S1": "Surface",
    "S2": "Grammar",
    "S3": "Meaning",
    "S4": "Completeness",
    "S5": "Terminology",
    "S6": "Pragmatic",
    "S7": "Discourse",
}
N_SKILLS = 7

# =============================================================================
# Baseline detection rates (session 1) — spec §4.1.1
# =============================================================================

BASELINE_DETECTION_RATES = {
    "S1": 0.93,
    "S2": 0.85,
    "S3": 0.80,
    "S4": 0.67,
    "S5": 0.65,
    "S6": 0.50,
    "S7": 0.35,
}

BASELINE_VARIANCE = {
    "S1": 0.05,
    "S2": 0.08,
    "S3": 0.10,
    "S4": 0.12,
    "S5": 0.12,
    "S6": 0.15,
    "S7": 0.15,
}

# =============================================================================
# Learning rates per session — spec §4.1.2
# =============================================================================

LEARNING_RATES = {
    "S1": 0.030,
    "S2": 0.025,
    "S3": 0.020,
    "S4": 0.015,
    "S5": 0.015,
    "S6": 0.010,
    "S7": 0.008,
}

# =============================================================================
# BKT parameters per skill — spec §4.4
# =============================================================================

BKT_PARAMS = {
    "S1": {"P_L0": 0.35, "P_T": 0.15, "P_G": 0.25, "P_S": 0.05},
    "S2": {"P_L0": 0.25, "P_T": 0.12, "P_G": 0.20, "P_S": 0.08},
    "S3": {"P_L0": 0.15, "P_T": 0.10, "P_G": 0.15, "P_S": 0.12},
    "S4": {"P_L0": 0.08, "P_T": 0.08, "P_G": 0.20, "P_S": 0.15},
    "S5": {"P_L0": 0.10, "P_T": 0.08, "P_G": 0.10, "P_S": 0.12},
    "S6": {"P_L0": 0.06, "P_T": 0.06, "P_G": 0.15, "P_S": 0.15},
    "S7": {"P_L0": 0.04, "P_T": 0.05, "P_G": 0.10, "P_S": 0.18},
}

# =============================================================================
# Target mastery profile (expert-level)
# =============================================================================

TARGET_PROFILE = {
    "S1": 0.95,
    "S2": 0.90,
    "S3": 0.85,
    "S4": 0.80,
    "S5": 0.80,
    "S6": 0.75,
    "S7": 0.70,
}

# =============================================================================
# Over-editing parameters — spec §4.1.3
# =============================================================================

OVER_EDITING_INITIAL = 0.35
OVER_EDITING_DECAY_PER_SESSION = 0.02

# =============================================================================
# Unbalanced OT regularization sweep — spec §5.7
# =============================================================================

REG_ENTROPIC = 0.01
REG_M_VALUES = [0.1, 0.5, 1.0, 5.0]

# =============================================================================
# MQM → Skill mapping (for WMT data) — spec §3.2
# =============================================================================

MQM_TO_SKILL = {
    # Accuracy → S3 (Meaning) or S4 (Completeness)
    "Accuracy/Mistranslation": "S3",
    "Accuracy/Omission": "S4",
    "Accuracy/Addition": "S4",
    "Accuracy/Untranslated text": "S4",
    # Fluency → S1 (Surface) or S2 (Grammar) or S6 (Pragmatic)
    "Fluency/Spelling": "S1",
    "Fluency/Punctuation": "S1",
    "Fluency/Character encoding": "S1",
    "Fluency/Grammar": "S2",
    "Fluency/Register": "S6",
    "Fluency/Inconsistency": "S6",
    # Terminology → S5
    "Terminology/Inappropriate for context": "S5",
    "Terminology/Inconsistent use of terminology": "S5",
    # Style → S6
    "Style/Awkward": "S6",
    # Locale → S6
    "Locale convention/Currency format": "S6",
    "Locale convention/Address format": "S6",
    "Locale convention/Date format": "S6",
    "Locale convention/Time format": "S6",
    # Other
    "Non-translation!": "S3",
    "Other": "S3",
}

# Categories to exclude (not actual errors)
MQM_EXCLUDE = {"No-error", "no-error"}

# =============================================================================
# Graph adjacency (ToM skill dependency) — spec §2.1
# =============================================================================

ADJACENCY = np.array([
    [0, 1, 0, 0, 0, 0, 0],
    [1, 0, 1, 0, 0, 0, 0],
    [0, 1, 0, 1, 1, 1, 0],
    [0, 0, 1, 0, 0, 0, 0],
    [0, 0, 1, 0, 0, 0, 0],
    [0, 0, 1, 0, 0, 0, 1],
    [0, 0, 0, 0, 0, 1, 0],
])

# Edge weights from empirical detection rate gradient — spec §2.4
EDGE_WEIGHTS = {
    (0, 1): 8,   # S1-S2: |93%-85%|
    (1, 2): 5,   # S2-S3: |85%-80%|
    (2, 3): 13,  # S3-S4: |80%-67%|
    (2, 4): 15,  # S3-S5: |80%-65%|
    (2, 5): 30,  # S3-S6: |80%-50%|
    (5, 6): 15,  # S6-S7: |50%-35%|
}

# 2D embedding coordinates (ToM Level × Linguistic Grain) — spec §2.5
EMBEDDING_2D = np.array([
    [1, 1],  # S1: word-level, machine
    [2, 1],  # S2: phrase-level, machine
    [2, 2],  # S3: phrase-level, machine+author
    [3, 2],  # S4: sentence-level, author
    [1, 3],  # S5: word-level, reader
    [3, 3],  # S6: sentence-level, reader
    [4, 4],  # S7: multi-sentence, recursive
], dtype=float)

# =============================================================================
# Archetype definitions — spec §4.2
# =============================================================================

ARCHETYPE_INITIAL = np.array([0.65, 0.50, 0.35, 0.25, 0.20, 0.15, 0.10])

ARCHETYPES = {
    "coherent": {
        "name": "Coherent Learner",
        "n_instances": 5,
        "description": "Sequential mastery along ToM hierarchy",
    },
    "scattered": {
        "name": "Scattered Learner",
        "n_instances": 5,
        "description": "Random improvement, no developmental coherence",
    },
    "fast_plateau": {
        "name": "Fast Starter / Plateau",
        "n_instances": 4,
        "description": "Rapid early surface gains, then stagnation",
    },
    "slow_steady": {
        "name": "Slow Steady",
        "n_instances": 3,
        "description": "Uniform improvement across all skills",
    },
    "surface_only": {
        "name": "Surface-Only",
        "n_instances": 3,
        "description": "Masters S1-S2 but stalls on deeper skills",
    },
}

# Total: 5+5+4+3+3 = 20 synthetic students

# =============================================================================
# Experiment settings
# =============================================================================

N_SESSIONS = 10
NOISE_STD = 0.03
N_RANDOM_METRICS = 10
BONFERRONI_ALPHA = 0.05
