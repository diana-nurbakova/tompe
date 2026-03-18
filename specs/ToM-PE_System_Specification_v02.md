# ToM-PE: Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training
## System Specification Document — v0.2 (March 2026)

---

## 1. Project Overview

### 1.1 Purpose

ToM-PE is a controlled pedagogical environment for training translation students in both **MT quality evaluation** (identifying and classifying translation errors) and **MT post-editing** (correcting errors efficiently). Inspired by IILAP/IILAP+, the platform generates assessment items with known, categorized errors injected into MT output from EU/UN parallel corpora, scaffolded by a Theory of Mind framework that makes the multi-agent perspective-taking structure of post-editing explicit.

### 1.2 Core Innovation

No existing platform combines:
- Controlled error injection on institutional parallel corpora (EU/UN)
- MQM-based error taxonomy with ToM-informed difficulty scaffolding
- Progressive annotation scaffolding (Navigator → Guided → Independent → Expert)
- Dual-mode assessment (quality evaluation + post-editing)
- Dual-mode comparison exercises (independent evaluation + comparative ranking)
- Bidirectional ToM feedback (system-generated explanations + student-generated justifications)
- Dual explanation layers: error-specific contrastive + MT system behavior models
- Teacher dashboard modeling student blind spots (meta-ToM)
- Both translation directions (primarily EN→FR, with FR→EN available)

### 1.3 Design Principles

| Principle | Source | Implementation |
|-----------|--------|----------------|
| Cognitive forcing before explanation | Buçinca et al. 2021 | Students commit judgment before seeing system explanation |
| Graduated intentionality scaffolding | Dunbar/Dennett | Error exercises ordered by ToM demand |
| Justification before correction | Chi et al. 1994; ICAP | Students explain *why* before editing |
| Contrastive explanation design | Buçinca et al. 2025 | Explanations show "X rather than Y because Z" |
| Error-boundary calibration | Bansal et al. 2019 | Mix of correct segments + errors to combat over-editing |
| Teacher meta-ToM | Shulman PCK | Teacher dashboard surfaces student blind spots by error type |

### 1.4 Target Publication Venues

- **EC-TEL 2026** (April 10 deadline): Theory paper — ToM framework for MT PE pedagogy
- **CIKM 2026** (~mid-June deadline): Demo paper — the platform itself

---

## 2. Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                               │
│  EU/UN Parallel Corpus (FR↔EN)  │  IATE Terminology DB          │
│  Europarl │ DGT-TM │ EUR-Lex │ UNPC                            │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE LAYER                                │
│                                                                 │
│  ┌──────────┐   ┌───────────┐   ┌──────────────┐   ┌────────┐ │
│  │ Segment   │──▶│ MT        │──▶│ Error        │──▶│ Item   │ │
│  │ Selector  │   │ Generator │   │ Injector     │   │ Store  │ │
│  └──────────┘   └───────────┘   └──────────────┘   └────────┘ │
│       │              │                │                  │      │
│  corpus filters  multiple MT     MQM-guided         manifest   │
│  domain/complex  systems         LLM injection      + metadata │
│                                                                 │
│  ┌──────────────┐   ┌────────────────┐                         │
│  │ QE Validator  │   │ Explanation    │                         │
│  │ (xCOMET/GEMBA)│   │ Generator     │                         │
│  └──────────────┘   └────────────────┘                         │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SERVICE LAYER (FastAPI)                        │
│                                                                 │
│  /api/items      — item CRUD + assignment                       │
│  /api/sessions   — student session management                   │
│  /api/responses  — student response submission + scoring        │
│  /api/feedback   — explanation retrieval + justification store   │
│  /api/analytics  — aggregated performance data                  │
│  /api/config     — teacher configuration                        │
└──────────┬─────────────────────────────────┬────────────────────┘
           │                                 │
           ▼                                 ▼
┌─────────────────────┐       ┌──────────────────────────┐
│  STUDENT INTERFACE  │       │   TEACHER INTERFACE      │
│  (Gradio)           │       │   (Streamlit)            │
│                     │       │                          │
│  • Evaluation mode  │       │  • Item generation/      │
│  • Post-editing mode│       │    review pipeline       │
│  • Justification    │       │  • Class management      │
│    prompts          │       │  • Analytics dashboard   │
│  • Feedback display │       │  • ToM blind spot view   │
│  • Progress view    │       │  • Item configuration    │
└─────────────────────┘       └──────────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Backend API | FastAPI (Python) | Async, type-safe, OpenAPI docs |
| Student UI | Gradio | Rapid prototyping, annotation widgets |
| Teacher UI | Streamlit | Dashboard-oriented, data visualization |
| Data storage (v1) | JSON/CSV files | Prototype speed; schema designed for DB migration |
| Data storage (v2) | PostgreSQL + SQLAlchemy | Multi-tenant, relational queries |
| MT backends | Google Translate API, DeepL API, NLLB (HuggingFace), GPT-4.1, Claude, DeepSeek V3 | Dedicated MT + general-purpose LLMs for diverse error profiles |
| Error injection | LLM-based (GPT-4.1 / DeepSeek V3) | Controlled, MQM-categorized injection |
| QE validation | xCOMET-XL, GEMBA-MQM | Ground truth verification |
| Explanation gen. | LLM-based (same as injection) | Contrastive ToM explanations |

### 2.3 Directory Structure (Prototype)

