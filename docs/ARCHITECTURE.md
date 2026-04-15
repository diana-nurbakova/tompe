# ToM-PE System Architecture

**Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training**

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Sources](#2-data-sources)
3. [Data Preparation Pipeline](#3-data-preparation-pipeline)
4. [Teacher Workflow](#4-teacher-workflow)
5. [Student Workflow](#5-student-workflow)
6. [Gamification & Badges](#6-gamification--badges)
7. [Backend Services](#7-backend-services)
8. [Scoring, Feedback & Analytics](#8-scoring-feedback--analytics)
9. [Research Infrastructure](#9-research-infrastructure)
10. [Configuration & Deployment](#10-configuration--deployment)
11. [End-to-End Architecture Diagram](#11-end-to-end-architecture-diagram)

---

## 1. System Overview

ToM-PE is a pedagogical platform that trains translation students to critically evaluate machine translation (MT) output through scaffolded post-editing exercises. The platform is grounded in Theory of Mind (ToM) — the cognitive ability to attribute mental states to others — applied to understanding how MT systems "think" and where they fail.

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Teacher UI | **Streamlit** (`teacher_app.py`) | Corpus management, item review, class admin |
| Student UI | **Gradio** (`student_app.py`) | Three-phase PE training workflow |
| Backend API | **FastAPI** (`api.py`) | REST endpoints for student-facing operations |
| Data Pipeline | **Async Python** | Segment selection, MT generation, error injection |
| LLM Integration | **httpx** (async) | OpenAI, Anthropic, Ollama, Together AI |
| MT Systems | **REST APIs** | Google Translate, DeepL |
| Data Models | **Pydantic** | Typed schemas for all entities |
| Storage | **JSON files** | One file per entity in `data/` directory |
| Authentication | **bcrypt + bearer tokens** | Student login, 7-day token sessions |

### Repository Structure

```
ToM-PE/
├── src/tompe/
│   ├── schemas/          # Pydantic data models (items, students, competency, badges)
│   ├── pipeline/         # Item generation pipeline (6 stages)
│   ├── services/         # API, auth, scoring, feedback, analytics, badges
│   └── interfaces/       # Teacher (Streamlit) & Student (Gradio) UIs
├── config/               # settings.yaml, mt_backends.yaml, badges.json
├── assets/badges/        # Badge icon images (40+ PNGs)
├── data/                 # All persistent data (JSON, JSONL)
├── scripts/              # Batch ingestion, generation & report scripts
├── study/                # Standalone ECTEL 2026 pilot study app
├── experiments/
│   ├── ectel/            # ECTEL 2026 submission experiments (3a, 3b)
│   ├── tom_validation/   # ToM hypothesis validation pipeline (R + Python)
│   └── wasserstein/      # MasteryGap dashboard visualizations
├── screenshots/          # Labelled UI screenshots (student & teacher workflows)
├── docs/                 # Architecture, fluency-trap spec
└── tests/                # Test suite
```

---

## 2. Data Sources

### 2.1 Parallel Corpora (OPUS)

The platform ingests sentence-aligned parallel corpora from the OPUS project, covering four EU/UN domains:

| Corpus | Domain | Approx. Size | Register |
|--------|--------|-------------|----------|
| **Europarl v8** | Parliamentary proceedings | ~2M segments | Formal |
| **DGT-TM v2019** | EU legal translation memory | ~5M segments | Formal |
| **EUbookshop v2** | EU publications & legislation | ~10M segments | Semi-formal |
| **UNPC v1.0** | UN institutional documents | ~30M segments | Formal |

**Ingestion** is handled by `scripts/ingest_corpus.py`, which downloads pre-aligned Moses-format files from OPUS, converts them to JSONL, and stores them in `data/corpora/{corpus}/segments_en_fr.jsonl`.

Each segment follows the schema:

```json
{
  "segment_id": "europarl_00042",
  "source_text": "Le Parlement a adopté la résolution.",
  "reference_translation": "Parliament adopted the resolution.",
  "source_lang": "fr",
  "target_lang": "en",
  "corpus_origin": "europarl",
  "domain": "parliamentary",
  "register": "formal"
}
```

### 2.2 Error Codebook

Located at `data/codebook/error_codebook_fr_en.json`, the codebook defines **37 error types** across **10 MQM primary categories**. Each entry includes:

- Machine-readable identifiers (codebook ID, MQM hierarchy path)
- Severity range (minor / major / critical)
- Theory of Mind level assignment (1st-machine, 1st-author, 2nd-reader, recursive)
- Primary competency skill (S1–S7)
- Definition with boundary conditions ("what this is NOT")
- Few-shot examples with inline XML-tagged errors and three-layer explanations

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

1. **Token-length filtering**: Segments must be between 10–50 tokens (configurable) to ensure they are neither trivially short nor overwhelmingly long for student review.
2. **Exact deduplication**: Token-set identity check removes verbatim duplicates.
3. **Near-duplicate removal**: Jaccard similarity threshold (default 0.8) eliminates paraphrastic duplicates that would reduce exercise variety.
4. **Complexity scoring**: Each segment receives a [0, 1] complexity score based on sentence length and terminology density.
5. **Stratified sampling**: Final selection draws proportionally from each corpus to ensure domain diversity.

**Key functions**:
- `load_corpus(corpus_dir, origin)` — Parse JSONL files
- `filter_segments(segments, min_tokens, max_tokens, jaccard_threshold)` — Apply all filters
- `select_segments(corpora_dirs, n_segments, ...)` — Full selection pipeline
- `compute_complexity(source_text, terminology_density)` — Difficulty heuristic

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

**Error profiles** specify target distributions: which MQM categories, severity mix (e.g., 1 minor : 2 major : 0 critical), and ToM levels to include in a given item.

### 3.4 QE Validation

**Module**: `src/tompe/pipeline/qe_validator.py`

Quality estimation validates that injected errors are genuine degradations and detectable by automated QE systems:

1. **xCOMET-XL** scores both the clean reference and the error-injected text against the source. The injected version must show measurable quality degradation (score drop > 0).
2. **GEMBA-MQM** performs MQM-categorized error detection on the injected text. At least 80% of injected errors must be independently detected.

Items that fail validation are flagged for manual review or discarded. This ensures that the platform's ground truth is consistent with state-of-the-art automatic quality metrics.

### 3.5 Explanation Generation (Three Layers)

**Module**: `src/tompe/pipeline/explanation_generator.py`

Each injected error receives up to three layers of explanation, generated by LLM prompts with codebook context:

**Layer 1 — Contrastive Explanation** (per error instance):
- **MT interpretation**: "The system treated *assister à* as cognate of English *assist*, mapping it to the most frequent translation."
- **Actual meaning**: "In this context, *assister à* means *to attend* or *to be present at*."
- **Reader impact**: "A reader would understand that someone was helping at the conference, not attending it."
- **Correction rationale**: "Replace *assisting at* with *attending* to restore the original meaning."

**Layer 2a — System Behavior** (per error type, accessible language):
- Why MT systems make this specific type of error
- Architectural causes (e.g., shared BPE vocabularies, attention patterns)
- When to expect similar errors in practice
- Whether general-purpose LLMs share this vulnerability

**Layer 2b — Technical NLP** (optional, progressive disclosure):
- Detailed NLP-level explanation
- Key concepts (e.g., "BPE tokenization", "cross-lingual transfer")
- Academic references

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
  explanations_layer1: list           # Contrastive explanations
  explanations_layer2: list           # System behavior explanations
  iate_terms: list[IATETerm]          # Domain terminology
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

Load and edit `config/settings.yaml` and `config/mt_backends.yaml` directly from the UI:
- Toggle MT systems on/off, adjust prompt strategies
- Set segment selection parameters (token range, dedup threshold)
- Configure error injection defaults (severity distribution, clean span ratio)
- Adjust QE validation thresholds
- Modify scoring parameters (IoU threshold, mastery threshold, sustained sessions)

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
   - **Layer 1**: Contrastive explanation — what the MT system "thought" vs. reality
   - **Layer 2a**: System behavior explanation — why MT systems make this error type
   - **Layer 2b** (optional): Technical NLP deep dive with references
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
| S7 | Discourse coherence | Recursive | Cross-sentence consistency, anaphora |

Promotion requires sustained performance (detection rate above threshold for 3 consecutive sessions) along with a false positive rate below 20% and at least 40% deep justifications.

---

## 6. Gamification & Badges

The platform includes a gamification layer to sustain student motivation through badges and experience points (XP).

### 6.1 Badge System

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

### 6.2 XP System

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

### 6.3 UI Integration

- **Student app**: Badge collection display with visual hierarchy, progress bars toward next tiers, and XP history
- **Teacher app**: Badge analytics tab with class-wide heatmap showing badge distribution across students, and a visibility toggle

---

## 7. Backend Services

### 7.1 FastAPI Application

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

#### Key Endpoints

```
POST /api/auth/login              → {token, student_id, display_name, level, consent_status}
GET  /api/assignments/{student_id} → list[ExerciseAssignment]
GET  /api/exercises/{exercise_id}  → Exercise with item_ids
GET  /api/items/{item_id}          → AssessmentItem (filtered by student's level)
POST /api/responses/submit         → {response_id}
POST /api/responses/{id}/justifications → confirmation
GET  /api/responses/{id}/feedback  → {summary, errors with explanations}
GET  /api/responses/{id}/score     → ScoringResult
GET  /api/analytics/student/{id}   → StudentProfile with blind spots
GET  /api/badges/{student_id}      → StudentBadges with earned badges & XP
```

### 7.2 Authentication

**Module**: `src/tompe/services/auth.py`

1. Student submits credentials via Gradio → `POST /api/auth/login`
2. Backend verifies bcrypt password hash
3. Generates `secrets.token_urlsafe()` bearer token
4. Token stored in `data/sessions/tokens/{token}.json` with 7-day expiry
5. Subsequent requests include `Authorization: Bearer {token}` header
6. FastAPI dependency `verify_token()` validates on each request

Teacher access (Streamlit) runs on the same machine with direct service imports — no authentication layer in v1.

### 7.3 Data Store

**Module**: `src/tompe/services/datastore.py`

A generic `JsonStore` class provides CRUD operations over JSON files:

```python
class JsonStore:
    def save(obj: BaseModel) → str          # Write entity to data/{dir}/{id}.json
    def get(obj_id, model_class) → T        # Read and validate via Pydantic
    def list_all(model_class, filter_fn)     # List with optional filter
    def update(obj_id, model_class, patch)   # Partial update
    def delete(obj_id) → bool               # Remove file
```

**Pre-configured stores**:

| Store | Directory | ID Field |
|-------|-----------|----------|
| `students_store` | `data/students/` | `student_id` |
| `classes_store` | `data/classes/` | `class_id` |
| `exercises_store` | `data/exercises/` | `exercise_id` |
| `items_store` | `data/items/` | `item_id` |
| `responses_store` | `data/sessions/responses/` | `response_id` |
| `assignments_store` | `data/assignments/` | `assignment_id` |
| `feedback_store` | `data/feedback/` | — |
| `tokens_store` | `data/sessions/tokens/` | — |
| `consent_store` | `data/consent/` | — |
| `badges_store` | `data/badges/` | `student_id` |

### 7.4 LLM Client

**Module**: `src/tompe/pipeline/llm_client.py`

Unified async client supporting four providers:

| Provider | Endpoint | Models |
|----------|----------|--------|
| OpenAI | `/v1/chat/completions` | gpt-4.1, gpt-5-nano, o-series |
| Anthropic | Native Messages API | claude-sonnet-4-6 |
| Ollama | `/api/chat` or OpenAI-compatible | llama3, mistral, etc. |
| Together AI | OpenAI-compatible | deepseek-v3, open-source models |

Key methods:
- `complete_text(system, user, temperature)` — Plain text completion
- `complete_json(system, user, schema, temperature)` — Structured JSON output
- `stream_text(system, user)` — Streaming async iterator

Factory functions `make_client(provider, model)` and `make_client_from_config(config)` read API keys from environment variables.

---

## 8. Scoring, Feedback & Analytics

### 8.1 Scoring

**Module**: `src/tompe/services/scoring.py`

**Span matching** uses character-level Intersection over Union (IoU):

```
IoU = |intersection| / |union|
Match if IoU ≥ 0.5 (configurable threshold)
```

Student errors are greedily matched to the closest ground-truth error by IoU. From matches, the system computes:

- **True positives** (TP): Student spans matching ground truth above IoU threshold
- **False positives** (FP): Student spans with no ground-truth match
- **False negatives** (FN): Ground-truth errors the student missed
- **Precision**: TP / (TP + FP)
- **Recall (detection rate)**: TP / (TP + FN)
- **F1**: Harmonic mean of precision and recall

Additional breakdowns by:
- **MQM category**: Accuracy, Fluency, Terminology, Style, Locale
- **ToM level**: 1st-machine, 1st-author, 2nd-reader, recursive

For post-editing mode:
- **HTER** (Human Translation Edit Rate): Edit distance between student's edit and reference, normalized by reference length
- **Unnecessary edits**: Changes to spans that were not errors
- **Edit quality**: Proportion of edits that improve the translation

### 8.2 Feedback (Cognitive Forcing Protocol)

**Module**: `src/tompe/services/feedback.py`

The feedback service implements the cognitive forcing protocol:

1. Student submits identified errors + justifications.
2. System scores the response (scoring service).
3. **Only then** are explanations revealed — the student cannot see correct answers before committing their reasoning.

The feedback payload includes:
- Summary metrics (detected, missed, false positives, precision, recall, F1)
- Per-error detail: student classification vs. ground truth, student's own justification displayed alongside Layer 1/2a/2b explanations
- Missed errors with full explanations to fill knowledge gaps
- False positives with explanation of why the flagged span is actually correct

### 8.3 Analytics & Blind Spot Detection

**Module**: `src/tompe/services/analytics.py`

**Blind spot detection** identifies systematic weaknesses:

```
For each (MQM category × ToM level) combination:
    If detection_rate < 0.5 AND sessions_observed ≥ 3:
        → Blind spot identified
```

Returns: affected category, ToM level, average rate, session count, and example items for targeted practice.

**Student profiles** aggregate:
- Performance time series across sessions
- Skill mastery levels (S1–S7)
- Current progression stage
- Recommended next exercises based on blind spots

---

## 9. Research Infrastructure

The `experiments/` and `study/` directories contain standalone research tooling that validates the platform's theoretical foundations and supports pilot data collection.

### 9.1 ToM Hypothesis Validation

**Directory**: `experiments/tom_validation/`

An 8-step statistical pipeline that validates the core hypothesis: errors requiring higher Theory of Mind levels are harder for human raters to detect.

| Step | Module | Method |
|------|--------|--------|
| 1 | `parse_mqm.py` | Parse WMT-MQM TSV annotations, extract error spans with IoU alignment |
| 2 | `align_errors.py` | Rater-level error alignment with configurable IoU thresholds (standard 0.5, lenient 0.4, strict 0.6) |
| 3 | `assign_tom.py` | Map detected errors to ToM levels (1st-machine, 1st-author, 2nd-reader, recursive) |
| 4 | `descriptive.py` | Descriptive statistics: rater counts, error distributions per category and ToM level |
| 5 | `test_trend.py` | Jonckheere-Terpstra trend test for monotonic ToM-difficulty relationship |
| 6 | `mixed_models.py` | Kruskal-Wallis H-test, Dunn's post-hoc comparisons, ordinal regression, rater-level logistic regression |
| 7 | `sensitivity.py` | Sensitivity analyses: IoU variants, rater exclusion, severity filtering, subset replication |
| 8 | `figures.py` | Generate V1–V3 visualization figures (boxplot, heatmap, rater slopes) |

**R integration**: `r_runner.py` wraps two R scripts for mixed-effects models:

- `clmm_analysis.R` — Cumulative link mixed model (CLMM) for ordinal ToM levels
- `rater_glmm.R` — Generalized linear mixed model (GLMM) for rater random effects

**Orchestration**: `run_all.py` runs the full pipeline end-to-end, writing outputs to `outputs/tom_validation/`.

### 9.2 ECTEL 2026 Experiments

**Directory**: `experiments/ectel/`

Experiments supporting the EC-TEL 2026 submission:

- `exp3b_developmental.py` — Tests the developmental gradient hypothesis (low-ToM skills are mastered before high-ToM skills) using first-mastery analysis, learning curve slopes, phase improvement, and experience-gradient methods
- `visualizations.py` — Generates figures F4–F6: ToM ordering vs. published difficulty scatter plots, convergence analysis, and convergence heatmaps
- `run_all.py` — Orchestration script including exp3b

**Report generation**: `scripts/generate_ectel_report.py` produces detailed Markdown reports from experiment results, with support for source-exclusion sensitivity runs (e.g., excluding Temnikova 2010).

### 9.3 Wasserstein Distance Visualizations

**Module**: `experiments/wasserstein/dashboard_visualizations.py`

Generates teacher-facing dashboard prototypes using the MasteryGap metric (Wasserstein / optimal-transport distance between a student's current skill distribution and a target mastery profile):

- **Option A** — Individual student skill profiles with optimal-transport arrows showing current vs. target mastery
- **Option B** — Class-level trajectory sparklines with alert bands for at-risk students
- **Option C** — Class heatmap with student rows, skill columns, and session-by-session color-coded progression

Outputs 9 dashboard prototypes to `outputs/wasserstein/figures/dashboard/` (3 student archetypes × 3 visualization options).

### 9.4 ECTEL 2026 Pilot Study App

**Directory**: `study/`

A standalone Gradio + Streamlit application for participant data collection, independent of the main training platform:

- `study_app.py` — Gradio interface with a linear flow: Consent → 20 segment evaluations → Post-task questionnaire → Thank you
- `study_manager.py` — Streamlit management dashboard with Setup, Monitor, and Export tabs
- `study_config.json` — Configuration with consent forms and post-task questionnaires
- `segments/ectel2026_pilot.json` — 20 curated segments across three conditions (L1 surface errors, L2 meaning errors with fluency-form variants, L3 deeper ToM errors)

**Design features**: Form randomization (A/B) for counterbalancing fluency effects, segment ordering constraints (first segment always L1 warm-up, max 2 consecutive from same condition), anonymous participant ID generation, per-participant JSON export.

---

## 10. Configuration & Deployment

### 10.1 Environment Variables (`.env`)

```bash
ANTHROPIC_API_KEY=sk-ant-...      # Claude for error injection & explanations
OPENAI_API_KEY=sk-proj-...        # GPT-4.1 for MT generation & injection
GOOGLE_TRANSLATE_API_KEY=...      # Google Translate API v2
DEEPL_AUTH_KEY=...                # DeepL translation API
OLLAMA_BASE_URL=https://...       # Ollama server URL
OLLAMA_API_KEY=...                # Ollama authentication
TOGETHER_API_KEY=...              # Together AI for open-source models
HF_TOKEN=...                      # Hugging Face (xCOMET model access)
```

### 10.2 Global Settings (`config/settings.yaml`)

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

### 10.3 MT Backend Configuration (`config/mt_backends.yaml`)

Each MT system is independently toggleable with its own model, prompt strategy, and provider settings. The `injection_llm` section configures which model performs error injection (default: GPT-4.1, temperature 0.3).

### 10.4 Running the Platform

```bash
# Start the FastAPI backend (port 8000)
uv run tompe-api

# Start the student Gradio UI (port 7860)
uv run tompe-student

# Start the teacher Streamlit UI (port 8501)
streamlit run src/tompe/interfaces/teacher_app.py
```

---

## 11. End-to-End Architecture Diagram

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
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  MT Systems: Google Translate │ DeepL                        │     │
│  └──────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      DATA LAYER (JSON Files)                         │
│                                                                       │
│  data/corpora/     ← Parallel text (JSONL)                           │
│  data/codebook/    ← Error taxonomy & examples                       │
│  data/items/       ← Assessment items (draft/reviewed/published)     │
│  data/students/    ← Student accounts                                │
│  data/classes/     ← Class groups                                    │
│  data/exercises/   ← Exercise definitions                            │
│  data/assignments/ ← Student-exercise assignments                    │
│  data/sessions/    ← Responses & auth tokens                         │
│  data/feedback/    ← Generated feedback                              │
│  data/consent/     ← Research consent records                        │
│  data/analytics/   ← Performance metrics                             │
│  data/badges/      ← Earned badges & XP records                      │
└───────────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════╗
║                      FASTAPI BACKEND (port 8000)                       ║
║                                                                        ║
║  /api/auth/          ← Login, logout, token management                 ║
║  /api/consent/       ← Research consent CRUD                           ║
║  /api/assignments/   ← Student exercise assignments                    ║
║  /api/exercises/     ← Exercise retrieval                              ║
║  /api/items/         ← Assessment item delivery                        ║
║  /api/responses/     ← Submit annotations, justifications, feedback    ║
║  /api/analytics/     ← Performance metrics                             ║
║  /api/badges/        ← Badge collection & XP                           ║
║  /api/classes/       ← Admin class management                          ║
║  /api/students/      ← Admin student management                        ║
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
║                     RESEARCH INFRASTRUCTURE                            ║
║                                                                        ║
║  experiments/tom_validation/   ← ToM hypothesis validation (R+Python)  ║
║  experiments/ectel/            ← ECTEL 2026 experiments (3a, 3b)       ║
║  experiments/wasserstein/      ← MasteryGap dashboard prototypes       ║
║  study/                        ← Standalone pilot study app (Gradio)   ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### Data Flow Summary

1. **Teacher ingests** parallel corpora from OPUS into `data/corpora/`.
2. **Pipeline selects** segments, generates MT output, injects controlled errors, validates via QE, generates explanations, and assembles items.
3. **Teacher reviews** draft items, approves/edits, publishes, and builds exercises.
4. **Teacher assigns** exercises to classes or individual students.
5. **Student logs in**, selects an exercise, and enters the three-phase workflow.
6. **Phase 1**: Student identifies errors in the presented MT text (with scaffolding appropriate to their level).
7. **Phase 2**: Student justifies each detection before seeing answers (cognitive forcing).
8. **Phase 3**: System scores the response, reveals explanations, awards badges and XP, and stores results.
9. **Analytics** track performance over time, detect blind spots, and recommend progression.
10. **Gamification** awards progression, specialisation, and behaviour badges; XP scales with ToM level and scaffolding independence.
11. **Teacher monitors** class and individual performance via analytics dashboards and badge heatmaps, adjusting scaffolding levels as students demonstrate mastery.
