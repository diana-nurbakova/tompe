"""Shared configuration for pipeline validation experiments.

Central config for paths, thresholds, batch parameters, and baseline
definitions matching pipeline-validation-spec-v2 §2 and §4.
"""

from __future__ import annotations

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CORPORA_DIR = DATA_DIR / "corpora"
CODEBOOK_PATH = DATA_DIR / "codebook" / "error_codebook_fr_en.json"
ITEMS_DIR = DATA_DIR / "items"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "pipeline_validation" / "results"

# ── Language pair ─────────────────────────────────────────────────────────────

SOURCE_LANG = "en"
TARGET_LANG = "fr"
DIRECTION = "en_fr"

# ── Batch specification (spec §2.1) ──────────────────────────────────────────

TOTAL_ITEMS = 200
ITEMS_PER_CORPUS = 50
CORPORA = ["europarl", "dgt_tm", "eurlex", "unpc"]

MT_SYSTEMS = {
    "google_translate": 100,
    "deepseek_v3": 100,
}

ITEMS_PER_TOM_LEVEL = 50  # ~50 per level (L0, L1, L2, L3)
TOM_LEVELS = ["1st_machine", "1st_author", "2nd_reader", "recursive"]

CLEAN_RATIO = 0.25  # 50 out of 200 items have no errors
CLEAN_ITEMS = 50
INJECTED_ITEMS = 150

SEVERITY_DISTRIBUTION = {"minor": 1, "major": 2, "critical": 0}
MAX_ERRORS_PER_ITEM = 2

# ── Baseline specification (spec §4) ─────────────────────────────────────────

BASELINE_ITEMS = 60  # 60 segments shared across all conditions
BASELINE_ITEMS_PER_TOM = 15  # 15 per ToM level

BASELINE_CONDITIONS = ["B0_random", "B1_single_step", "B2_unconstrained", "full_pipeline"]

# ── Track A thresholds (spec §3) ─────────────────────────────────────────────

STRUCTURAL_PASS_TARGET = 0.90
GEMBA_DETECTION_TARGET = 0.80
IOU_THRESHOLD = 0.5

# ── Track C annotation set (spec §5.2 from annotation-tool-spec) ─────────────

ANNOTATION_PIPELINE_PER_TOM = 6  # 6 items per ToM level from full pipeline (24 total)
ANNOTATION_BASELINE_PER_CONDITION = 6  # 6 items per baseline (18 total)
ANNOTATION_AUTHENTIC = 12  # 12 authentic MT items (if available)
ANNOTATION_CLEAN = 12  # 12 clean items
ANNOTATION_PRACTICE = 3  # 3 practice items (excluded from analysis)

# Total: 24 + 18 + 12 + 12 = 66 items + 3 practice (without authentic: same)
# With authentic: 24 + 18 + 12 + 12 = 66 + 12 authentic = 78 + 3 practice = 81

ANNOTATION_RANDOMISATION_SEED = 42

# ── LLM configuration ────────────────────────────────────────────────────────

DEFAULT_LLM_CONFIG = {
    "provider": "openai",
    "model": "gpt-4.1",
    "temperature": 0.3,
    "max_tokens": 2048,
}

# ── xCOMET configuration ─────────────────────────────────────────────────────

XCOMET_MODEL = "Unbabel/XCOMET-XL"
XCOMET_BATCH_SIZE = 16


def ensure_dirs() -> None:
    """Create output directories if they don't exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "track_a").mkdir(exist_ok=True)
    (RESULTS_DIR / "track_b").mkdir(exist_ok=True)
    (RESULTS_DIR / "track_c").mkdir(exist_ok=True)
    (RESULTS_DIR / "figures").mkdir(exist_ok=True)
    (RESULTS_DIR / "tables").mkdir(exist_ok=True)