```
mtpe-tom/
├── config/
│   ├── settings.yaml              # Global configuration
│   └── mt_backends.yaml           # MT system credentials/endpoints
├── data/
│   ├── corpora/
│   │   ├── europarl/              # Raw parallel segments
│   │   ├── dgt_tm/
│   │   ├── eurlex/
│   │   └── unpc/
│   ├── terminology/
│   │   └── iate_fr_en.json        # IATE extract for FR-EN
│   ├── items/
│   │   ├── manifests/             # Generated item manifests (JSON)
│   │   └── reviewed/              # Teacher-approved items
│   ├── sessions/
│   │   └── {student_id}/          # Per-student session logs (JSON)
│   └── analytics/
│       └── aggregated/            # Cross-session analytics (CSV)
├── pipeline/
│   ├── segment_selector.py        # Corpus sampling + filtering
│   ├── mt_generator.py            # Multi-system MT generation
│   ├── error_injector.py          # MQM-guided error injection
│   ├── qe_validator.py            # xCOMET/GEMBA validation
│   ├── explanation_generator.py   # ToM-informed explanations
│   └── item_builder.py            # Assembles final items
├── services/
│   ├── api.py                     # FastAPI application
│   ├── scoring.py                 # Response evaluation + MQM scoring
│   ├── feedback.py                # Feedback selection logic
│   ├── analytics.py               # Performance aggregation
│   ├── progression.py             # Difficulty/stage management
│   └── auth.py                    # Simple auth (token-based v1)
├── interfaces/
│   ├── student_app.py             # Gradio student interface
│   └── teacher_app.py             # Streamlit teacher interface
├── schemas/
│   ├── item.py                    # Item data models (Pydantic)
│   ├── session.py                 # Session data models
│   ├── response.py                # Student response models
│   ├── feedback.py                # Feedback models
│   └── analytics.py               # Analytics models
├── tests/
├── scripts/
│   ├── ingest_corpus.py           # Corpus preprocessing
│   ├── ingest_iate.py             # IATE terminology extraction
│   └── generate_items.py          # Batch item generation
└── requirements.txt
```

---

## 3. Data Models

### 3.1 Corpus Segment

```python
class CorpusSegment(BaseModel):
    segment_id: str                          # Unique identifier
    source_text: str                         # Original source (FR or EN)
    reference_translation: str               # Human reference translation
    source_lang: Literal["fr", "en"]
    target_lang: Literal["fr", "en"]
    corpus_origin: Literal["europarl", "dgt_tm", "eurlex", "unpc"]
    domain: str                              # e.g., "legal", "parliamentary", "institutional"
    complexity_score: float                   # Computed: sentence length, terminology density
    terminology_density: float               # IATE term count / total tokens
    register: Literal["formal", "semi-formal", "informal"]
```

### 3.2 MT Output

```python
class MTOutput(BaseModel):
    mt_id: str
    segment_id: str                          # FK to CorpusSegment
    mt_system: Literal["google", "deepl", "nllb", "madlad", "gpt4", "claude", "deepseek"]
    mt_text: str                             # Raw MT output
    system_type: Literal["dedicated_mt", "general_llm"]  # Dedicated MT vs. general-purpose LLM
    generation_timestamp: datetime
    bleu_score: Optional[float]              # Against reference
    comet_score: Optional[float]             # xCOMET score
```

### 3.3 Error Manifest (Core of the Controlled Environment)

```python
class InjectedError(BaseModel):
    error_id: str
    span_start: int                          # Character offset in modified text
    span_end: int
    original_text: str                       # What was there before injection
    injected_text: str                       # What replaced it
    mqm_category: MQMCategory                # Top-level MQM dimension
    mqm_subcategory: str                     # Specific MQM issue type
    severity: Literal["minor", "major", "critical"]
    tom_level: TOMLevel                      # ToM demand for detection
    explanation: ContrastiveExplanation       # Pre-generated explanation

class MQMCategory(str, Enum):
    ACCURACY = "accuracy"
    FLUENCY = "fluency"
    TERMINOLOGY = "terminology"
    STYLE = "style"
    LOCALE = "locale"

class TOMLevel(str, Enum):
    """Maps error detection to Theory of Mind demand"""
    FIRST_ORDER_MACHINE = "1st_machine"      # What did the MT "think"?
    FIRST_ORDER_AUTHOR = "1st_author"        # What did the author intend?
    SECOND_ORDER_READER = "2nd_reader"       # What will the reader infer?
    RECURSIVE_MULTI = "recursive"            # Multi-agent reasoning required

class ContrastiveExplanation(BaseModel):
    """Layer 1: Error-specific ToM-informed contrastive explanation"""
    mt_interpretation: str      # "The MT system likely interpreted X as..."
    actual_meaning: str         # "The source actually means..."
    reader_impact: str          # "A target reader would understand this as..."
    correction_rationale: str   # "The correct translation is Y because..."

class SystemBehaviorExplanation(BaseModel):
    """Layer 2: Educational explanation of WHY MT systems make this type of error.
    Builds the student's mental model of MT (first-order ToM about the machine)."""
    error_mechanism: str        # "NMT systems commonly make this error because..."
    architectural_cause: str    # "This relates to how transformers process / training data distribution..."
    pattern_generalization: str # "You can expect similar errors when you see..."
    mt_system_specific: Optional[str]  # "General-purpose LLMs additionally tend to..."
```

### 3.4 Annotation Scaffolding System

The annotation system implements the CCL Navigator concept adapted for MT post-editing.
Annotations are tied to error manifest entries and progressively fade across scaffolding levels.

```python
class AnnotationLevel(str, Enum):
    """Progressive scaffolding levels — maps to CCL stages"""
    NAVIGATOR = "navigator"        # Level 0: Full annotations visible
    GUIDED = "guided"              # Level 1: Location hints, no labels
    INDEPENDENT = "independent"    # Level 2: No annotations
    EXPERT = "expert"              # Level 3: No annotations + clean spans + multi-system

class ErrorAnnotation(BaseModel):
    """Annotation overlay for a single error — visibility depends on scaffolding level"""
    error_id: str                            # FK to InjectedError
    span_start: int
    span_end: int

    # Level 0 (Navigator): ALL fields visible
    highlight_color: str                     # Visual cue mapped to MQM category
    mqm_label: str                           # "Accuracy > Mistranslation"
    severity_label: str                      # "Major"
    tom_perspective_hint: str                # "Think about what the MT system understood"
    guiding_question: str                    # "Does this phrase match the source meaning?"

    # Level 1 (Guided): Only these fields visible
    region_highlight: bool = True            # Approximate area highlighted (wider span)
    hint_text: Optional[str] = None          # "There may be an accuracy issue here"

    # Level 2+: No annotation fields visible

class AnnotationConfig(BaseModel):
    """Per-exercise annotation configuration set by teacher"""
    level: AnnotationLevel
    show_mqm_labels: bool                    # Level 0 only
    show_severity: bool                      # Level 0 only
    show_tom_hints: bool                     # Level 0 only
    show_guiding_questions: bool             # Level 0 only
    show_region_highlights: bool             # Level 0 + 1
    show_hint_text: bool                     # Level 1 only
    include_clean_spans: bool                # Level 2+, required at Level 3
    include_multi_system: bool               # Level 3 only
```

