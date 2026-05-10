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
9. [Scoring, Feedback & Analytics](#9-scoring-feedback--analytics)
10. [Research Infrastructure](#10-research-infrastructure)
11. [Configuration & Deployment](#11-configuration--deployment)
12. [End-to-End Architecture Diagram](#12-end-to-end-architecture-diagram)

---

## 1. System Overview

ToM-PE is a pedagogical platform that trains translation students to critically evaluate machine translation (MT) output through scaffolded post-editing exercises. The platform is grounded in Theory of Mind (ToM) — the cognitive ability to attribute mental states to others — applied to understanding how MT systems "think" and where they fail.

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Teacher UI | **Streamlit** (`teacher_app.py`) | Corpus management, item review, class admin |
| Student UI | **Gradio** (`student_app.py`) | Three-phase PE training workflow |
| Annotation UI | **Gradio** (`annotation_app.py`) | Expert MQM annotation for pipeline validation |
| Backend API | **FastAPI** (`api.py`) | REST endpoints for student-facing operations |
| Data Pipeline | **Async Python** | Segment selection, MT generation, error injection |
| LLM Integration | **httpx** (async) | OpenAI, Anthropic, Ollama, Together AI |
| MT Systems | **REST APIs** | Google Translate, DeepL |
| Data Models | **Pydantic v2** | Typed schemas for all entities |
| Storage | **JSON files** | One file per entity in `data/` directory |
| Authentication | **bcrypt + bearer tokens** | Student login, 7-day token sessions |

### Repository Structure

```
ToM-PE/
├── src/tompe/
│   ├── schemas/          # Pydantic data models
│   │   ├── annotation.py         # Scaffolding annotation config (L0-L3)
│   │   ├── badges.py             # Badge definitions and progress
│   │   ├── competency.py         # Skill competency framework (S1-S7)
│   │   ├── corpus.py             # CorpusSegment, MTOutput, IATETerm
│   │   ├── enums.py              # PrimaryTag, TOMLevel, Severity, SkillID, etc.
│   │   ├── error.py              # InjectedError, DetectedError, explanations
│   │   ├── expert_annotation.py  # ExpertAnnotation, ExplanationRating (validation)
│   │   ├── item.py               # AssessmentItem, ItemMetadata
│   │   ├── response.py           # StudentResponse, Justification
│   │   ├── scoring.py            # ScoringResult, BlindSpot
│   │   └── session.py            # StudentAccount, ClassGroup, Exercise
│   ├── pipeline/         # Item generation pipeline (6 stages)
│   │   ├── segment_selector.py   # Corpus filtering and sampling
│   │   ├── mt_generator.py       # MT system translation
│   │   ├── error_injector.py     # Two-step LLM error injection + span realignment
│   │   ├── qe_validator.py       # GEMBA-MQM + xCOMET validation
│   │   ├── explanation_generator.py  # Three-layer explanation generation
│   │   ├── item_builder.py       # Final assembly
│   │   ├── llm_client.py         # Unified async LLM client (4 providers)
│   │   ├── codebook.py           # Error codebook loader and query interface
│   │   ├── mqm_taxonomy.py       # 42 error types with ToM/skill mappings
│   │   ├── authentic_detector.py # Authentic MT error detection
│   │   ├── _injection_prompts.py # Step 1/2 prompt templates
│   │   └── _translation_prompts.py  # MT prompt strategies
│   ├── services/         # API, auth, scoring, feedback, analytics, badges
│   │   ├── api.py                # FastAPI application
│   │   ├── auth.py               # Authentication service
│   │   ├── datastore.py          # JSON file CRUD operations
│   │   ├── scoring.py            # IoU span matching, F1, HTER
│   │   ├── feedback.py           # Cognitive forcing feedback assembly
│   │   ├── badges.py             # Badge awarding and XP calculation
│   │   ├── analytics.py          # Blind spot detection, student profiles
│   │   └── progression.py        # BKT-based scaffolding level advancement
│   └── interfaces/       # User interfaces
│       ├── student_app.py        # Gradio student training UI
│       ├── teacher_app.py        # Streamlit teacher admin UI
│       ├── annotation_app.py     # Gradio expert annotation UI (validation)
│       ├── api_client.py         # HTTP client for Student ↔ Backend
│       └── components/
│           ├── span_selector.py  # Interactive text span selection (JS+HTML)
│           └── colors.py         # Colorblind-safe MQM tag palette
├── config/               # settings.yaml, mt_backends.yaml, badges.json
├── assets/badges/        # Badge icon images (40+ JPGs)
├── data/                 # All persistent data (JSON, JSONL)
│   ├── corpora/          # Parallel text with document IDs
│   ├── codebook/         # Error taxonomy (8 entries) + tag schema (42 types)
│   ├── annotations/      # Expert annotation data (validation study)
│   └── ...               # items, students, exercises, sessions, badges, etc.
├── scripts/              # Corpus ingestion, batch generation
│   └── ingest_corpus.py  # OPUS download with document structure preservation
├── experiments/
│   ├── pipeline_validation/  # CIKM 2026 validation experiments
│   ├── ectel/                # EC-TEL 2026 experiments
│   ├── tom_validation/       # ToM hypothesis validation (R + Python)
│   └── wasserstein/          # MasteryGap dashboard visualizations
├── study/                # Standalone ECTEL 2026 pilot study app
├── specs/                # Specification documents
├── docs/                 # Architecture documentation
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

**Ingestion** is handled by `scripts/ingest_corpus.py`, which uses `opustools.OpusRead` to download OPUS XML-aligned data and extract sentence pairs with document metadata. Output is stored as JSONL in `data/corpora/{corpus}/segments_en_fr.jsonl`.

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

Located at `data/codebook/error_codebook_fr_en.json`, the codebook defines **8 detailed entries** with few-shot examples across the **42 error types** enumerated in `data/codebook/tag_schema.json`. The 42 types span **10 MQM primary categories** and **4 ToM levels**.

Each codebook entry includes:

- Machine-readable identifiers (codebook ID, MQM hierarchy path)
- Severity range (minor / major / critical)
- Theory of Mind level assignment (1st-machine, 1st-author, 2nd-reader, recursive)
- Primary competency skill (S1-S7)
- Definition with boundary conditions ("what this is NOT")
- Few-shot examples with inline XML-tagged errors and multi-layer explanations

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

The item generation pipeline transforms raw parallel text into pedagogically-graded assessment items through six sequential stages. Each stage is implemented as an async Python module in `src/tompe/pipeline/`.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Segment    │    │      MT      │    │    Error     │
│  Selection   │───▶│  Generation  │───▶│  Injection   │
│              │    │              │    │  (2-step)    │
└──────────────┘    └──────────────┘    └──────────────┘
                                              │
                                              ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│     Item     │    │ Explanation  │    │      QE      │
│   Assembly   │◀───│  Generation  │◀───│  Validation  │
│              │    │  (3 layers)  │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
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

1. **GEMBA-MQM** (LLM-as-a-judge) performs MQM-categorized error detection on the injected text using structured JSON output. Detected errors are matched to injected ground truth via text overlap and IoU-based span matching.
2. **COMET** (wmt22-comet-da, reference-based) scores both the clean reference and the error-injected text against the source. The injected version must show measurable quality degradation (score drop > 0).

Items that fail validation are flagged for manual review or discarded.

### 3.5 Explanation Generation (Three Layers)

**Module**: `src/tompe/pipeline/explanation_generator.py`

Each injected error receives up to three layers of explanation, generated by LLM prompts with codebook context:

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

### 3.6 Item Assembly

**Module**: `src/tompe/pipeline/item_builder.py`

The final stage assembles all pipeline outputs into a complete `AssessmentItem`:

```python
AssessmentItem:
  item_id: str
  source_text: str                    # Original source (FR or EN)
  presented_text: str                 # MT with injected errors (what students see)
  reference_translation: str          # Clean reference (hidden until feedback)
  mt_system: str                      # Which MT system produced the base
  errors: list[InjectedError]         # Ground truth errors with all metadata
  difficulty_level: int               # 1–5 scale
  domain: str                         # e.g., "parliamentary", "legal"
  item_status: "draft" | "reviewed" | "published" | "retired"
  metadata: ItemMetadata              # ToM profile, MQM profile, scaffolding level
```

Items are stored as individual JSON files in `data/items/` and progress through a status lifecycle: **draft** (auto-generated) → **reviewed** (teacher-approved) → **published** (available for exercises) → **retired** (removed from active use).

---

## 4. Teacher Workflow

The teacher interface is a **Streamlit** application (`src/tompe/interfaces/teacher_app.py`) that runs locally and accesses services directly (no API layer). It provides nine functional pages:

### 4.1 Corpus Management

**Browse Corpus**: Filter segments by corpus source, domain, translation direction, register, and token range. Search within source/reference text. Preview segments with computed complexity scores.

**Upload Corpus**: Add new parallel corpora. Files are auto-ingested to JSONL format with domain metadata assignment.

### 4.2 Item Generation

**Generate Translations**: Select corpora and MT systems (multi-select), then batch-generate translations with progress monitoring. Results feed into the error injection pipeline.

The teacher can trigger the full pipeline: segment selection → MT generation → error injection → QE validation → explanation generation. This produces draft items ready for review.

### 4.3 Item Review

**Review Queue**: The teacher reviews draft items in a dedicated editor:
- Visual span selection for annotation verification
- Error classification review (MQM tag, type, severity, ToM level, skill)
- Manual editing of generated explanations
- Difficulty rating (1–5)
- Status transitions: draft → reviewed → published

**Published Items**: Browse curated items filtered by domain, difficulty, and target skill. Per-item analytics show how students have performed on each item.

### 4.4 Exercise Builder

Teachers compose exercises from published items with full control over pedagogical parameters:

| Parameter | Options | Purpose |
|-----------|---------|---------|
| Mode | Evaluation / Post-editing / Both | What students are asked to do |
| Scaffolding level | Navigator / Guided / Independent / Expert | How much support is provided |
| Item ordering | Manual / Difficulty / Random | Sequence strategy |
| Clean segment ratio | 0.0–1.0 | Proportion of error-free items (tests false positive bias) |
| False annotation ratio | 0.0–1.0 | Proportion of deliberately misleading annotations (L0/L1) |
| Justification type | Free text / Structured / Both | How students explain their reasoning |

Exercises are assigned to entire classes or individual students.

### 4.5 Class & Student Management

- Create and edit class groups
- Bulk import students via CSV
- Set per-student scaffolding levels and allowed level range
- View enrollment and active consent status
- Monitor progression stage (Orientation → Guided Detection → Independent → Dual Mode → Expert)

### 4.6 Analytics Dashboard

- **Class-level aggregates**: Average detection rates, F1 scores, HTER across exercises
- **Per-student time series**: Performance trends over sessions
- **Blind spot detection**: Identifies MQM categories and ToM levels where a student consistently underperforms
- **Difficulty progression recommendations**: Suggests when students are ready to advance

### 4.7 Settings

Load and edit `config/settings.yaml` and `config/mt_backends.yaml` directly from the UI.

---

## 5. Student Workflow

The student interface is a **Gradio** application (`src/tompe/interfaces/student_app.py`) that communicates with the FastAPI backend over HTTP. Students interact through a structured three-phase cognitive forcing protocol.

### 5.1 Login & Consent

1. Student logs in with username/password.
2. On first login, a two-tier research consent form is presented:
   - **Tier 1**: Allow interaction data (responses, time, scaffolding level) for research.
   - **Tier 2**: Allow anonymized text excerpts (student justifications) in publications.
   - Refusal does not affect grades or platform access. Consent can be withdrawn at any time.

### 5.2 Exercise Selection

The student sees their assigned exercises with metadata: exercise name, mode, number of items, and completion status. They select an exercise to begin.

### 5.3 Phase 1 — Error Identification

The student sees the **presented text** (MT output with injected errors) alongside the **source text**. Depending on their scaffolding level, they may also see:

| Level | Name | What the Student Sees |
|-------|------|----------------------|
| **L0** | Navigator | Full annotations: error spans highlighted, MQM labels, severity badges, ToM hints, guiding questions |
| **L1** | Guided | Region highlights (approximate location) with hint text, but no labels |
| **L2** | Independent | No annotations — raw MT output only |
| **L3** | Expert | No annotations + clean spans mixed in + multiple MT systems to compare |

**In evaluation mode**, the student:
- Selects error spans by dragging over text (via the `span_selector.py` component)
- Classifies each span: MQM primary tag, severity, confidence level

**In post-editing mode**, the student:
- Directly edits the presented text to correct errors
- The system computes HTER against the reference

**In comparison mode** (L3 only):
- Evaluates multiple MT system outputs for the same source
- Ranks systems holistically
- Makes PE triage decisions ("Is this worth post-editing?")

### 5.4 Phase 2 — Justification (Cognitive Forcing)

Before seeing any feedback, the student must justify each detected error. This is the core pedagogical mechanism — it forces metacognitive reflection.

**Free-text mode**: Open-ended reasoning field.

**Structured mode** (ToM-guided prompts):
1. *"What did the MT system misunderstand about the source?"* (1st-order: machine perspective)
2. *"What did the original author intend?"* (1st-order: author perspective)
3. *"What would a target-language reader understand from this translation?"* (2nd-order: reader perspective)

The justification is submitted and **locked** before Phase 3 reveals explanations.

### 5.5 Phase 3 — Feedback Display

After justification submission, the system reveals:

1. **Scoring summary**: True positives, false positives, missed errors, precision, recall, F1.
2. **Per-error comparison**:
   - Student's classification vs. ground truth (MQM tag, severity match)
   - Student's own justification (displayed first for metacognitive reflection)
   - **Layer 1**: Contrastive explanation
   - **Layer 2a**: System behavior explanation (collapsible "How It Works")
   - **Layer 2b** (optional): Technical NLP deep dive (collapsible "Under the Hood")
3. **Missed errors**: Errors the student did not detect, with full explanations.
4. **False positives**: Spans the student flagged that are not actual errors.

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
- Per-item **elapsed timer** and progress indicator ("Item X / Y")
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

**Behaviour badges**:

- **Clean Sheet**: Perfect score on an item (zero FP, all errors detected)
- **Trap Detector**: Correctly identifies false annotations at Navigator level
- **False Positive Discipline**: Maintains zero false positives at Expert level

### 7.2 XP System

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

### 7.3 UI Integration

- **Student app**: Badge collection display with visual hierarchy, progress bars toward next tiers, and XP history
- **Teacher app**: Badge analytics tab with class-wide heatmap showing badge distribution across students

---

## 8. Backend Services

### 8.1 FastAPI Application

**Module**: `src/tompe/services/api.py`
**Default port**: 8000, CORS enabled for Gradio cross-origin requests.

#### Endpoint Groups

| Group | Path Prefix | Purpose |
|-------|------------|---------|
| Authentication | `/api/auth/` | Login, logout, token management |
| Consent | `/api/consent/` | Research consent text, status, submission, withdrawal |
| Assignments | `/api/assignments/` | Student exercise assignments |
| Exercises | `/api/exercises/` | Exercise CRUD, assignment to classes/students |
| Items | `/api/items/` | Assessment item retrieval and querying |
| Responses | `/api/responses/` | Annotation submission, justifications, feedback retrieval |
| Classes | `/api/classes/` | Class management (teacher/admin) |
| Students | `/api/students/` | Student CRUD, bulk import, level management |
| Analytics | `/api/analytics/` | Per-student and per-class performance metrics |
| Badges | `/api/badges/` | Badge collection, XP history, progress summaries |

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

A generic `JsonStore` class provides CRUD operations over JSON files with Pydantic validation.

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

## 9. Scoring, Feedback & Analytics

### 9.1 Scoring

**Module**: `src/tompe/services/scoring.py`

**Span matching** uses character-level Intersection over Union (IoU):

```
IoU = |intersection| / |union|
Match if IoU ≥ 0.5 (configurable threshold)
```

Metrics computed: precision, recall, F1, per-MQM breakdown, per-ToM breakdown, per-skill breakdown.

For post-editing mode: HTER, unnecessary edits, edit quality.

### 9.2 Feedback (Cognitive Forcing Protocol)

**Module**: `src/tompe/services/feedback.py`

The student cannot see correct answers before committing their reasoning. Feedback includes: summary metrics, per-error comparisons with student justification displayed alongside Layer 1/2a/2b explanations, missed errors, and false positive diagnostics.

### 9.3 Analytics & Blind Spot Detection

**Module**: `src/tompe/services/analytics.py`

Identifies systematic weaknesses per (MQM category × ToM level) combination where detection rate < 0.5 over ≥ 3 sessions.

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

**Track C — Expert Annotation** (pending: 84 items + explanation review):
- Three-way agreement analysis (Pipeline × Human × GEMBA)
- Explanation quality ratings (factual accuracy, clarity, completeness)

Scripts: `generate_batch.py`, `run_all.py`, `figures.py`, `tables.py`, plus per-track modules in `track_a/`, `track_b/`, `track_c/`, and `baselines/`.

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
║                         TEACHER INTERFACE                              ║
║                      (Streamlit — port 8501)                           ║
║                                                                        ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐  ║
║  │  Browse  │ │ Generate │ │  Review  │ │ Exercise │ │  Analytics  │  ║
║  │  Corpus  │ │    MT    │ │  Items   │ │ Builder  │ │  Dashboard  │  ║
║  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬──────┘  ║
╚═══════│════════════│════════════│════════════│═══════════════│═════════╝
        │            │            │            │               │
        ▼            ▼            ▼            ▼               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    SERVICES LAYER (Direct Imports)                    │
│                                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────┐  │
│  │  auth.py │  │datastore │  │ scoring  │  │analytics.py│  │badges│  │
│  │          │  │   .py    │  │   .py    │  │            │  │  .py │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  └──────┘  │
└───────────────────────────┬───────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     PIPELINE LAYER (Async)                            │
│                                                                       │
│  segment_selector ──▶ mt_generator ──▶ error_injector                │
│                                              │                        │
│  item_builder ◀── explanation_generator ◀── qe_validator             │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  llm_client.py — Unified async client                        │     │
│  │  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────────────┐   │     │
│  │  │ OpenAI  │ │Anthropic │ │ Ollama │ │   Together AI    │   │     │
│  │  └─────────┘ └──────────┘ └────────┘ └──────────────────┘   │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  codebook.py ── mqm_taxonomy.py (42 types, 4 ToM levels)            │
└───────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      DATA LAYER (JSON Files)                         │
│                                                                       │
│  data/corpora/     ← Parallel text with document IDs (JSONL)        │
│  data/codebook/    ← Error taxonomy (8 entries) + tag schema (42)   │
│  data/items/       ← Assessment items (draft/reviewed/published)     │
│  data/students/    ← Student accounts                                │
│  data/exercises/   ← Exercise definitions + assignments              │
│  data/sessions/    ← Responses & auth tokens                         │
│  data/annotations/ ← Expert annotation data (validation study)       │
│  data/badges/      ← Earned badges & XP records                      │
└───────────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════╗
║                      FASTAPI BACKEND (port 8000)                       ║
║                                                                        ║
║  /api/auth/    /api/consent/   /api/assignments/   /api/exercises/     ║
║  /api/items/   /api/responses/ /api/analytics/     /api/badges/        ║
╚═══════════════════════════════════╤════════════════════════════════════╝
                                    │ HTTP (REST)
                                    ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                        STUDENT INTERFACE                               ║
║                      (Gradio — port 7860)                              ║
║                                                                        ║
║  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐   ║
║  │   Phase 1:     │  │   Phase 2:     │  │      Phase 3:          │   ║
║  │   Identify     │──▶  Justify       │──▶   Feedback             │   ║
║  │   Errors       │  │  (Cognitive    │  │  (Explanations         │   ║
║  │                │  │   Forcing)     │  │   revealed)            │   ║
║  └────────────────┘  └────────────────┘  └────────────────────────┘   ║
║                                                                        ║
║  Scaffolding: L0 Navigator │ L1 Guided │ L2 Independent │ L3 Expert   ║
║  Gamification: Badges (progression/specialisation/behaviour) + XP      ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║                     ANNOTATION INTERFACE                               ║
║                      (Gradio — port 7861)                              ║
║                                                                        ║
║  ┌──────────────────────────┐  ┌──────────────────────────────────┐   ║
║  │     Phase A:             │  │      Phase B:                    │   ║
║  │  Error Annotation (84)   │──▶  Explanation Quality Review (24) │   ║
║  │  Blind MQM annotation    │  │  Rate accuracy/clarity/complete  │   ║
║  └──────────────────────────┘  └──────────────────────────────────┘   ║
║                                                                        ║
║  Self-contained (JSON I/O) │ No backend dependency                     ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║                     RESEARCH INFRASTRUCTURE                            ║
║                                                                        ║
║  experiments/pipeline_validation/  ← CIKM 2026 (Track A/B/C)         ║
║  experiments/tom_validation/       ← ToM hypothesis (R+Python)        ║
║  experiments/ectel/                ← EC-TEL 2026 experiments          ║
║  experiments/wasserstein/          ← MasteryGap dashboards            ║
║  study/                            ← Standalone pilot study app       ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### Data Flow Summary

1. **Teacher ingests** parallel corpora from OPUS (with document IDs) into `data/corpora/`.
2. **Pipeline selects** segments (including multi-sentence L3 segments), generates MT output, injects controlled errors (1 or more per item), validates via QE, generates three-layer explanations, and assembles items.
3. **Teacher reviews** draft items, approves/edits, publishes, and builds exercises.
4. **Teacher assigns** exercises to classes or individual students.
5. **Student logs in**, selects an exercise, and enters the three-phase workflow.
6. **Phase 1**: Student identifies errors in the presented MT text (with scaffolding appropriate to their level).
7. **Phase 2**: Student justifies each detection before seeing answers (cognitive forcing).
8. **Phase 3**: System scores the response, reveals explanations, awards badges and XP, and stores results.
9. **Analytics** track performance over time, detect blind spots, and recommend progression.
10. **Gamification** awards progression, specialisation, and behaviour badges; XP scales with ToM level and scaffolding independence.
11. **Expert annotation** (validation study): annotator evaluates pipeline items blind, then reviews explanation quality. Results feed three-way agreement analysis.
