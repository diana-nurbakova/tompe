# ToM-PE System Architecture

**Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training**

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Sources](#2-data-sources)
3. [Data Preparation Pipeline](#3-data-preparation-pipeline)
4. [Teacher Workflow](#4-teacher-workflow)
5. [Student Workflow](#5-student-workflow)
6. [Annotation Interface](#6-annotation-interface)
7. [Gamification & Badges](#7-gamification--badges)
8. [Backend Services](#8-backend-services)
9. [Scoring, Feedback, Analytics & Progression](#9-scoring-feedback-analytics--progression)
10. [Research Infrastructure](#10-research-infrastructure)
11. [Configuration & Deployment](#11-configuration--deployment)
12. [End-to-End Architecture Diagram](#12-end-to-end-architecture-diagram)

---

## 1. System Overview

ToM-PE is a pedagogical platform that trains translation students to critically evaluate machine translation (MT) output through scaffolded post-editing exercises. The platform is grounded in Theory of Mind (ToM) — the cognitive ability to attribute mental states to others — applied to understanding how MT systems "think" and where they fail.

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Teacher UI | **Streamlit** (`teacher_app.py`) | Corpus & item management, exercise builder, analytics |
| Student UI | **Gradio** (`student_app.py`) | Tutorial overlay + 3-phase PE training workflow, all 4 scaffolding levels (L0/L1/L2/L3), L3 comparison view |
| Annotation UI | **Gradio** (`annotation_app.py`) | Expert MQM annotation for pipeline validation |
| Backend API | **FastAPI** (`api.py`) | REST endpoints for student-facing operations |
| Data Pipeline | **Async Python** | Segment selection, MT generation, two-step controlled error injection, authentic error detection, comparison item assembly |
| LLM Integration | **httpx** (async) | OpenAI, Anthropic, Ollama, Together AI |
| MT Systems | **REST APIs** | Google Translate, DeepL |
| Data Models | **Pydantic v2** | Typed schemas for all entities |
| Storage | **JSON files** | One file per entity in `data/` directory |
| Authentication | **bcrypt + bearer tokens** | Student login, 7-day token sessions |
| Learner model | **BKT** (`bkt.py`) | Per-skill Bayesian Knowledge Tracing, drives mastery-gated promotion |

### Repository Structure

```
ToM-PE/
├── src/tompe/
│   ├── schemas/          # Pydantic data models
│   │   ├── annotation.py         # Scaffolding annotation config (L0-L3)
│   │   ├── badges.py             # Badge definitions, tiers, XP, StudentBadges store
│   │   ├── competency.py         # Skill competency framework (S1-S7), stages, mastery thresholds
│   │   ├── corpus.py             # CorpusSegment, MTOutput (+ is_human_reference, quality_score), IATETerm
│   │   ├── enums.py              # PrimaryTag, TOMLevel, Severity, SkillID, ComparisonType, ItemPathway
│   │   ├── error.py              # InjectedError, DetectedError, ContrastiveExplanation, SystemBehaviorExplanation, TechnicalExplanation
│   │   ├── expert_annotation.py  # ExpertAnnotation, ExplanationRating (validation)
│   │   ├── item.py               # AssessmentItem, ItemMetadata (comparison_outputs/comparison_type live here)
│   │   ├── response.py           # StudentResponse, Justification, VerificationResponse, SystemRanking, PEWorthinessVerdict
│   │   ├── scoring.py            # ScoringResult, CategoryScore, BlindSpot, StudentProfile, StudentBKT
│   │   └── session.py            # StudentAccount (consent + tutorial_completed), ClassGroup (badges_visible + threshold_overrides), Exercise (false_annotation_mode)
│   ├── pipeline/         # Item generation pipeline (controlled + authentic + comparison)
│   │   ├── segment_selector.py   # Filtering, dedup, length window, L3 long-segment + adjacency strategies
│   │   ├── mt_generator.py       # Google/DeepL/LLM-as-translator
│   │   ├── error_injector.py     # Two-step controlled injection + span realignment + opt-in GEMBA gating
│   │   ├── qe_validator.py       # GEMBA-MQM detection (xCOMET deferred — GPU)
│   │   ├── explanation_generator.py  # Layer 1/2a/2b with on-disk template cache
│   │   ├── item_builder.py       # Canonical orchestrator: CONTROLLED + AUTHENTIC pathways
│   │   ├── comparison_builder.py # L3 comparison-mode item assembly (multi-MT + human ref)
│   │   ├── authentic_detector.py # GEMBA-MQM → taxonomy mapping for real MT errors
│   │   ├── false_annotation_generator.py  # L0 decoys (LLM / rule / manual / none modes)
│   │   ├── corpus_ingest.py      # TMX + TSV upload parser used by the teacher UI
│   │   ├── llm_client.py         # Unified async LLM client (4 providers)
│   │   ├── codebook.py           # Error codebook loader and query interface
│   │   ├── mqm_taxonomy.py       # 42 error types with ToM/skill mappings
│   │   ├── tag_formats.py        # C1–C4 tag-format enum + render/parse/reformat helpers
│   │   ├── _injection_prompts.py # Step 1/2 prompt templates (tag-format parameterised)
│   │   ├── _false_annotation_prompts.py  # LLM prompt for plausible-but-wrong decoys
│   │   └── _translation_prompts.py  # MT prompt strategies
│   ├── services/         # API, auth, scoring, feedback, analytics, badges, BKT, progression
│   │   ├── api.py                # FastAPI application (auth, items, exercises, responses, feedback, badges, analytics, tutorial)
│   │   ├── auth.py               # Authentication service
│   │   ├── datastore.py          # JSON file CRUD; per-domain stores (students, items, badges, bkt, profiles, …)
│   │   ├── scoring.py            # IoU span matching, navigator confirm/dispute, HTER, comparison τ + human-vs-MT, skill_profile aggregation
│   │   ├── feedback.py           # Cognitive forcing feedback assembly (incl. navigator + comparison reveal blocks)
│   │   ├── badges.py             # Badge awarding + XP + per-class threshold overrides + visibility gating
│   │   ├── analytics.py          # update_student_profile, detect_blind_spots, compute_class_analytics, build_profile_from_store
│   │   ├── bkt.py                # Bayesian Knowledge Tracing + bkt_skill_profile aggregator
│   │   └── progression.py        # BKT-gated recommend_next_level + recommend_exercises (from blind spots)
│   └── interfaces/       # User interfaces
│       ├── student_app.py        # Gradio student training UI (login → consent → tutorial → main)
│       ├── teacher_app.py        # Streamlit teacher admin UI (10 pages + Build Comparison Items + L0 mode picker)
│       ├── annotation_app.py     # Gradio expert annotation UI (validation, animated timer)
│       ├── api_client.py         # HTTP client for Student ↔ Backend
│       └── components/
│           ├── span_selector.py  # Interactive text span selection (JS+HTML)
│           └── colors.py         # Colorblind-safe MQM tag palette
├── config/               # settings.yaml, mt_backends.yaml, badges.json
├── assets/badges/        # Badge icon images (40+ JPGs)
├── data/                 # All persistent data (JSON, JSONL)
│   ├── corpora/          # Parallel text with document IDs (Europarl, DGT-TM, EUbookshop, + uploaded TMX/TSV)
│   ├── codebook/         # Error taxonomy (8 entries + 3 drafts + 34 stubs) + tag schema (42 types) + Layer 2a/2b caches
│   ├── annotations/      # Expert annotation data (validation study) + _gemba/ cache for FP analysis
│   ├── badges/           # Per-student StudentBadges + XP records
│   ├── bkt/              # Per-student StudentBKT (per_skill mastery state)
│   ├── profiles/         # Persistent StudentProfile snapshots (analytics writes here)
│   └── ...               # items, students, exercises, sessions, etc.
├── scripts/              # Corpus ingestion, batch generation, codebook tooling
│   ├── ingest_corpus.py  # OPUS download with document structure preservation
│   ├── scaffold_codebook_entries.py  # Generates stubs for the 34 missing taxonomy entries
│   └── validate_codebook.py  # Per-entry checks + coverage report (--strict / --min-examples)
├── experiments/
│   ├── pipeline_validation/  # CIKM 2026 validation experiments (Track A/B/C + tagging ablation + FP analysis)
│   ├── ectel/                # EC-TEL 2026 experiments
│   ├── tom_validation/       # ToM hypothesis validation (R + Python)
│   └── wasserstein/          # MasteryGap dashboard visualizations
├── study/                # Standalone ECTEL 2026 pilot study app
├── specs/                # Specification documents
├── docs/                 # Architecture + implementation-audit documentation
└── tests/                # Test suite
```

---

## 2. Data Sources

### 2.1 Parallel Corpora (OPUS)

The platform ingests sentence-aligned parallel corpora from the OPUS project, covering EU/UN domains. Corpora are downloaded via `opustools` which preserves document structure from the OPUS XML format.

| Corpus | Domain | Segments | Documents | Register |
|--------|--------|:--------:|:---------:|----------|
| **Europarl v8** | Parliamentary proceedings | 9,982 | 8 | Semi-formal |
| **DGT-TM v2019** | EU legal translation memory | 9,919 | 169 | Formal |
| **EUbookshop v2** | EU publications & legislation | 10,000 | — | Formal |
| **UNPC v1.0** | UN institutional documents | — | — | Formal |

**Ingestion** is handled by two paths:

- **OPUS download** (`scripts/ingest_corpus.py`): uses `opustools.OpusRead` to download OPUS XML-aligned data and extract sentence pairs with document metadata.
- **Teacher upload** (`src/tompe/pipeline/corpus_ingest.py` — wired into the Streamlit *Upload Corpus* page): parses TMX (translation memory XML) and TSV (`source\ttarget`) uploads. Handles namespace stripping, language-tag normalisation (`EN-US` matches `en`), unpaired `<tu>` skipping, and per-line warning collection. Supports both replace and append modes.

Both paths write to `data/corpora/{corpus}/segments_en_fr.jsonl`, so downstream `segment_selector.load_corpus()` consumes them identically.

Each segment follows the schema:

```json
{
  "segment_id": "europarl-b0e004b9e126",
  "source_text": "Resumption of the session",
  "reference_translation": "Reprise de la session",
  "source_lang": "en",
  "target_lang": "fr",
  "corpus_origin": "europarl",
  "domain": "parliamentary",
  "register": "semi-formal",
  "document_id": "ep-00-01-17",
  "position_in_doc": 0
}
```

The `document_id` and `position_in_doc` fields enable multi-sentence context windows for L3 (recursive/discourse) error injection, where cross-sentence dependencies must be preserved.

### 2.2 Error Codebook

Located at `data/codebook/error_codebook_fr_en.json`, the codebook defines **8 fully-authored entries** plus **3 drafts pending bilingual review** (`error_codebook_fr_en.drafts.json`) and **34 stubs** for the remaining taxonomy entries (`error_codebook_fr_en.stubs.json`) — together covering all **42 error types** enumerated in `data/codebook/tag_schema.json`. The 42 types span **10 MQM primary categories** and **4 ToM levels**.

**Codebook tooling** (`scripts/`):

- `scaffold_codebook_entries.py` — generates the 34 stubs from `ERROR_TYPE_SPECS`; `--list-missing` is the running expert-time backlog.
- `validate_codebook.py` — per-entry checks (required fields, taxonomy membership, valid enums, ≥3 examples, well-formed inline XML) plus coverage report. `--strict` rejects `_stub: true` entries; `--min-examples` configurable.

Each codebook entry includes:

- Machine-readable identifiers (codebook ID, MQM hierarchy path)
- Severity range (minor / major / critical)
- Theory of Mind level assignment (1st-machine, 1st-author, 2nd-reader, recursive)
- Primary competency skill (S1-S7)
- Definition with boundary conditions ("what this is NOT")
- Few-shot examples with inline XML-tagged errors and multi-layer explanations

**Layer 2a/2b explanation cache** (`data/codebook/layer2a_explanations.json`, `layer2b_explanations.json`): committed templates keyed by `(primary_tag, error_type, mt_system)`. `explanation_generator` consults the cache before calling the LLM, so curated explanations are reused exactly and only novel (tag, type) pairs cost LLM calls.

**L3 (recursive) entries** (added for CIKM 2026 validation):

| ID | Error Type | Primary Tag | Description |
|----|-----------|-------------|-------------|
| R1 | anaphora_resolution | MISTRANSLATION | Cross-sentence pronoun resolution failure |
| R2 | discourse_connective | MISTRANSLATION | Logical relationship inversion between sentences |
| R3 | tense_sequence | GRAMMAR | Tense inconsistency across discourse |
| R4 | lexical_cohesion | TERMINOLOGY | Same term translated differently across sentences |
| R5 | information_packaging | STYLE | Theme-rheme disruption across sentences |

### 2.3 IATE Terminology

The European Inter-institutional Terminology Database (IATE) provides domain-specific glossaries. Ingested via `scripts/ingest_iate.py` with fields: term ID, source/target terms, domain, and reliability score. Used in glossary-aware MT prompt strategies and terminology-focused exercises.

### 2.4 WMT-MQM Reference Data

Located in `data/wmt-mqm/`, this contains human-annotated MQM error data from WMT shared tasks, used for validation and calibration of the error injection pipeline.

---

## 3. Data Preparation Pipeline

The item generation pipeline transforms raw parallel text into pedagogically-graded assessment items. There are **three production pathways**, all implemented as async Python modules in `src/tompe/pipeline/`:

1. **CONTROLLED** — inject specific codebook-defined errors into the human reference. Used for the core training items.
2. **AUTHENTIC** — detect errors in real MT output via GEMBA-MQM and map them onto the ToM-PE taxonomy. Used for ecological-validity items.
3. **COMPARISON** — assemble multiple MT outputs (and the human reference) side-by-side for L3 ranking + human-vs-MT discrimination.

The canonical entry point is `item_builder.build_item(...)` / `build_batch(...)`, which selects the pathway from the `pathway` argument and dispatches accordingly. `experiments/pipeline_validation/generate_batch.py` retains its own stratified-sampling loop for the camera-ready batch and will migrate to `build_batch` once that batch is locked.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Segment    │    │      MT      │    │    Error     │
│  Selection   │───▶│  Generation  │───▶│  Injection   │  ← CONTROLLED
│  (tom-aware) │    │ (G/D/LLM)    │    │  (2-step)    │
└──────────────┘    └──────────────┘    └──────────────┘
       │                    │                    │
       │                    ├────────────────┐   │
       │                    ▼                ▼   ▼
       │            ┌──────────────┐  ┌──────────────┐
       │            │  Authentic   │  │      QE      │
       │            │   Detector   │  │  Validation  │  ← (opt-in gate)
       │            │   (GEMBA)    │  │ GEMBA + IoU  │
       │            └──────────────┘  └──────────────┘
       │                    │                    │
       │                    └────────┬───────────┘
       ▼                             ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Comparison   │    │     Item     │    │ Explanation  │
│   Builder    │───▶│   Assembly   │◀───│  Generator   │
│ (multi-MT)   │    │ (item_builder│    │  (L1/2a/2b)  │
└──────────────┘    └──────────────┘    └──────────────┘
                            │                    │
                            ▼                    ▼
                    ┌─────────────────────────────────┐
                    │ false_annotation_generator      │ ← L0 decoys
                    │ (LLM / rule / manual / none)    │
                    └─────────────────────────────────┘
```

### 3.1 Segment Selection

**Module**: `src/tompe/pipeline/segment_selector.py`

Selects suitable segments from ingested corpora by applying:

1. **Token-length filtering**: Standard segments 10-50 tokens; L3 discourse segments 30-150 tokens.
2. **Exact deduplication**: Token-set identity check removes verbatim duplicates.
3. **Near-duplicate removal**: Jaccard similarity threshold (default 0.8) eliminates paraphrastic duplicates.
4. **Complexity scoring**: Each segment receives a [0, 1] complexity score based on sentence length and terminology density.
5. **Stratified sampling**: Final selection draws proportionally from each corpus to ensure domain diversity.

**L3 segment selection** (for discourse-level errors) uses two strategies:

- **Strategy 1** (long segments): Selects naturally multi-clause segments (30-150 tokens) with semicolons, colons, or multiple periods. Used for R2 (discourse connectives), R3 (tense sequence), R4 (lexical cohesion).
- **Strategy 2** (adjacent pairs): Uses `document_id` and `position_in_doc` to concatenate genuinely consecutive segments within the same document. Used for R1 (anaphora resolution), R5 (information packaging).

### 3.2 MT Generation

**Module**: `src/tompe/pipeline/mt_generator.py`

Translates selected segments through one or more MT systems to produce candidate outputs for error injection or authentic error detection.

**Supported MT systems** (configured in `config/mt_backends.yaml`):

| System | Type | Provider |
|--------|------|----------|
| Google Translate | Dedicated MT | REST API v2 |
| DeepL | Dedicated MT | REST API (free/pro) |
| GPT-4.1 | General LLM | OpenAI |
| Claude Sonnet | General LLM | Anthropic |
| Llama 3 (Ollama) | General LLM | Ollama (local/remote) |
| DeepSeek v3 | General LLM | Together AI |

**Prompt strategies** for LLM-based translation:
- `zero_shot` — Simple translation instruction
- `domain_context` — Domain and register awareness
- `few_shot` — In-context examples
- `glossary_aware` — Domain terminology provided
- `constraint_based` — Explicit register constraints

All translation calls are async with configurable concurrency (`max_concurrent=3`). Each output includes the MT system name, system type (dedicated vs. general LLM), and optional BLEU/COMET scores for quality reference.

### 3.3 Error Injection (Two-Step LLM Reasoning)

**Module**: `src/tompe/pipeline/error_injector.py`

This is the core pedagogical component. The platform uses a **controlled error injection** approach: starting from a clean reference translation, the system deliberately introduces specific, codebook-defined errors to create training items with known ground truth.

The injection follows a two-step architecture (per the Error Injection Annotation Spec v1.1):

**Step 1 — Planning** (unconstrained reasoning):
- The LLM receives the source text, reference translation, and target error specification from the codebook.
- It reasons freely about: which span is vulnerable, what MT misunderstanding would produce this error, and how to implement it plausibly.
- No format constraints are imposed to allow better chain-of-thought reasoning.
- Output: JSON with `target_span`, `planned_error`, `mt_rationale`.

**Step 2 — Execution** (structured output):
- The LLM receives the plan from Step 1 and produces the modified translation with inline XML tags.
- Strict preservation of surrounding text (character-for-character) is enforced.
- Output contains inline XML-tagged errors:

```xml
The committee voted on <MISTRANSLATION type="false_cognate" severity="major"
  tom="1st_machine" desc="assister à ≠ assist; means 'attend'">
  assisting at</MISTRANSLATION> the conference.
```

**Verification**: The system parses XML tags from the output, validates tag attributes against the codebook, checks span alignment, and retries up to 3 times on failure.

**Span realignment**: When multiple errors are injected sequentially, `_realign_spans()` runs after all injections to fix offset drift. It processes errors last-to-first using `find()` to relocate each span in the final text, and updates `injected_text` for any spans overwritten by later injections.

**Error profiles** specify target distributions: which MQM categories, severity mix, and ToM levels to include in a given item. The validation configuration uses 1 error per item for clean baseline comparisons.

### 3.4 QE Validation

**Module**: `src/tompe/pipeline/qe_validator.py`

Quality estimation validates that injected errors are genuine degradations and detectable by automated QE systems:

1. **GEMBA-MQM** (LLM-as-a-judge) performs MQM-categorized error detection on the injected text using structured JSON output. Detected errors are matched to injected ground truth via IoU-based span matching at `_GEMBA_IOU_THRESHOLD = 0.5` (unified with Track A2 across the codebase).
2. **COMET** (wmt22-comet-da, reference-based) scores both the clean reference and the error-injected text against the source. The injected version must show measurable quality degradation (score drop > 0). *xCOMET-XL is deferred until GPU access lands; see `experiments/pipeline_validation/config.py:XCOMET_MODEL`.*

**Opt-in GEMBA gating** (`inject_errors_reference_based(verify_gemba=True, gemba_min_detection_rate=0.5)`) runs a post-injection GEMBA pass and raises if detection falls below the configured floor — useful when a batch needs the injected error to be reliably "visible" to QE.

### 3.4b C1–C4 Tag Format Ablation

**Module**: `src/tompe/pipeline/tag_formats.py`

The injection prompt + verification pipeline is parameterised by `TagFormat` (C1 plain spans → C4 full structured `<TAG type="…" severity="…" tom="…" desc="…">…</TAG>`). `render_tag()`, `reformat_codebook_xml()`, and `parse_tags()` round-trip cleanly across all four formats, letting the ablation runner (`experiments/pipeline_validation/ablation_tagging.py`) sweep the same items through every format and produce comparable structural / GEMBA-detection / category-fidelity / text-preservation metrics. Layer 1 results feed Table 4 of the paper.

### 3.5 Explanation Generation (Three Layers)

**Module**: `src/tompe/pipeline/explanation_generator.py`

Each injected error receives up to three layers of explanation. Layer 1 is always LLM-generated (it depends on the specific span); Layer 2a/2b consult an on-disk **template cache** (`data/codebook/layer2{a,b}_explanations.json`) keyed by `(primary_tag, error_type, mt_system)` and only call the LLM on cache misses.

**Layer 1 — Contrastive Explanation** (per error instance):
- **MT interpretation**: "The system treated *assister à* as cognate of English *assist*..."
- **Actual meaning**: "In this context, *assister à* means *to attend*..."
- **Reader impact**: "A reader would understand that someone was helping..."
- **Correction rationale**: "Replace *assisting at* with *attending*..."

**Layer 2a — System Behavior** (per error type, accessible language):
- Why MT systems make this specific type of error
- Architectural causes (e.g., shared BPE vocabularies, attention patterns)
- When to expect similar errors in practice

**Layer 2b — Technical NLP** (optional, progressive disclosure):
- Detailed NLP-level explanation with key concepts and academic references

### 3.5b Authentic Error Detection (real-MT pathway)

**Module**: `src/tompe/pipeline/authentic_detector.py`

`detect_authentic_errors(segment, mt_output, llm_config)` runs GEMBA-MQM on a real MT output and maps each detection onto the ToM-PE taxonomy: it picks the matching `PrimaryTag`, infers an `error_type` from the GEMBA subcategory, derives `tom_level` and `primary_skill` from `mqm_taxonomy`, and synthesises a Layer 1 contrastive explanation from the GEMBA fields. Layer 2a comes from the cache (Layer 2b is left None — it's progressive disclosure only).

xCOMET cross-validation is deferred (GPU); v1 is GEMBA-only. The result is an `AuthenticErrorDetection` carrying `detected_errors`, `detection_method="gemba_mqm"`, and `confidence_score`.

### 3.5c L0 False-Annotation Generator

**Module**: `src/tompe/pipeline/false_annotation_generator.py`

L0 (Navigator) items present *pre-annotated* errors that the student must Confirm or Dispute (UI §3.3.4). To make the Dispute action meaningful, the teacher seeds each item with plausible-but-incorrect decoys via four mode choices:

| Mode | Source | Notes |
|------|--------|-------|
| `llm` | LLM prompted to invent plausible decoys | Highest pedagogical quality; needs an `injection_llm` config. |
| `rule` | Random word-boundary spans + weighted-random MQM tag | Cheap, deterministic with `seed=`. Falls back here automatically if `llm` mode loses its LLM client. |
| `manual` | Teacher authors decoys via the review queue | No auto-generation. |
| `none` | Disabled | Item gets only real errors. |

Decoys are stored on `Exercise.false_annotations[item_id]` (not on the item itself) so the same item can serve different decoys in different exercises. The student app shuffles real + decoy annotations deterministically by `item_id` so position can't leak the answer.

### 3.5d L3 Comparison Item Builder

**Module**: `src/tompe/pipeline/comparison_builder.py`

`build_comparison_item(segment, mt_outputs, *, comparison_type=COMPARATIVE_RANKING, include_human=True)` assembles a comparison-mode `AssessmentItem`:

- The caller supplies machine MT outputs (typically 2–3 via `translate_segment`); the builder appends the human reference as an `MTOutput` with `is_human_reference=True`, `system_type="human"`.
- `comparison_outputs` is populated; `presented_text=""` (the student reads from the cards, not the legacy translation panel); `errors=[]` (comparison-mode scoring uses Kendall's τ + human-vs-MT, not span overlap).
- `derive_expert_ranking(outputs)` sorts by `MTOutput.quality_score` descending (stable on input order for unscored systems; logs a warning so callers know τ is heuristic).

Skill A (independent per-system evaluation) is schema-supported but not yet wired in the UI — it would need per-MTOutput error manifests.

### 3.6 Item Assembly (canonical orchestrator)

**Module**: `src/tompe/pipeline/item_builder.py`

`build_item(segment, llm_config, *, pathway, error_profile=None, mt_output=None, codebook=…, tag_format=…, scaffolding_level=…, …)` is the canonical assembly path. It validates the pathway invariants (`CONTROLLED` requires `error_profile`; `AUTHENTIC` requires `mt_output`), runs the appropriate injection/detection stage, generates Layer 1/2a explanations, computes `clean_spans` from the error spans, and assembles an `AssessmentItem`:

```python
AssessmentItem:
  item_id: str
  segment_id: str
  source_text: str                    # Original source (FR or EN)
  presented_text: str                 # MT with injected errors (what students see)
  reference_translation: str          # Clean reference (hidden until feedback)
  mt_system: str                      # Which MT system produced the base ("comparison" sentinel for L3 comparison items)
  pathway: ItemPathway                # CONTROLLED | AUTHENTIC
  errors: list[InjectedError|DetectedError]   # Ground truth (empty for comparison items)
  clean_spans: list[tuple[int, int]]  # Spans with NO errors (for L3 expert items)
  annotations: list[ErrorAnnotation]  # Per-error scaffolding metadata for L0/L1
  comparison_outputs: list[MTOutput] | None  # L3 comparison only
  comparison_type: ComparisonType | None     # L3 comparison only
  difficulty_level: int               # 1–5 scale
  domain: str
  item_status: "draft" | "reviewed" | "published" | "retired"
  metadata: ItemMetadata              # ToM profile, MQM profile, scaffolding level, pathway
```

`build_batch(segments, …, on_failure="skip")` iterates, capturing per-item failures so a single bad segment can't poison the run. `ItemMetadata.tom_profile` and `mqm_profile` are auto-populated from the errors list via `_PRIMARY_TO_MQM` mapping.

Items are stored as individual JSON files in `data/items/` and progress through a status lifecycle: **draft** (auto-generated) → **reviewed** (teacher-approved) → **published** (available for exercises) → **retired** (removed from active use).

---

## 4. Teacher Workflow

The teacher interface is a **Streamlit** application (`src/tompe/interfaces/teacher_app.py`) that runs locally and accesses services directly (no API layer for the teacher path). It provides ten functional pages grouped under three sidebar sections (Corpus & Generation, Item Management, Class & Analytics, Settings).

### 4.1 Corpus Management

**Browse Corpus**: Filter segments by corpus source, domain, translation direction, register, and token range. Search within source/reference text. Preview segments with computed complexity scores. Selection is persisted across the page in `st.session_state.selected_segment_ids` so the next page can act on it.

**Upload Corpus**: Add new parallel corpora via TMX or TSV upload (no command-line step needed):
- **TMX**: parsed by `corpus_ingest.parse_tmx` (namespace-stripped XML, case-insensitive language matching, unpaired `<tu>` units silently skipped).
- **TSV** (`source\ttarget`): parsed by `corpus_ingest.parse_tsv` with per-line warnings for malformed rows (wrong column count, empty cells); warnings are surfaced in an expander without aborting the ingest.
- **Append vs. replace** toggle: by default a new upload replaces the corpus's `segments_en_fr.jsonl`; with append checked, new segments are concatenated.
- After upload, the success message reminds the teacher to register the new corpus in `experiments/pipeline_validation/config.py:CORPORA` if it should participate in batch runs.

### 4.2 Item Generation

**Generate Translations & Inject Errors** drives the controlled pipeline end-to-end:

1. Select MT systems (multi-select, with per-system green/yellow/red status flags showing API-key presence).
2. Pick a translation prompt preset (EU Formal / General / Legal) or write a custom prompt for LLM-based MT.
3. Configure error injection: which MQM categories to allow, severity distribution (minor / major / critical counts).
4. Click **Generate Translations & Inject Errors** → progress bar + per-segment streaming log. Output: draft items pre-populated with Layer 1/2a explanations.

**L3 Comparison Items** is a separate section on the same page: runs all selected MT systems on each segment and assembles one `AssessmentItem` per segment via `comparison_builder.build_comparison_item`. Items are saved as **published** so they land in the Exercise Builder immediately. Requires ≥2 MT systems selected.

### 4.3 Item Review

**Review Queue**: Two-column editor for draft items:
- Left: visual span selection over the presented text, with each existing error highlighted in its MQM color.
- Right: per-error cards with editable fields (primary tag, error type, severity, ToM level, primary skill, Layer 1 / Layer 2a / Layer 2b explanations, difficulty rating 1–5).
- Bottom: Approve (→ reviewed/published) / Reject / Save-Reviewed actions.

**Published Items**: Browse curated items filtered by domain, difficulty, and target skill. Per-item analytics show how students have performed on each item.

### 4.4 Exercise Builder

Teachers compose exercises from published items with full control over pedagogical parameters:

| Parameter | Options | Purpose |
|-----------|---------|---------|
| Mode | Evaluation / Post-editing / Both | What students are asked to do |
| Scaffolding level | Navigator / Guided / Independent / Expert | How much support is provided |
| Item ordering | Manual / Difficulty / Random | Sequence strategy |
| Clean segment ratio | 0.0–1.0 | Proportion of error-free items (tests false-positive bias at L3) |
| False annotation ratio (L0) | 0.0–0.5 | Proportion of items that receive decoys |
| False annotation source (L0) | `llm` / `rule` / `manual` / `none` | Where decoys come from. `llm` requires `injection_llm` in `mt_backends.yaml`; falls back to `rule` on missing config |
| False annotation count (L0) | 0–5 / item | Target number of decoys per item |
| Justification type | per_error_short / per_error_structured / global_free_text / none | How students explain their reasoning |

On **Create Exercise**, if the level is `navigator` and the false-annotation mode is `llm` or `rule`, `_populate_false_annotations()` runs the generator across the selected items and writes results to `Exercise.false_annotations[item_id]`. Exercises are then assigned to entire classes or individual students.

**AI-suggested items from a student's blind spots** (top of the page, collapsible): pick any student → click **Compute suggestions** → the system runs `build_profile_from_store(student)` then `progression.recommend_exercises(profile, items, max_recommendations=10)`. The recommended item IDs are listed and pre-fill the item multiselect below, so the teacher can accept-and-tweak the AI-targeted exercise rather than re-pick from scratch.

### 4.5 Class & Student Management

- Create and edit class groups; per-class `badges_visible` toggle (hides badge UI for that class but tracking continues server-side) and `badge_threshold_overrides` (per-category `[bronze, silver, gold]` overrides applied at award time).
- Bulk import students via CSV.
- Set per-student `current_level` and `allowed_levels`.
- View enrollment and active consent status.

### 4.6 Analytics Dashboard

Four tabs:

- **Class Overview** — average detection rates, F1, HTER across exercises; participation counts.
- **Individual Student** — for the selected student:
  - Performance time series (F1 over completed items).
  - **Wasserstein skill profile** (when ≥3 skills have observations): current vs. target with optimal-transport arrows + a `MasteryGap (W₁)` metric and an LLM-generated interpretation.
  - Per-MQM and per-ToM detection rate bars (fallback when Wasserstein data is thin).
  - **Skill Mastery (BKT) table** — per-skill p(mastery), observation count, Mastered / Practising / Untouched label (Sprint #9).
  - **Blind Spots table** — every `(MQM × ToM)` cell where this student's joint detection rate is <50% across ≥3 sessions, with up to 3 example item IDs per row (Sprint #9).
  - **Level Progression panel** — calls `progression.recommend_next_level(profile)`; if held back, lists the *blocking prerequisite skills* with their `(p, n)` so the teacher knows exactly what to target. The "Approve promotion" button updates `allowed_levels` only when the BKT thresholds pass.
- **Blind Spot Heatmap** — class-wide MQM × ToM grid with detection rates and per-cell student counts.
- **Badges** — class-wide badge distribution heatmap, most/least earned summary.

### 4.7 Study Management (translation-student studies)

Setup / Monitor / Export tabs for the in-class study workflow (separate from the `study/study_manager.py` broader-public app — by design, different audiences).

### 4.8 Settings

- **API Credentials**: per-provider expander (Google, DeepL, OpenAI, Anthropic, Together). Shows env-var status and exposes a **Test Connection** button (Sprint #6 B10): MT providers run a tiny `"Hello."` translation via `translate_segment`; LLM providers hit `LLMClient.complete_text` with a 1-token reply. Success/failure is reported inline.
- **MT Systems**: enable/disable each backend.
- **System Configuration**: ports, paths, error-injection defaults.
- **Launch Controls**: subprocess buttons to start/stop the FastAPI backend, student UI, and study app.

---

## 5. Student Workflow

The student interface is a **Gradio** application (`src/tompe/interfaces/student_app.py`) that communicates with the FastAPI backend over HTTP. The login flow routes through three gates in order — **consent → tutorial → main** — each shown only when needed.

### 5.1 Login → Consent → Tutorial → Main

1. **Login** (bcrypt + bearer token; 7-day expiry).
2. **Consent** (only if `consent_pending=True`): two-tier research consent.
   - **Tier 1**: Allow interaction data (responses, time, scaffolding level) for research.
   - **Tier 2**: Allow anonymized text excerpts (student justifications) in publications.
   - Refusal does not affect grades or platform access. Consent can be withdrawn at any time.
3. **First-session tutorial overlay** (only if `tutorial_pending=True` — Sprint #10, UI §3.3.5): a 60-second 3-step walkthrough explaining (1) drag to select a span, (2) pick a category + severity, (3) write a justification. *Skip tutorial* and *Done* both fire `POST /api/tutorial/complete`, which flips `StudentAccount.tutorial_completed=True` server-side so the overlay never reappears across devices.
4. **Main view** — Exercises + My Progress tabs.

### 5.2 Exercise Selection

The student sees their assigned exercises with metadata: exercise name, mode, number of items, and completion status. They select an exercise to begin.

### 5.3 Phase 1 — Error Identification (per-level views)

The student sees the **presented text** (MT output with injected errors) alongside the **source text**. The Annotate tab contains three sibling Columns; exactly one is shown per item depending on the level + the item itself:

| Level | View | What the student does |
|-------|------|----------------------|
| **L0 (Navigator)** | `l0_annotate_view` (Sprint #4) | Up to 10 pre-allocated Confirm/Dispute cards. Each card shows the highlighted span, MQM label, severity. The student picks **Confirm (real error)** or **Dispute (false alarm)** and writes a short reasoning. The real + decoy annotations are shuffled deterministically by item_id so position can't leak the answer. Submit jumps straight to Feedback (skipping Justify). |
| **L1/L2/L3** | `std_annotate_view` | Drag to select a span (via `span_selector.py`), pick a colored pill (10 MQM categories), pick a severity, click **Add Error**. Multiple spans can be added; each becomes a chip with a × remove button. |
| **L3 Comparison** | `cmp_annotate_view` (Sprint #7) | Up to 4 cards masked as **System A/B/C/D**, each showing one MT output's text. Per card: a rank radio (1–4), a triage radio (`pe_light` / `pe_full` / `retranslate`), and a rationale textbox. Below: "Which (if any) was produced by a human translator?" radio + optional rationale. Submit jumps to Feedback with a full reveal panel. |

**Post-editing mode** (any level except L0): a separate `pe_panel` shows the translation in an editable textbox; `_build_pe_diff_html` (Sprint #6 B8) renders a **live character-level diff** below the textbox as the student types — deletions in red strikethrough, insertions in green, plus a collapsible per-edit change list (UI §3.4).

### 5.4 Phase 2 — Justification (Cognitive Forcing)

L1–L3 (non-comparison) flow: before any feedback, the student must justify each detected error. This is the core pedagogical mechanism — it forces metacognitive reflection.

Four justification modes are configurable per exercise:

- **`per_error_short`** — one short textbox per detected error, with an adaptive prompt that depends on the error's primary tag.
- **`per_error_structured`** — three structured fields per error (MT misunderstanding / author intent / reader impact).
- **`global_free_text`** — one free-text box for the whole item.
- **`none`** — skip Justify entirely and submit directly to Feedback.

L0 verifications and L3 comparison submissions both bypass Justify because the reasoning is captured inline (in each card's textbox).

The justification is submitted and **locked** before Phase 3 reveals explanations.

### 5.5 Phase 3 — Feedback Display

After justification submission, the system reveals:

1. **Scoring summary**: True positives, false positives, missed errors, precision, recall, F1.
2. **Per-error comparison** (L1–L3):
   - Student's classification vs. ground truth (MQM tag, severity match)
   - Student's own justification (displayed first for metacognitive reflection)
   - **Layer 1**: Contrastive explanation
   - **Layer 2a**: System behavior explanation (collapsible "How It Works")
   - **Layer 2b** (optional): Technical NLP deep dive (collapsible "Under the Hood")
3. **L0-specific feedback**: real errors that were Confirmed render as "Found"; real errors that were Disputed render as "Missed". The summary stats split into `correct_confirms` / `correct_disputes` / `incorrect_confirms` / `incorrect_disputes` (so Trap Detector + analytics can read them).
4. **L3 Comparison reveal panel** (`_build_comparison_reveal_html`):
   - Per-system reveal — real `mt_system` ids with a HUMAN badge + quality_score for the reference.
   - Student ranking vs. expert ranking + Kendall's τ value (color-coded green/red).
   - Human-vs-MT verdict (correct ✓ / incorrect ✗).
5. **Missed errors**: Errors the student did not detect, with full explanations.
6. **False positives**: Spans the student flagged that are not actual errors.
7. **Badge notification toast**: any newly earned badges + XP delta from this submission (visibility honors `class.badges_visible`).

### 5.6 My Progress dashboard

- **Summary cards**: total exercises completed, average detection rate, current level, total XP.
- **Badge Collection** (when `class.badges_visible=True`): three sections (progression / specialisation / achievements) with tooltips.
- **Skill Radar** (Sprint #5): heptagonal SVG showing per-skill mastery probability for S1–S7. The data source is `aggregate_skill_profile(scores)` which pools `detection_by_skill` across all the student's responses. Detection-rate-based pooling is a deliberately simple stand-in for BKT — the consumer doesn't change when BKT replaces it.
- **Recent exercises**: last 5 exercise scores.

### 5.6 Scaffolding Levels & Progression

Students progress through five stages as they demonstrate mastery:

| Stage | Name | Active Skills | Level | Modes | Requirements to Advance |
|-------|------|---------------|-------|-------|------------------------|
| 1 | Orientation | S1, S2 | Navigator (L0) | Evaluation only, critical severity, EN→FR | S1 ≥ 90%, S2 ≥ 80% (3 sessions) |
| 2 | Guided Detection | S3, S4 | Guided (L1) | Evaluation, major severity added | S3 ≥ 70%, S4 ≥ 65% (3 sessions) |
| 3 | Independent | S3–S6 | Independent (L2) | Eval + PE, mixed severity | S5 ≥ 70%, S6 ≥ 60% (3 sessions) |
| 4 | Dual Mode | S1–S6 | Independent (L2) | Eval + PE, both directions | All S1–S6 at threshold (3 sessions) |
| 5 | Expert | S1–S7 | Expert (L3) | + Comparative ranking + PE triage | S7 ≥ 55%, FP rate < 20% |

**Seven competency skills** (S1 easiest → S7 hardest):

| Skill | Focus | ToM Level | Example Errors |
|-------|-------|-----------|---------------|
| S1 | Surface errors | 1st (machine) | Spelling, punctuation, diacritics |
| S2 | Grammar errors | 1st (machine) | Agreement, tense, word order |
| S3 | Meaning transfer | 1st (machine) | False cognates, word sense, negation |
| S4 | Completeness | 1st (author) | Omissions, additions, hallucinations |
| S5 | Terminology | 2nd (reader) | Wrong/inconsistent/missing terms |
| S6 | Pragmatics & style | 2nd (reader) | Register, idiomaticity, locale conventions |
| S7 | Discourse coherence | Recursive | Cross-sentence consistency, anaphora, lexical cohesion |

---

## 6. Annotation Interface

**Module**: `src/tompe/interfaces/annotation_app.py`
**Port**: 7861

A standalone Gradio application for expert MQM annotation, used in the CIKM 2026 pipeline validation study (Track C). The annotation interface is a stripped-down variant of the student interface, configured for blind expert annotation without pedagogical scaffolding.

### 6.1 Phase A — Error Annotation

The annotator works through items sequentially, marking error spans and classifying them:

- **Source text** (English) displayed alongside **Translation** (French)
- Interactive span selector (reuses `span_selector.py` component)
- All **10 MQM category** pill buttons (including SPELLING and PUNCTUATION)
- Severity radio (minor / major / critical)
- Per-item **confidence rating** (Low / Medium / High)
- Optional **free-text notes**
- **"No Errors Found"** button for clean segment judgment
- Per-item **animated elapsed timer** (Sprint #2 B3): a `<div class="timer-display">` ticking every 500ms via `ANNOTATION_TIMER_JS` injected through `gr.Blocks.load(js=…)`; resets on per-item Submit / "No Errors" buttons
- Progress indicator ("Item X / Y")
- No feedback, no scaffolding, no ground truth revealed

**Item set composition** (84 items + 3 practice):
- Full pipeline items: 6 per ToM level (24 total)
- Baseline B0/B1/B2 items: 6 per condition (18 total)
- Authentic MT errors: 12 (if available)
- Clean segments: 12
- Practice items: 3 (excluded from analysis)

Items are presented in a randomized order; the annotator is blind to item source.

### 6.2 Phase B — Explanation Quality Review

After completing Phase A, the annotator reviews 24 generated explanations (6 per ToM level) and rates them on three dimensions:

- **Factual accuracy**: Incorrect / Partially correct / Correct
- **Pedagogical clarity**: Unclear / Somewhat clear / Clear
- **Completeness**: Incomplete / Adequate / Thorough
- Optional free-text comment

The annotator sees the ground truth error and the generated Layer 1 (contrastive) and Layer 2a (system behavior) explanations.

### 6.3 Data Model

```python
ExpertAnnotation:       # Phase A: per-item annotation record
  annotation_id, annotator_id, item_id, item_source, tom_level
  timestamp_start, timestamp_end, duration_seconds
  errors: list[AnnotatedError]    # span_start, span_end, category, severity
  no_errors_found: bool
  confidence: "low" | "medium" | "high"
  notes: str | None

ExplanationRating:      # Phase B: per-explanation quality rating
  rating_id, annotator_id, item_id, error_index, tom_level
  factual_accuracy, pedagogical_clarity, completeness
  comment: str | None
  timestamp_start, timestamp_end, duration_seconds
```

Annotations are saved as JSON in `data/annotations/{annotator_id}/`.

### 6.4 Three-Way Agreement Analysis

The annotation data supports three-way agreement analysis (Pipeline ground truth × Human annotator × GEMBA-MQM), computed by `experiments/pipeline_validation/track_c/three_way_agreement.py`:

- IoU-based span alignment across all three sources
- Pairwise detection rates and Cohen's kappa
- Agreement breakdown by ToM level (Cochran-Armitage trend test)
- Three-way overlap statistics

### 6.5 False-Positive Analysis (Sprint #3)

**Module**: `experiments/pipeline_validation/track_c/false_positive_analysis.py`

Classifies every span the human flagged as an error but the pipeline did NOT inject into one of three buckets:

- **`true_positive`** — overlaps an injected error (the pipeline missed it; rare).
- **`real_mt_error`** — overlaps a GEMBA-flagged span (a real MT error the controlled pipeline didn't generate).
- **`genuine_false_alarm`** — overlaps neither (the annotator was wrong).

Uses IoU against the injected manifest and a per-item GEMBA cache at `data/annotations/_gemba/{item_id}.json` (the LLM only runs on a cache miss). Emits per-annotator + by-condition + by-MQM-category breakdowns plus pairwise Cohen's κ on the real-MT-vs-false-alarm call. Closes annotation §6.6.

---

## 7. Gamification & Badges

The platform includes a gamification layer to sustain student motivation through badges and experience points (XP).

### 7.1 Badge System

**Schema**: `src/tompe/schemas/badges.py`
**Service**: `src/tompe/services/badges.py`
**Configuration**: `config/badges.json`
**Assets**: `assets/badges/` (40+ icon images)

Badges are organized into three categories:

| Category | Count | Description |
|----------|-------|-------------|
| **Progression** | 4 tiers | Awarded when students complete scaffolding levels L0–L3 (Navigator → Scout → Analyst → Expert) |
| **Specialisation** | 10 × 3 tiers = 30 | Track detection mastery per MQM error category with bronze / silver / gold tiers |
| **Behaviour** | 3 unique | Reward strategic thinking patterns |

**Specialisation badge tiers** require cumulative correct detections per category:

| Tier   | Detections | Category Matches | Severity Matches |
|--------|------------|------------------|------------------|
| Bronze | 10         | 8                | 5                |
| Silver | 25         | 20               | 15               |
| Gold   | 50         | 40               | 30               |

**Behaviour badges** (all three live and tested):

- **Clean Sheet** (Sprint #1 A2): perfect score on a single item (every real error detected, correct category, zero FP). Repeatable; counter tracked on `StudentBadges.clean_sheet_count`.
- **Trap Detector** (Sprint #4): correctly disputes ≥10 false annotations at L0. Counter (`StudentBadges.correct_disputes`) is fed from `scoring.correct_disputes` via `item_results[0]["correct_disputes"]` in the feedback flow.
- **False Positive Discipline**: completes an L3 Expert exercise (≥5 items) with zero false positives.

### 7.2 Per-class Configuration

Sprint #1 A3 plumbed two per-class knobs end-to-end through `process_badges_and_xp`, `get_badge_summary`, and the API:

- **`ClassGroup.badges_visible: bool`** — when False, the student app hides the Badge Collection panel and the XP card, and `api_get_feedback` masks the `badges` field in the response. Tracking continues internally per spec §8.3, so flipping the toggle back on shows badges earned during the off period.
- **`ClassGroup.badge_threshold_overrides: dict[str, list[int]]`** — per-category `[bronze, silver, gold]` count overrides. Falls back to global `CATEGORY_THRESHOLDS` for any category not overridden.

### 7.3 XP System

Each student action earns XP with base values:

| Action | Base XP |
|--------|---------|
| Error detection | +10 |
| Category match | +5 |
| Severity match | +3 |
| False positive | −5 |

XP is scaled by two multipliers:

- **ToM level multiplier**: 1.0× (1st-machine) → 2.0× (recursive) — rewards detecting harder errors
- **Scaffolding level multiplier**: 0.5× (Navigator L0) → 2.0× (Expert L3) — rewards independence

`compute_item_xp(...)` ceilings each component to integer XP and records the breakdown in `StudentBadges.xp_history`.

### 7.4 UI Integration

- **Student app**: Badge collection display with visual hierarchy, progress bars toward next tiers, and XP history. Visibility honors `class.badges_visible`.
- **Teacher app**: Badge analytics tab with class-wide heatmap showing badge distribution across students.

---

## 8. Backend Services

### 8.1 FastAPI Application

**Module**: `src/tompe/services/api.py`
**Default port**: 8000, CORS enabled for Gradio cross-origin requests.

#### Endpoint Groups

| Group | Path Prefix | Purpose |
|-------|------------|---------|
| Authentication | `/api/auth/` | Login, logout, token management. `LoginResponse` includes `consent_pending` + `tutorial_pending` for the student-app routing logic. |
| Consent | `/api/consent/` | Research consent text, status, submission, withdrawal |
| Tutorial | `/api/tutorial/` | `POST /api/tutorial/complete` — flips `StudentAccount.tutorial_completed` (idempotent; called by both Skip and Done in the overlay) |
| Assignments | `/api/assignments/` | Student exercise assignments |
| Exercises | `/api/exercises/` | Exercise CRUD, including comparison-mode + L0 false-annotation config fields |
| Items | `/api/items/` | Assessment item retrieval and querying |
| Responses | `/api/responses/` | Annotation submission across **all four modes**: `evaluation` (`identified_errors`), `postediting` (`edited_text`), `navigator` (`verification_responses`), `comparison` (`comparison_type` + `per_system_evaluations` + `system_rankings` + `pe_worthiness` + `human_pick`) |
| Feedback | `/api/feedback/` | Dispatches to the right `score_*` function per response mode; emits the cognitive-forcing feedback payload + comparison reveal block when applicable |
| Classes | `/api/classes/` | Class management (teacher/admin) |
| Students | `/api/students/` | Student CRUD, bulk import, level management |
| Analytics | `/api/analytics/` | Per-student and per-class performance metrics |
| Progress | `/api/progress/` | Per-student progress + `skill_profile` (Sprint #5) for the radar |
| Badges | `/api/badges/` | Badge collection, XP history, progress summaries (visibility-gated per class) |

### 8.2 Authentication

**Module**: `src/tompe/services/auth.py`

1. Student submits credentials via Gradio → `POST /api/auth/login`
2. Backend verifies bcrypt password hash
3. Generates `secrets.token_urlsafe()` bearer token
4. Token stored in `data/sessions/tokens/{token}.json` with 7-day expiry
5. Subsequent requests include `Authorization: Bearer {token}` header

Teacher access (Streamlit) runs on the same machine with direct service imports — no authentication layer in v1.

### 8.3 Data Store

**Module**: `src/tompe/services/datastore.py`

A generic `JsonStore` class provides CRUD operations over JSON files with Pydantic validation. Per-domain stores live under `data/`:

| Store | Path | Schema |
|-------|------|--------|
| `students_store` | `data/students/{id}.json` | `StudentAccount` (incl. `consent`, `tutorial_completed`) |
| `classes_store` | `data/classes/{id}.json` | `ClassGroup` (incl. `badges_visible`, `badge_threshold_overrides`) |
| `items_store` | `data/items/{id}.json` | `AssessmentItem` |
| `exercises_store` | `data/exercises/{id}.json` | `Exercise` (incl. `false_annotation_mode/count`, `false_annotations`) |
| `assignments_store` | `data/sessions/assignments/{id}.json` | `ExerciseAssignment` |
| `responses_store` | `data/sessions/responses/{id}.json` | `StudentResponse` |
| `tokens_store` | `data/sessions/tokens/{token}.json` | `SessionToken` |
| `feedback_store` | `data/sessions/feedback/{id}.json` | `ScoringResult` |
| `badges_store` | `data/badges/{student_id}.json` | `StudentBadges` (per-category counts + XP history + earned badges) |
| `bkt_store` | `data/bkt/{student_id}.json` | `StudentBKT` (per-skill BKT state) |
| `profiles_store` | `data/profiles/{student_id}.json` | `StudentProfile` snapshots (written by `build_profile_from_store`) |

### 8.4 LLM Client

**Module**: `src/tompe/pipeline/llm_client.py`

Unified async client supporting four providers:

| Provider | Endpoint | Models |
|----------|----------|--------|
| OpenAI | `/v1/chat/completions` | gpt-4.1, o-series reasoning models |
| Anthropic | Native Messages API | claude-sonnet-4-6 |
| Ollama | `/api/chat` or OpenAI-compatible | llama3, mistral, etc. |
| Together AI | OpenAI-compatible | deepseek-v3, open-source models |

Key methods:
- `complete_text(system, user, temperature)` — Plain text completion
- `complete_json(system, user, schema, temperature)` — Structured JSON output (OpenAI: json_schema mode)
- `stream_text(system, user)` — Streaming async iterator

Factory function `make_client_from_config(config)` reads API keys from environment variables.

---

## 9. Scoring, Feedback, Analytics & Progression

### 9.1 Scoring (mode-aware)

**Module**: `src/tompe/services/scoring.py`

`api_get_feedback` dispatches to the right scorer based on `response.mode`:

| Mode | Scorer | Output |
|------|--------|--------|
| `evaluation` | `score_evaluation_response` | IoU-based span matching (0.3 student-grading threshold, lenient with text-overlap fallback); precision/recall/F1; per-MQM, per-ToM, per-skill breakdowns |
| `postediting` | `score_postediting_response` | Character-level Levenshtein → HTER, plus an `unnecessary_edits` count for changes outside ground-truth spans |
| `navigator` | `score_navigator_response` | Splits TP/FP/FN into `correct_confirms` / `correct_disputes` / `incorrect_confirms` / `incorrect_disputes` — fuels both feedback rendering and the Trap Detector behaviour badge |
| `comparison` | `score_comparison_response` | Kendall's τ between student `system_rankings` and the expert ranking derived from `MTOutput.quality_score`; plus `human_pick_correct` boolean. Folds both into an F1-style overall score so badges + analytics keep working |

**IoU thresholds intentionally differ by domain**: `_GEMBA_IOU_THRESHOLD = 0.5` in `qe_validator` (strict, for pipeline-validation rigor) vs `iou_threshold = 0.3` in `score_evaluation_response` (lenient, accommodates imprecise student selections).

**Cross-response aggregator**: `aggregate_skill_profile(scores)` (Sprint #5) pools `detection_by_skill` across a student's responses into a `{S1..S7: p}` dict for the radar. Detection-rate-based today; will swap to BKT probabilities transparently when callers want.

### 9.2 Feedback (Cognitive Forcing Protocol)

**Module**: `src/tompe/services/feedback.py`

`prepare_feedback(response, item, scoring)` builds a mode-aware payload:

- **Summary** — TP/FP/FN, precision/recall/F1, score_pct (rounded recall by default; overridden to F1 for comparison mode).
- **Per-error cards** — student classification, student justification (displayed first per the cognitive forcing protocol), then Layer 1 contrastive, Layer 2a "How It Works" (collapsible), Layer 2b "Under the Hood" (collapsible, optional).
- **Navigator mode** — recognises confirmed real errors as Found / disputed real errors as Missed; pulls the student's reasoning from `VerificationResponse.suggested_correction` rather than the (empty) `justifications` list.
- **Comparison mode** — adds a `comparison` block (system_reveal, student_ranking, expert_ranking, kendall_tau, human_pick, human_pick_correct, pe_worthiness) that the student app renders via `_build_comparison_reveal_html`.

### 9.3 Analytics & Blind Spot Detection

**Module**: `src/tompe/services/analytics.py` (Sprint #8)

Three previously-stub functions are now wired end-to-end:

- **`update_student_profile(student_id, responses, scores, items)`** — recomputes `StudentProfile` (sessions_completed, mqm_performance time series, tom_performance time series, blind_spots, false_positive_rate_history) and persists to `data/profiles/`.
- **`detect_blind_spots(scores, items)`** — surfaces every `(MQM × ToM)` cell where the student's joint detection rate is < 0.5 over ≥ 3 sessions; populates `example_item_ids` (up to 3 per cell) so the teacher dashboard can link to specific items.
- **`compute_class_analytics(class_id, students, responses, scores, items)`** — class-level rollups consumed by the Analytics → Class Overview tab.
- **`build_profile_from_store(student_id, display_name)`** — convenience wrapper that loads from the existing stores; called by the teacher individual-student view + the Exercise Builder's "AI-suggested" expander.

### 9.4 BKT (Bayesian Knowledge Tracing)

**Module**: `src/tompe/services/bkt.py` (Sprint #8)

Per-skill `(p_init, p_transit, p_slip, p_guess)` BKT update applied after each scored response. The model treats each `(skill, observation)` pair from `scoring.detection_by_skill` as one BKT step. Output:

- **`StudentBKT.per_skill[skill_id]`** — `(p_mastery, n_observations, last_updated)` triple per S1–S7.
- **`bkt_skill_profile(student_id) -> dict[str, float]`** — `{S1..S7: p_mastery}` aggregator the radar (and eventually `aggregate_skill_profile`) can swap in.

### 9.5 Progression

**Module**: `src/tompe/services/progression.py` (Sprint #8)

- **`recommend_next_level(profile)`** — returns the next `AnnotationLevel` if the BKT mastery for every prerequisite skill clears `DEFAULT_MASTERY_THRESHOLD = 0.98` *and* the observation count clears `DEFAULT_MIN_OBSERVATIONS`; otherwise `None`. Prerequisite skill mapping per level lives in `_prerequisite_skills_for(level)`.
- **`is_level_unlocked(student, level)`** — guards `allowed_levels` updates against the same threshold.
- **`recommend_exercises(profile, items, max_recommendations=10)`** — ranks candidate items by overlap with the student's blind spots: an item scores high if it contains errors in `(MQM × ToM)` cells where the student is weakest. Feeds the teacher Exercise Builder's "AI-suggested items" expander (Sprint #9).

The teacher dashboard (Sprint #9) consumes these directly: the "Approve promotion" button only fires when `recommend_next_level` returns non-None; held-back promotions list which prerequisite skills are blocking the advance with their `(p, n)` so the teacher can target them.

---

## 10. Research Infrastructure

### 10.1 Pipeline Validation (CIKM 2026)

**Directory**: `experiments/pipeline_validation/`

Three-track validation of the error injection pipeline:

**Track A — Automated Validation** (N = 196 items, 1 error/item):

| Metric | Result |
|--------|--------|
| A1: Structural pass rate | 96.4% (target: >90%) |
| A2: GEMBA detection rate | 53% (L0: 79%, L3: 41%) |
| A3: COMET score drop | 0.045 (L0: 0.072, L3: 0.034) |

**Track B — Ablation Baselines** (N = 60 segments × 4 conditions):

| Condition | Structural | Category Fidelity | Text Preservation |
|-----------|:----------:|:-----------------:|:-----------------:|
| B0: Random (no LLM) | 0% | N/A | N/A |
| B1: Single-step LLM | 64% | 100% | 88% |
| B2: Unconstrained LLM | 0% | N/A | 78% |
| **Full pipeline** | **95%** | **100%** | **90%** |

**Track C — Expert Annotation** (84-item set; runner ships, real numbers pending the annotation run):
- `build_annotation_set.py` (Sprint #2 B7) — end-to-end "batch → ablation → annotation_set.json" runner. `--skip-baselines` mode works without an LLM.
- `prepare_annotation_set.py` — segment reuse enforced via `_baseline_sample(forced_segment_ids=…)` (Sprint #2 B8) so B0/B1/B2 share the same source segments.
- `three_way_agreement.py` — Pipeline × Human × GEMBA agreement with IoU alignment + pairwise Cohen's κ + Cochran-Armitage trend by ToM.
- `naturalness_test.py` — pipeline-vs-authentic Mann-Whitney / Fisher / χ².
- `explanation_quality.py` — factual / clarity / completeness aggregates.
- `false_positive_analysis.py` (Sprint #3) — categorises every human-flagged span into true_positive / real_mt_error / genuine_false_alarm using IoU + cached GEMBA.

**Tagging strategy ablation (C1–C4)** (Sprint #3): `ablation_tagging.py` sweeps the same N items through all four tag formats (`TagFormat.C1_PLAIN`/`C2_TAG_ONLY`/`C3_TAG_TYPE_SEV`/`C4_FULL`); Layer 1 metrics (parse / structural / GEMBA detection / category fidelity / text preservation) feed Table 4. Layer 2 (LLM-as-judge) + Layer 3 (expert review) follow-ups still pending.

Scripts: `generate_batch.py`, `run_all.py`, `figures.py`, `tables.py`, plus per-track modules in `track_a/`, `track_b/`, `track_c/`, `baselines/`, plus `ablation_tagging.py`.

### 10.2 ToM Hypothesis Validation

**Directory**: `experiments/tom_validation/`

An 8-step statistical pipeline validating the core hypothesis: errors requiring higher Theory of Mind levels are harder for human raters to detect. Uses WMT-MQM data, Jonckheere-Terpstra trend tests, CLMM (R), and GLMM with rater random effects.

### 10.3 ECTEL 2026 Experiments

**Directory**: `experiments/ectel/`

Experiments supporting the EC-TEL 2026 submission: developmental gradient hypothesis, fluency paradox, over-editing analysis, convergence analysis.

### 10.4 Wasserstein Distance Visualizations

**Directory**: `experiments/wasserstein/`

Teacher-facing dashboard prototypes using the MasteryGap metric (optimal-transport distance between current and target skill distributions).

### 10.5 ECTEL 2026 Pilot Study App

**Directory**: `study/`

Standalone Gradio + Streamlit application for participant data collection: consent → 20 segment evaluations → post-task questionnaire.

---

## 11. Configuration & Deployment

### 11.1 Environment Variables (`.env`)

```bash
OPENAI_API_KEY=sk-proj-...        # GPT-4.1 for injection, GEMBA, explanations
ANTHROPIC_API_KEY=sk-ant-...      # Claude for injection & explanations
OLLAMA_API_KEY=...                # Ollama authentication
TOGETHER_API_KEY=...              # Together AI for open-source models
DEEPL_AUTH_KEY=...                # DeepL translation API
```

### 11.2 Global Settings (`config/settings.yaml`)

```yaml
languages:
  primary_source: "en"
  primary_target: "fr"

segment_selection:
  min_tokens: 10
  max_tokens: 50
  jaccard_dedup_threshold: 0.8

error_injection:
  clean_span_ratio: 0.25
  default_severity_distribution: {minor: 1, major: 2, critical: 0}

qe_validation:
  gemba_detection_rate_threshold: 0.8

scoring:
  iou_threshold: 0.5
  mastery_threshold: 0.8
  sustained_sessions_for_promotion: 3

server:
  api_port: 8000
  student_ui_port: 7860
  teacher_ui_port: 8501
```

### 11.3 Running the Platform

```bash
# Start the FastAPI backend (port 8000)
uv run tompe-api

# Start the student Gradio UI (port 7860)
uv run tompe-student

# Start the teacher Streamlit UI (port 8501)
streamlit run src/tompe/interfaces/teacher_app.py

# Start the annotation UI (port 7861)
PYTHONPATH=src python -m tompe.interfaces.annotation_app
```

---

## 12. End-to-End Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════╗
║                         TEACHER INTERFACE                                ║
║                      (Streamlit — port 8501)                             ║
║                                                                          ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐    ║
║  │  Browse  │ │ Generate │ │  Review  │ │ Exercise │ │  Analytics  │    ║
║  │  Corpus  │ │ MT + L3  │ │  Items   │ │ Builder  │ │ + BKT + FB  │    ║
║  │  + TMX/  │ │ Compare  │ │          │ │ + AI-sug │ │             │    ║
║  │   TSV up │ │  + L0    │ │          │ │  exer.   │ │             │    ║
║  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬──────┘    ║
╚═══════│════════════│════════════│════════════│═══════════════│═══════════╝
        │            │            │            │               │
        ▼            ▼            ▼            ▼               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  SERVICES LAYER (Direct Imports for teacher)             │
│                                                                          │
│  ┌────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ ┌──────┐ ┌────────────┐ │
│  │auth.py │ │datastore │ │scoring │ │analytics│ │bkt.py│ │progression │ │
│  │        │ │   .py    │ │  .py   │ │   .py   │ │      │ │   .py      │ │
│  └────────┘ └──────────┘ └────────┘ └─────────┘ └──────┘ └────────────┘ │
│                                                                          │
│  ┌─────────────┐  ┌─────────────────────────────────────────────────┐    │
│  │ feedback.py │  │ badges.py  (+ visibility + threshold overrides) │    │
│  └─────────────┘  └─────────────────────────────────────────────────┘    │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          PIPELINE LAYER (Async)                          │
│                                                                          │
│  segment_selector ─▶ mt_generator ─▶ error_injector ────┐                │
│       (tom-aware)                  │ (+ opt-in GEMBA    │                │
│                                    │   gating, C1–C4)   │                │
│                                    ▼                    ▼                │
│                          authentic_detector       qe_validator           │
│                          (GEMBA → taxonomy)      (GEMBA-MQM 0.5)         │
│                                    │                    │                │
│                                    └──────────┬─────────┘                │
│                                               ▼                          │
│  comparison_builder ──▶ item_builder ◀── explanation_generator           │
│   (multi-MT + human)   (CONTROLLED +     (L1 LLM + L2a/b cache)          │
│                         AUTHENTIC)                                       │
│                              │                                           │
│                              ▼                                           │
│                  false_annotation_generator                              │
│                  (LLM / rule / manual / none) → Exercise.false_annot.    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  llm_client.py — Unified async client                              │  │
│  │  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────────────┐         │  │
│  │  │ OpenAI  │ │Anthropic │ │ Ollama │ │   Together AI    │         │  │
│  │  └─────────┘ └──────────┘ └────────┘ └──────────────────┘         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  codebook.py ── mqm_taxonomy.py (42 types, 4 ToM levels, 7 skills)       │
│  corpus_ingest.py (TMX/TSV) ── tag_formats.py (C1–C4)                    │
└──────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER (JSON Files)                          │
│                                                                          │
│  data/corpora/     ← Parallel text (OPUS + uploaded TMX/TSV)             │
│  data/codebook/    ← Taxonomy (8 done + 3 drafts + 34 stubs) + L2 cache  │
│  data/items/       ← Assessment items (draft / reviewed / published)     │
│  data/students/    ← Accounts (consent, tutorial_completed)              │
│  data/classes/     ← ClassGroup (badges_visible, threshold_overrides)    │
│  data/exercises/   ← Exercises (mode, false_annotation_mode, decoys)     │
│  data/sessions/    ← Responses (eval/PE/navigator/comparison) + tokens   │
│  data/badges/      ← StudentBadges (earned + XP history)                 │
│  data/bkt/         ← StudentBKT (per_skill BKT state)                    │
│  data/profiles/    ← StudentProfile snapshots (analytics cache)          │
│  data/annotations/ ← Expert annotation data + _gemba/ FP-analysis cache  │
└──────────────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════╗
║                      FASTAPI BACKEND (port 8000)                         ║
║                                                                          ║
║  /api/auth/      /api/consent/   /api/tutorial/   /api/assignments/      ║
║  /api/exercises/ /api/items/     /api/responses/  /api/feedback/         ║
║  /api/classes/   /api/students/  /api/analytics/  /api/progress/         ║
║  /api/badges/                                                            ║
╚═══════════════════════════════════╤══════════════════════════════════════╝
                                    │ HTTP (REST)
                                    ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                          STUDENT INTERFACE                               ║
║                       (Gradio — port 7860)                               ║
║                                                                          ║
║  Login → Consent → Tutorial (3 steps, once per account) → Main           ║
║                                                                          ║
║  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐     ║
║  │ Annotate panel │  │   Justify      │  │      Feedback          │     ║
║  │ ┌──────────┐   │  │ (Cognitive     │  │ (Layer 1 + 2a + 2b     │     ║
║  │ │ L0 cards │   │──▶  Forcing)      │──▶  + L3 reveal panel +   │     ║
║  │ │ L1/L2/L3 │   │  │ skipped for    │  │  badge toasts)         │     ║
║  │ │ Compare  │   │  │ L0 + Compare   │  │                        │     ║
║  │ │ PE panel │   │  │                │  │                        │     ║
║  │ └──────────┘   │  │                │  │                        │     ║
║  └────────────────┘  └────────────────┘  └────────────────────────┘     ║
║                                                                          ║
║  My Progress: BKT-fed Skill Radar │ Badge Collection │ Recent exercises  ║
║  Scaffolding: L0 Navigator │ L1 Guided │ L2 Independent │ L3 Expert      ║
║  PE diff (B8) │ L0 Confirm/Dispute (Sprint #4) │ L3 Compare (Sprint #7)  ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║                       ANNOTATION INTERFACE                               ║
║                       (Gradio — port 7861)                               ║
║                                                                          ║
║  ┌──────────────────────────┐  ┌──────────────────────────────────┐      ║
║  │       Phase A:           │  │        Phase B:                  │      ║
║  │  Error Annotation (84)   │──▶  Explanation Quality Review (24) │      ║
║  │  Blind MQM + animated    │  │  Rate accuracy/clarity/complete  │      ║
║  │  per-item timer (B3)     │  │                                  │      ║
║  └──────────────────────────┘  └──────────────────────────────────┘      ║
║                                                                          ║
║  Self-contained (JSON I/O) │ No backend dependency                       ║
║  Feeds: 3-way agreement + naturalness + explanation-quality + FP-analysis║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║                      RESEARCH INFRASTRUCTURE                             ║
║                                                                          ║
║  experiments/pipeline_validation/                                        ║
║      ├─ track_a/ (structural, GEMBA, COMET)                              ║
║      ├─ track_b/ (B0/B1/B2 baselines, ablation)                          ║
║      ├─ track_c/ (3-way agreement, naturalness, expl quality, FP)        ║
║      ├─ ablation_tagging.py (C1–C4 tag-format ablation)                  ║
║      └─ tables.py / figures.py / run_all.py                              ║
║  experiments/tom_validation/   ← ToM hypothesis (R+Python)               ║
║  experiments/ectel/            ← EC-TEL 2026 experiments                 ║
║  experiments/wasserstein/      ← MasteryGap dashboards                   ║
║  study/                        ← Standalone pilot study app              ║
║  scripts/                      ← scaffold_codebook_entries + validate    ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### Data Flow Summary

1. **Teacher ingests** parallel corpora — either from OPUS (`scripts/ingest_corpus.py`) or directly via the **Upload Corpus** page (TMX/TSV through `corpus_ingest.py`) — into `data/corpora/`.
2. **Pipeline produces items** via one of three pathways:
   - **CONTROLLED** — `segment_selector` (tom-aware) → `mt_generator` → `error_injector` (two-step LLM + span realignment + optional GEMBA gate, parameterised by `TagFormat` C1–C4) → `qe_validator` → `explanation_generator` (with template cache) → `item_builder`.
   - **AUTHENTIC** — real MT output → `authentic_detector` (GEMBA → taxonomy mapping) → `explanation_generator` → `item_builder`.
   - **COMPARISON** — multiple MT outputs (+ human reference) → `comparison_builder` → `item_builder` (with empty `errors`, populated `comparison_outputs`).
3. **Teacher reviews** draft items, approves/edits, publishes. L0 exercises optionally get **false-annotation decoys** generated at exercise-creation time and stored on `Exercise.false_annotations[item_id]`.
4. **Teacher composes exercises** from published items, manually or via the **AI-suggested expander** that runs `recommend_exercises(profile, items)` against a target student's blind spots.
5. **Teacher assigns** exercises to entire classes or individual students. Per-class `badges_visible` + `badge_threshold_overrides` apply.
6. **Student logs in** — login → consent (if pending) → tutorial overlay (if pending, once per account) → main view.
7. **Per-level Annotate flow** is mode-aware:
   - **L0** — Confirm/Dispute cards (per-card reasoning); submits directly to Feedback.
   - **L1/L2/L3 standard** — span selection + classification → Justify (4 modes) → Feedback.
   - **L3 Comparison** — 4 masked system cards + ranking + triage + "which is human?"; submits directly to Feedback.
   - **PE mode** — direct edit with live char-level diff (`_build_pe_diff_html`).
8. **Scoring** is dispatched per mode in `api_get_feedback`: `score_evaluation_response` (IoU), `score_postediting_response` (HTER), `score_navigator_response` (confirm/dispute counts), `score_comparison_response` (Kendall's τ + human-vs-MT).
9. **Feedback** assembles a cognitive-forcing payload: student justification displayed first, then Layer 1 / 2a / 2b explanations, then the L3 comparison reveal panel when applicable.
10. **Badges + XP** — `process_badges_and_xp` runs after every submission. Honors per-class visibility (responses masked but tracking continues server-side) and per-class threshold overrides. Three behaviour badges are live: Clean Sheet (Sprint #1 A2), Trap Detector (Sprint #4), False Positive Discipline.
11. **BKT update** — each scored response advances `StudentBKT.per_skill` via Bayesian Knowledge Tracing; `bkt_skill_profile(student_id)` aggregates `{S1..S7: p_mastery}`.
12. **Analytics** — `update_student_profile` writes a `StudentProfile` snapshot; `detect_blind_spots` populates `BlindSpot.example_item_ids`; `recommend_next_level` gates promotion on BKT mastery thresholds.
13. **Teacher dashboard** consumes all of the above: BKT Skill Mastery table + Blind Spots table + BKT-gated Level Progression panel + AI-suggested exercises (Sprint #9). The "Approve promotion" button only fires when `recommend_next_level` returns non-None; held-back promotions list the blocking prerequisite skills with their `(p, n)`.
14. **Expert annotation** (validation study) — annotator evaluates pipeline items blind, then reviews explanation quality. Animated per-item timer (Sprint #2 B3). Results feed three-way agreement, naturalness, explanation quality, **and false-positive analysis** (Sprint #3) which categorises every human flag into true_positive / real_mt_error / genuine_false_alarm.