**MQM Category → Annotation Color Mapping:**

| MQM Category | Color | Hex | Rationale |
|-------------|-------|-----|-----------|
| Accuracy | Red | #E74C3C | Critical meaning errors — highest salience |
| Fluency | Blue | #3498DB | Language form errors — distinct from meaning |
| Terminology | Purple | #9B59B6 | Domain-specific — specialized knowledge |
| Style | Orange | #E67E22 | Subjective/register — softer signal |
| Locale | Gray | #95A5A6 | Convention-based — lowest salience |

**Navigator Level Task Design:**

At Level 0, the student's task is NOT to find errors (they're pre-highlighted) but to:
1. **Verify**: "Do you agree this is an error? Yes/No"
2. **Classify**: "What type of error is this?" (even though label is shown — tests understanding)
3. **Explain**: "Why is this an error? What did the MT misunderstand?"
4. **Suggest**: "What should the correct translation be?"

This scaffolds the ToM reasoning process explicitly before asking students to do detection independently.

### 3.5 Dual Item Pathways

Items can be generated through two complementary pathways:

```python
class ItemPathway(str, Enum):
    CONTROLLED = "controlled"    # Errors injected into human reference
    AUTHENTIC = "authentic"      # Real MT errors detected via QE pipeline

class AuthenticErrorDetection(BaseModel):
    """For authentic pathway: errors found by comparing MT output to reference"""
    detection_method: Literal["xcomet", "gemba_mqm", "human_expert"]
    mt_output: str
    reference: str
    detected_errors: List[DetectedError]
    confidence_score: float

class DetectedError(BaseModel):
    """Error detected in authentic MT output (not injected)"""
    span_start: int
    span_end: int
    mqm_category: MQMCategory
    mqm_subcategory: str
    severity: Literal["minor", "major", "critical"]
    tom_level: TOMLevel
    detection_confidence: float              # QE model confidence
    explanation: ContrastiveExplanation       # Generated post-detection
    system_behavior: SystemBehaviorExplanation # WHY the MT made this error
    human_validated: bool                     # Has an expert confirmed?
```

### 3.6 Assessment Item

```python
class AssessmentItem(BaseModel):
    item_id: str
    segment_id: str                          # FK to CorpusSegment
    source_text: str                         # Source text (always shown)
    source_lang: Literal["fr", "en"]
    target_lang: Literal["fr", "en"]
    presented_text: str                      # MT output WITH injected/detected errors
    reference_translation: str               # Clean human reference (hidden)
    mt_system: str                           # Which MT system generated base
    pathway: ItemPathway                     # Controlled (injected) or Authentic (detected)
    errors: List[Union[InjectedError, DetectedError]]  # Error manifest (ground truth)
    clean_spans: List[Tuple[int, int]]       # Spans with NO errors (for over-editing detection)
    annotations: List[ErrorAnnotation]       # Scaffolding annotations (visibility per config)
    annotation_config: AnnotationConfig      # Scaffolding level for this item
    difficulty_level: int                    # 1-5, derived from ToM demands + scaffolding level
    domain: str
    item_status: Literal["draft", "reviewed", "published", "retired"]
    teacher_notes: Optional[str]             # Teacher annotations from review
    iate_terms: List[IATETerm]               # Relevant terminology for this segment
    explanations_layer1: List[ContrastiveExplanation]       # Per-error explanations
    explanations_layer2: List[SystemBehaviorExplanation]    # Per-error-type MT behavior
    metadata: ItemMetadata

    # For comparison exercises: additional MT outputs for same segment
    comparison_outputs: Optional[List[MTOutput]]  # Other systems' translations
    comparison_type: Optional[ComparisonType]      # Which comparison skill to exercise

class ComparisonType(str, Enum):
    """Two distinct skills exercised through comparison tasks"""
    INDEPENDENT_EVAL = "independent_eval"
    # Student evaluates each MT output separately using full MQM annotation.
    # Trains: analytical per-error detection across systems; granular ToM
    #         ("what did THIS system misunderstand vs. THAT system?").
    # Output: per-system error reports, then cross-system comparison summary.

    COMPARATIVE_RANKING = "comparative_ranking"
    # Student sees all outputs side-by-side and ranks them holistically.
    # Trains: global quality judgment, triage decision (PE vs. retranslate),
    #         system-level ToM ("which system better captured the author's
    #         overall communicative intent for the target audience?").
    # Output: ranked list with justifications + PE-worthiness verdict per system.

class ItemMetadata(BaseModel):
    tom_profile: Dict[TOMLevel, int]         # Count of errors per ToM level
    mqm_profile: Dict[MQMCategory, int]      # Count of errors per MQM category
    estimated_time_minutes: float
    has_clean_segments: bool                  # Whether item includes error-free spans
    scaffolding_level: AnnotationLevel       # Which annotation level
    pathway: ItemPathway                     # Controlled or Authentic
    translation_direction: str               # "en→fr" or "fr→en"
```

### 3.7 Student Response

```python
class StudentResponse(BaseModel):
    response_id: str
    session_id: str
    item_id: str
    student_id: str
    mode: Literal["evaluation", "postediting", "navigator", "comparison"]
    timestamp: datetime
    time_spent_seconds: float

    # Evaluation mode fields
    identified_errors: Optional[List[IdentifiedError]]

    # Post-editing mode fields
    edited_text: Optional[str]

    # Navigator mode fields (Level 0)
    verification_responses: Optional[List[VerificationResponse]]

    # Comparison mode fields — two distinct skills
    comparison_type: Optional[ComparisonType]

    # Skill A: Independent evaluation per system
    per_system_evaluations: Optional[List[PerSystemEvaluation]]

    # Skill B: Comparative ranking
    system_rankings: Optional[List[SystemRanking]]
    pe_worthiness: Optional[Dict[str, PEWorthinessVerdict]]  # Per-system PE decision

    # Justification (both modes) — required before seeing feedback
    # Teacher configures which format per exercise (A/B testing)
    justification_format: Literal["free_text", "structured", "both"]
    justifications: List[Justification]

class IdentifiedError(BaseModel):
    span_start: int
    span_end: int
    student_mqm_category: MQMCategory
    student_severity: Literal["minor", "major", "critical"]
    confidence: Literal["low", "medium", "high"]

class VerificationResponse(BaseModel):
    """Navigator level: student verifies pre-annotated errors"""
    error_id: str                            # Which annotated error
    agrees_is_error: bool                    # "Do you agree this is an error?"
    student_classification: Optional[MQMCategory]  # Student's own classification
    suggested_correction: Optional[str]      # What should it be?

class SystemRanking(BaseModel):
    """Comparison Skill B: student ranks MT outputs holistically"""
    mt_system: str
    rank: int                                # 1 = best
    rationale: str                           # Why this ranking?

class PerSystemEvaluation(BaseModel):
    """Comparison Skill A: student evaluates each system independently"""
    mt_system: str
    identified_errors: List[IdentifiedError]
    overall_quality: Literal["good", "acceptable", "poor"]
    cross_system_note: Optional[str]         # "System A handled X better than B because..."

class PEWorthinessVerdict(BaseModel):
    """Professional triage decision: is this MT output worth post-editing?"""
    verdict: Literal["pe_light", "pe_full", "retranslate"]
    rationale: str                           # Why this decision?
    estimated_effort: Literal["low", "medium", "high"]

class Justification(BaseModel):
    """Student-generated ToM reasoning — supports both formats for A/B testing"""
    error_id: Optional[str]                  # Which error this justifies
    format: Literal["free_text", "structured"]

    # Free-text format
    text: Optional[str]                      # Open-ended explanation

    # Structured format (guided ToM prompts)
    mt_misunderstanding: Optional[str]       # "What did the MT system misunderstand?"
    author_intent: Optional[str]             # "What did the author actually mean?"
    reader_impact: Optional[str]             # "How would a reader misinterpret this?"
    tom_perspective: Optional[TOMLevel]      # Which perspective is most relevant?
```

### 3.8 Scoring Result

```python
class ScoringResult(BaseModel):
    response_id: str
    item_id: str

    # Detection metrics
    true_positives: int                      # Correctly identified errors
    false_positives: int                     # Flagged correct spans (over-editing)
    false_negatives: int                     # Missed errors
    precision: float
    recall: float
    f1: float

    # Per-category breakdown
    detection_by_mqm: Dict[MQMCategory, CategoryScore]
    detection_by_tom: Dict[TOMLevel, CategoryScore]

    # Post-editing metrics (if PE mode)
    hter: Optional[float]                    # Human TER vs reference
    unnecessary_edits: Optional[int]         # Edits to clean spans
    edit_quality: Optional[float]            # How close PE is to reference

    # Justification quality (LLM-assessed)
    justification_scores: List[JustificationScore]

class CategoryScore(BaseModel):
    detected: int
    total: int
    detection_rate: float

class JustificationScore(BaseModel):
    justification_id: str
    tom_perspective_correct: bool            # Did student identify right perspective?
    reasoning_quality: Literal["surface", "partial", "deep"]
```

### 3.9 Student Profile (Cross-Session)

```python
class StudentProfile(BaseModel):
    student_id: str
    display_name: str
    sessions_completed: int
    current_difficulty_level: int

    # Longitudinal performance by MQM category
    mqm_performance: Dict[MQMCategory, PerformanceTimeSeries]

    # Longitudinal performance by ToM level
    tom_performance: Dict[TOMLevel, PerformanceTimeSeries]

    # Blind spot detection (for teacher meta-ToM dashboard)
    blind_spots: List[BlindSpot]

    # Over-editing tendency
    false_positive_rate_history: List[float]

class PerformanceTimeSeries(BaseModel):
    """Rolling detection rate over sessions"""
    session_ids: List[str]
    detection_rates: List[float]
    trend: Literal["improving", "stable", "declining"]

class BlindSpot(BaseModel):
    """Systematic weakness identified across sessions"""
    mqm_category: MQMCategory
    tom_level: TOMLevel
    detection_rate: float                    # Consistently below threshold
    sessions_observed: int
    example_item_ids: List[str]              # Items where this manifested
```

---

## 4. Pipeline Specification

### 4.1 Segment Selection (`segment_selector.py`)

**Input**: Raw parallel corpus files
**Output**: Filtered, scored `CorpusSegment` objects

Selection criteria:
- Sentence length: 10–50 tokens (source side)
- Alignment quality: 1:1 sentence alignment only
- Terminology density: computed via IATE lookup
- Domain tag: derived from corpus origin + document metadata
- Deduplication: remove near-duplicate segments (Jaccard > 0.8)
- Register classification: rule-based from corpus origin (Europarl → semi-formal, EUR-Lex → formal, etc.)

Stratified sampling ensures balanced representation across domains and complexity levels.

### 4.2 MT Generation (`mt_generator.py`)

**Input**: `CorpusSegment`
**Output**: Multiple `MTOutput` objects per segment

For each selected segment, generate translations from all configured MT systems. Store raw outputs with metadata. Compute automatic metrics (BLEU, COMET) against reference.

Teacher can configure which MT systems to include per exercise. Comparison mode presents outputs from 2+ systems side by side.

### 4.3 Error Injection (`error_injector.py`)

**Input**: `CorpusSegment` + `MTOutput` (or reference translation as base)
**Output**: Modified text + `InjectedError` manifest

**Two injection modes:**

1. **Reference-based injection**: Start from the clean human reference, inject controlled errors. Guarantees known ground truth. Preferred for early-stage students.

2. **MT-based augmentation**: Start from real MT output, add/modify errors to ensure coverage of target MQM categories. More ecologically valid but harder to control.

**Injection procedure (reference-based):**

```
For each item:
  1. Teacher selects target error profile:
     - MQM categories to include
     - Severity distribution (e.g., 2 major, 1 minor)
     - ToM levels to target
     - Whether to include clean spans
  2. LLM prompt constructs injection request:
     - Source text + reference translation
     - Target error type + severity
     - Domain context
     - Instruction: "Modify the translation to introduce a [category] error
       of [severity] severity at approximately [location]. The error should
       be the kind a [MT_system] would plausibly produce."
  3. LLM returns modified text + error description
  4. System validates:
     - Error span is correctly identified
     - Unmodified spans remain identical
     - Error is classifiable under target MQM category
  5. xCOMET/GEMBA confirms detectability
  6. Contrastive explanation is generated
```

**MQM → ToM mapping for injection targeting:**

| MQM Category | Subcategory | ToM Level | Example Injection |
|-------------|-------------|-----------|-------------------|
| Accuracy | Mistranslation | 1st_machine | "actuellement" → "actually" (false cognate) |
| Accuracy | Omission | 1st_author | Remove a subordinate clause |
| Accuracy | Addition | 1st_machine | Add information not in source |
| Accuracy | Untranslated | 1st_machine | Leave source phrase untranslated |
| Fluency | Grammar | 1st_machine | Break subject-verb agreement |
| Fluency | Register | 2nd_reader | Swap formal register for informal |
| Terminology | Wrong term | 2nd_reader | Replace IATE term with general synonym |
| Style | Awkward | 2nd_reader | Produce grammatical but unnatural phrasing |
| Locale | Date/number format | 2nd_reader | Use source locale conventions |
| Coherence | Discourse | recursive | Break anaphoric reference chain |

### 4.4 Explanation Generation (`explanation_generator.py`)

**Input**: `InjectedError` or `DetectedError` + source/reference context
**Output**: `ContrastiveExplanation` (Layer 1) + `SystemBehaviorExplanation` (Layer 2)

**Layer 1: Error-specific contrastive explanation** (per error):

Each explanation follows the contrastive template:

> "The MT system likely interpreted **[source phrase]** as **[wrong interpretation]** rather than **[correct interpretation]**, because **[plausible reason: cognate interference / word sense ambiguity / syntactic attachment / ...]**. A target reader would understand the translation as meaning **[wrong reader inference]**, which misrepresents the author's intent to convey **[actual meaning]**."

**Layer 2: System behavior explanation** (per error type):

Educational content that builds the student's mental model of how MT works:

> "**Why MT systems make this type of error:** [Architectural/training explanation]. **Pattern to watch for:** [Generalizable cue]. **System-specific note:** [If LLM vs. dedicated MT behaves differently]."

Example Layer 2 explanations by error type:

| Error Type | System Behavior Explanation |
|------------|----------------------------|
| False cognate | "NMT learns word associations from co-occurrence patterns in training data. French-English cognates that diverge in meaning (faux amis) are systematically problematic because the surface similarity biases the model toward the English cognate." |
| Omission | "NMT encodes source sentences into fixed-size representations. Long sentences or parenthetical clauses can be 'compressed out' during encoding, leading to systematic omission of subordinate information." |
| LLM hallucination | "General-purpose LLMs generate text by predicting plausible continuations. Unlike dedicated MT systems, they may add interpretive content or world knowledge not present in the source — a form of hallucination specific to generation-based translation." |
| Register error | "MT systems trained on mixed-register data do not reliably maintain consistent register throughout a text. EU legal texts require formal register that the system may not preserve if similar phrasing appears in informal training contexts." |

Explanations are pre-generated and stored in the item manifest. They are revealed to the student only AFTER the student has submitted their own justification (cognitive forcing).

### 4.5 Authentic Error Detection (`authentic_detector.py`)

**Input**: `CorpusSegment` + `MTOutput` (real MT, no injection)
**Output**: `AuthenticErrorDetection` with detected errors + generated explanations

For the authentic pathway:
1. Compare real MT output against human reference
2. Run xCOMET-XL → get word-level error spans with severity
3. Run GEMBA-MQM → get MQM-categorized error annotations
4. Cross-validate: keep errors detected by both systems (high confidence)
5. Assign ToM level based on MQM category mapping (same table as injection)
6. Generate Layer 1 + Layer 2 explanations for detected errors
7. Flag for human expert validation before publishing

### 4.6 QE Validation (`qe_validator.py`)

Automated quality gate before items reach the teacher review queue:
- Run xCOMET-XL on the error-injected text → verify score degradation vs. clean reference
- Run GEMBA-MQM → verify at least 80% of injected errors are detected
- Flag items where QE fails to detect injected errors (may indicate errors are too subtle for current difficulty level, or that injection is not realistic)

---

## 5. Student Interface (Gradio)

### 5.1 Session Flow

```
┌────────────────────┐
│  Session Start     │
│  Select exercise   │
│  (assigned by      │
│   teacher or       │
│   adaptive)        │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  ITEM PRESENTATION │
│                    │
│  Source text (EN)   │
│  MT output (FR)    │
│  [IATE glossary]   │
│  [MT system label] │
│  [Annotations if   │
│   Level 0/1]       │
└────────┬───────────┘
         │
         ├──────────────────────────────────────────────────────┐
         │                    │                │                │
         ▼                    ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ MODE:        │  │ MODE:        │  │ MODE:        │  │ MODE:        │
│ NAVIGATOR    │  │ EVALUATION   │  │ POST-EDITING │  │ COMPARISON   │
│ (Level 0)    │  │ (Level 1-3)  │  │ (Level 1-3)  │  │ (Level 3)    │
│              │  │              │  │              │  │              │
│ Errors pre-  │  │ Highlight    │  │ Edit the     │  │ See 2-3 MT   │
│ highlighted  │  │ errors       │  │ text         │  │ outputs      │
│              │  │ Classify     │  │ directly     │  │              │
│ Verify:      │  │ (MQM)        │  │              │  │ Evaluate     │
│ "Agree this  │  │ Set severity │  │              │  │ each OR      │
│  is error?"  │  │ Set confid.  │  │              │  │ Rank them    │
│              │  │              │  │              │  │              │
│ Classify     │  │              │  │              │  │ Recommend:   │
│ Suggest fix  │  │              │  │              │  │ "PE or re-   │
│              │  │              │  │              │  │  translate?" │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                 │
       └─────────────────┴─────────────────┴─────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────┐
│  JUSTIFICATION PROMPT (Cognitive Forcing)         │
│                                                   │
│  Format depends on teacher config:                │
│                                                   │
│  FREE-TEXT:                                       │
│  "Explain your reasoning for each error/edit"     │
│  [Open text input]                                │
│                                                   │
│  STRUCTURED:                                      │
│  "What did the MT system misunderstand?"  [input] │
│  "What did the author actually mean?"     [input] │
│  "How would a reader misinterpret this?"  [input] │
│  "Which perspective matters most?"                │
│  [🔵Machine / 🟢Author / 🟡Reader]               │
│                                                   │
│  BOTH: structured fields + open text              │
└────────────────────┬──────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│  SUBMIT → SCORING → FEEDBACK                      │
│                                                   │
│  Detection results:                               │
│  ✓ Correctly identified (green)                   │
│  ✗ Missed errors (red, revealed)                  │
│  ⚠ False positives (orange)                       │
│                                                   │
│  For each error (revealed after submission):      │
│  ┌──────────────────────────────────────────┐     │
│  │ YOUR JUSTIFICATION:                      │     │
│  │ "[student's text]"                       │     │
│  │                                          │     │
│  │ LAYER 1 — ERROR EXPLANATION:             │     │
│  │ "The MT interpreted X as Y because Z.    │     │
│  │  The author intended... A reader would..." │   │
│  │                                          │     │
│  │ LAYER 2 — WHY MT DOES THIS:             │     │
│  │ "NMT systems commonly make this error    │     │
│  │  because... Watch for this pattern when..." │  │
│  │                                          │     │
│  │ ToM PERSPECTIVE:                         │     │
│  │ 🔵 Machine interpretation                │     │
│  │ 🟢 Author intent                         │     │
│  │ 🟡 Reader inference                      │     │
│  └──────────────────────────────────────────┘     │
│                                                   │
│  Session summary:                                 │
│  Detection rate by MQM category                   │
│  Detection rate by ToM level                      │
│  Over-editing rate                                │
│  Justification quality score                      │
└───────────────────────────────────────────────────┘
```

### 5.2 Student Dashboard (Gradio Tab)

**Progress view** showing:
- Overall detection rate trend (line chart over sessions)
- Per-MQM-category radar chart (Accuracy, Fluency, Terminology, Style, Locale)
- Per-ToM-level bar chart (1st_machine, 1st_author, 2nd_reader, recursive)
- Over-editing tendency (false positive rate trend)
- Recent session history with scores

### 5.3 Key Gradio Components

| View | Component | Purpose |
|------|-----------|---------|
| Source display | `gr.HighlightedText` or `gr.HTML` | Show source text with terminology highlights (IATE) |
| MT output (eval mode) | `gr.HighlightedText` | Student selects spans to mark as errors |
| MT output (PE mode) | `gr.Textbox` (editable) | Student edits directly |
| MQM classification | `gr.Dropdown` + `gr.Radio` | Category + severity per flagged span |
| Confidence | `gr.Radio` | Low / Medium / High per flagged error |
| Justification | `gr.Textbox` (per error) | Free-text explanation |
| Feedback display | `gr.HTML` | Side-by-side student justification vs. system explanation |
| Progress charts | `gr.Plot` (Plotly) | Performance visualizations |
| MT comparison | `gr.Dataframe` or side-by-side `gr.HTML` | Compare outputs from multiple MT systems |

---

## 6. Teacher Interface (Streamlit)

### 6.1 Main Navigation

```
SIDEBAR:
├── 📋 Item Management
│   ├── Generate Items
│   ├── Review Queue
│   └── Published Items
├── 📚 Exercise Builder
│   ├── Create Exercise
│   └── Manage Exercises
├── 👥 Class Management
│   ├── Student Roster
│   └── Assign Exercises
├── 📊 Analytics Dashboard
│   ├── Class Overview
│   ├── Individual Students
│   └── ToM Blind Spot Analysis
└── ⚙️ Configuration
    ├── MT Systems
    ├── Error Profiles
    └── Difficulty Settings
```

### 6.2 Item Generation & Review

**Generate Items page:**
1. Select corpus source(s) and domain filter
2. Set target error profile:
   - MQM categories to include (checkboxes)
   - Severity distribution (sliders)
   - ToM levels to target (checkboxes)
   - Number of items to generate
   - Include clean spans? (toggle)
3. Select MT system(s) for base translation
4. Click "Generate" → pipeline runs → items enter review queue

**Review Queue page:**
- List of draft items with metadata (domain, difficulty, MQM profile, ToM profile)
- For each item, teacher sees:
  - Source text
  - Original reference translation
  - Error-injected version with errors highlighted
  - Error manifest (type, severity, span, ToM level)
  - Pre-generated contrastive explanation
  - QE validation results
- Teacher actions: **Approve** / **Edit** / **Reject** / **Regenerate**
- Teacher can add notes, adjust severity, modify explanations
- Approved items move to "Published" pool

### 6.3 Exercise Builder

An exercise is an ordered collection of items assigned to students:
- Select items from published pool
- Set sequencing: manual order, or auto-sequence by difficulty/ToM level
- Set mode per item or per exercise: navigator, evaluation, post-editing, or student choice
- Set comparison skill type: independent evaluation (Skill A), comparative ranking (Skill B), or both sequentially (evaluate first, then rank — scaffolded comparison)
- Set justification format: free-text, structured, or both (for A/B testing)
- Set justification requirements: required, optional, or disabled per item
- Set annotation level: navigator, guided, independent, expert
- Set comparison mode: single MT system or multi-system (select which systems)
- Assign to students or class

### 6.4 Analytics Dashboard

**Class Overview:**
- Aggregate detection rates by MQM category (stacked bar chart)
- Aggregate detection rates by ToM level (grouped bar chart)
- Over-editing rate distribution (histogram)
- Time-on-task distribution
- Most commonly missed error types (ranked list)

**Individual Student View:**
- Student's performance time series
- MQM radar chart (current vs. class average)
- ToM level performance (current vs. class average)
- Blind spot alerts (systematic weaknesses)
- Recent justification quality scores
- Recommended next exercises (based on weak areas)

**ToM Blind Spot Analysis (Teacher Meta-ToM):**

This is the key view that operationalizes the teacher's ToM about student misconceptions:

```
┌──────────────────────────────────────────────────────────┐
│  ToM BLIND SPOT ANALYSIS                                 │
│                                                          │
│  Class-wide patterns:                                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🔴 1st_machine × Accuracy/Omission:  32% detected │  │
│  │    → Students rarely notice missing content when   │  │
│  │      the MT output reads fluently                  │  │
│  │    → RECOMMENDATION: Increase omission items at    │  │
│  │      current difficulty level                      │  │
│  ├────────────────────────────────────────────────────┤  │
│  │ 🟡 2nd_reader × Fluency/Register:    48% detected │  │
│  │    → Students detect formal↔informal shifts but    │  │
│  │      miss domain-specific register issues          │  │
│  │    → RECOMMENDATION: Add legal register items      │  │
│  ├────────────────────────────────────────────────────┤  │
│  │ 🟢 1st_machine × Accuracy/Mistranslation: 78%     │  │
│  │    → Strong performance on obvious mistranslations │  │
│  │    → RECOMMENDATION: Increase to major severity    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Student-specific blind spots:                           │
│  [Student selector dropdown]                             │
│  → [Individual blind spot report]                        │
│                                                          │
│  Generate targeted exercise from blind spots:            │
│  [Auto-generate exercise targeting class weak areas]     │
└──────────────────────────────────────────────────────────┘
```

This view directly embodies the **dual ToM**: the system models what students systematically miss (student ToM failures about the MT), and presents this to the teacher as actionable pedagogical intelligence (teacher ToM about student blind spots).

---

## 7. Scoring and Feedback Logic

### 7.1 Evaluation Mode Scoring

For each student-identified error span, compute overlap with ground truth error spans using character-level IoU (Intersection over Union):
- IoU ≥ 0.5 → match candidate
- If matched: check MQM category (exact match = full credit; same top-level = partial credit)
- If matched: check severity (exact = full credit; ±1 level = partial credit)
- Unmatched student spans → false positives (over-editing signal)
- Unmatched ground truth errors → false negatives (missed errors)

### 7.2 Post-Editing Mode Scoring

- Compute HTER (Human TER) between student's edited text and reference
- Compute character-level diff between student edit and reference
- Identify unnecessary edits: changes to spans that were NOT in the error manifest
- Identify missed errors: error spans left unmodified by the student
- Quality score combines: error correction rate, unnecessary edit penalty, and fluency preservation

### 7.3 Navigator Mode Scoring

For Level 0 (pre-annotated errors):
- Verification accuracy: % of annotations the student correctly agrees/disagrees with
- Classification accuracy: does the student's own MQM classification match the ground truth?
- Correction quality: how close is the student's suggested correction to the reference?
- Justification quality: scored same as other modes (see 7.5)

### 7.4 Comparison Mode Scoring

**Skill A (Independent Evaluation):**
- Each system's evaluation is scored independently using the same IoU-based method as 7.1
- Cross-system consistency: did the student identify the same error types across systems where they appear?
- Comparative insight quality: free-text cross-system notes assessed for depth

**Skill B (Comparative Ranking):**
- Ranking accuracy: Kendall's τ correlation between student ranking and expert/MQM-derived ranking
- PE-worthiness verdict accuracy: agreement with expert triage decision (light PE / full PE / retranslate)
- Rationale quality: LLM-assessed reasoning depth for ranking justifications

### 7.5 Justification Scoring

LLM-based assessment of student justifications against three criteria:
1. **Perspective identification**: Did the student correctly identify which ToM perspective is relevant?
2. **Reasoning depth**: Surface (restates the error), Partial (identifies likely cause), Deep (articulates full contrastive reasoning)
3. **Accuracy**: Is the student's reasoning factually correct about the error cause?

### 7.6 Feedback Sequencing (Cognitive Forcing Protocol)

```
1. Student sees item
2. Student works on item (evaluation or PE)
3. Student MUST submit justification(s) before proceeding
4. System reveals:
   a. Detection results (what was right/wrong/missed)
   b. Student's own justification (displayed first)
   c. System contrastive explanation (displayed second)
   d. ToM perspective label
   e. Comparison: "You identified the machine interpretation ✓
      but missed the reader impact ✗"
5. Student can optionally revise their response (revision tracked)
```

---

## 8. Progression and Difficulty Management

### 8.1 Difficulty Dimensions

Items are characterized along five orthogonal difficulty axes:

| Axis | Levels | Description |
|------|--------|-------------|
| **Scaffolding level** | Navigator → Guided → Independent → Expert | Annotation support fades progressively |
| Error severity | Critical → Major → Minor | Critical errors are most obvious |
| ToM demand | 1st_machine → 1st_author → 2nd_reader → recursive | Higher-order mentalizing = harder |
| MQM complexity | Fluency → Accuracy → Terminology → Coherence | Surface → meaning → domain → discourse |
| Context complexity | Single sentence → multi-sentence → document-level | More context = more cognitive load |

**Recommended progression path (combining scaffolding + difficulty):**

| Stage | Scaffolding | Error Profile | Translation Dir | Mode |
|-------|-------------|---------------|-----------------|------|
| 1. Orientation | Navigator (Level 0) | Critical severity, 1st_machine ToM, Fluency/Accuracy | EN→FR | Verification + explanation |
| 2. Guided detection | Guided (Level 1) | Major severity, 1st_machine + 1st_author, Accuracy/Fluency | EN→FR | Evaluation |
| 3. Independent eval | Independent (Level 2) | Mixed severity, all ToM levels, all MQM categories | EN→FR | Evaluation + PE |
| 4. Dual mode | Independent (Level 2) | Minor severity, 2nd_reader + recursive, Terminology/Style | Both directions | Evaluation + PE |
| 5a. Expert: Analytical | Expert (Level 3) | All levels + clean spans | Both directions | Independent eval across systems (Skill A) |
| 5b. Expert: Judgment | Expert (Level 3) | All levels + clean spans | Both directions | Comparative ranking + PE triage (Skill B) |

Stages 5a and 5b are parallel tracks, not sequential — both are expert-level skills exercised through different comparison tasks. Teachers can assign either or both.

### 8.2 Progression Model (Teacher-Defined, v1)

For the prototype, progression is teacher-controlled:
- Teacher assigns scaffolding level and difficulty level (1–5) to exercises
- Teacher selects annotation configuration per exercise
- Teacher reviews analytics and manually promotes students between stages
- System provides recommendations based on blind spot analysis but teacher decides
- Teacher can override to keep students at Navigator level longer if needed

### 8.3 Adaptive Progression (v2, future)

Planned for future versions:
- Track per-student detection rates by MQM × ToM × scaffolding level
- Apply mastery threshold (e.g., 80% detection rate sustained over 3 sessions at current level)
- Auto-recommend next scaffolding level transition
- Target exercises to individual blind spots
- Compare justification quality between free-text and structured formats to determine optimal format per student

---

## 9. Multi-Tenancy Preparation

Though v1 is solo-deployment, the schema supports multi-tenancy:

- All data models include `teacher_id` and `class_id` fields (populated with defaults in v1)
- Session data is organized by `student_id` subdirectories
- Item manifests include `created_by` metadata
- Configuration is per-class rather than global
- Authentication layer (v1: simple token; v2: OAuth/institutional SSO)

Migration path: JSON/CSV → PostgreSQL requires only implementing a storage abstraction layer (`StorageBackend` interface) that both file-based and DB-based backends implement.

---

## 10. Evaluation Plan (for CIKM Demo + Future Studies)

### 10.1 Technical Evaluation (for CIKM demo paper)

- Error injection quality: inter-annotator agreement between injected errors and expert MQM annotations
- QE validation rate: % of injected errors detected by xCOMET/GEMBA
- Pipeline throughput: items generated per hour
- Explanation quality: expert rating of contrastive explanations

### 10.2 Pedagogical Evaluation (for future empirical studies)

- **Study 1**: Controlled vs. authentic items — do students learn error detection faster with controlled (injected) items than with authentic MT output?
- **Study 2**: ToM-informed feedback vs. standard feedback — does contrastive explanation + justification prompts improve detection rates over simple correct/incorrect feedback?
- **Study 3**: Blind spot targeting — does the teacher meta-ToM dashboard lead to better-targeted exercises and faster student improvement?
- **Study 4**: Scaffolding fading — does the Navigator → Guided → Independent progression produce better outcomes than starting at Independent? What are optimal transition thresholds?
- **Study 5**: Justification format A/B — does structured ToM-prompted justification lead to deeper reasoning than free-text? Do students internalize the perspective-taking structure over time?
- **Study 6**: Comparison skills — do Skill A (independent evaluation) and Skill B (comparative ranking) develop different competences? Does training in one transfer to the other? Is there an optimal sequencing?
- **Study 7**: Layer 2 explanations — does exposure to system behavior explanations (why MT makes errors) improve students' mental models of MT and reduce automation bias over time?

---

## 11. Implementation Roadmap

| Phase | Timeline | Deliverables |
|-------|----------|--------------|
| **Phase 1: Core Pipeline** | Weeks 1–3 | Segment selector, MT generator, error injector, item builder |
| **Phase 2: Student Interface** | Weeks 3–5 | Gradio app: evaluation mode, PE mode, justification, feedback display |
| **Phase 3: Teacher Interface** | Weeks 5–7 | Streamlit app: item review, exercise builder, basic analytics |
| **Phase 4: Scoring & Analytics** | Weeks 7–9 | Scoring logic, student profiles, ToM blind spot analysis |
| **Phase 5: Integration & Demo** | Weeks 9–10 | End-to-end flow, demo video for CIKM |

---

## 12. Open Design Questions

### Resolved in v0.2

| Question | Decision | Rationale |
|----------|----------|-----------|
| Justification format | Both (A/B test) | Empirical comparison; teacher toggles per exercise |
| Clean segment ratio | 20–30% | Progressive: 0% at Navigator, increasing at higher levels |
| Translation direction | Both, primarily EN→FR | Matches translator training convention (into L1) |
| Error source | Human reference first | Cleaner ground truth; authentic MT errors as second pathway |
| MT systems | Dedicated MT + general-purpose LLMs | Different error profiles (LLMs hallucinate, dedicated MT mistranslates) |
| Comparison exercises | Both independent eval + ranking | Different cognitive processes; teacher selects per exercise |

### Still Open

1. **Navigator → Guided transition criteria**: What metrics determine readiness to move from full annotations to partial? Verification accuracy? Justification quality? Both?

2. **System behavior explanation depth**: How technical should Layer 2 explanations be? ("Transformer attention patterns" vs. "the system processes words one by one and can lose track of earlier meaning") — may need to adapt to student background.

3. **Authentic pathway validation threshold**: What confidence level from xCOMET/GEMBA is sufficient to use an automatically detected error as ground truth without human validation? 80%? 90%?

4. **Comparison exercise scoring**: Two distinct scoring models needed. Skill A (independent eval): scored per-system against error manifests, then cross-system comparison quality assessed. Skill B (ranking): scored against expert rankings? Against aggregate MQM scores? PE-worthiness verdict scored against expert triage decision? Need to define ground truth for both.

5. **LLM-as-translator prompting strategy**: What prompting approach for general-purpose LLMs? Zero-shot "translate this"? With domain context? With glossary? Different prompts produce different error profiles.

6. **Cross-direction comparison**: Can the same source segment be used for both EN→FR and FR→EN exercises? This would enable studying how direction affects error detection, but requires parallel items in both directions.

7. **Justification A/B study design**: How to control for order effects? Randomize format per student, per session, or per item? Need to decide before first deployment.
