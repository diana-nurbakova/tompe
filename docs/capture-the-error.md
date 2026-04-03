# Capture the Error — Gamified Error Detection in ToM-PE

## Overview

**Capture the Error** is the core gamified activity in ToM-PE (Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training). Students receive machine-translated text and must identify, classify, and justify translation errors. The activity is structured as a three-phase workflow — **Annotate → Justify → Feedback** — with progressive scaffolding levels (L0–L3) that systematically remove support as students develop expertise.

The gamification lies in the scoring mechanics, immediate feedback loops, progressive difficulty, and the cognitive challenge of "capturing" errors before the system reveals them. The platform tracks detection rates, false positives, and justification quality to create a skill-building progression.

---

## Pedagogical Foundation

The activity is grounded in two theoretical frameworks:

- **Theory of Mind (ToM)**: Students must reason about what the MT system "understood," what the author intended, and how a reader would interpret the translation. This multi-perspective reasoning maps to ToM levels (`1st_machine`, `1st_author`, `2nd_reader`, `recursive`).
- **Cognitive Constructivist Learning (CCL)**: The four scaffolding levels follow a release-of-responsibility model — from fully guided (Navigator) to fully independent (Expert).

### Error Taxonomy

Errors are classified using an MQM-derived 10-tag system:

| Tag | MQM Dimension | Skill Level |
|-----|---------------|-------------|
| `MISTRANSLATION` | Accuracy | S3 |
| `OMISSION` | Accuracy | S4 |
| `ADDITION` | Accuracy | S4 |
| `UNTRANSLATED` | Accuracy | S4 |
| `GRAMMAR` | Fluency | S2 |
| `SPELLING` | Fluency | S1 |
| `PUNCTUATION` | Fluency | S1 |
| `TERMINOLOGY` | Terminology | S5 |
| `STYLE` | Style | S6 |
| `LOCALE` | Locale | S6 |

Each error also carries a **severity** (`minor`, `major`, `critical`) and a **ToM level** indicating the depth of perspective-taking required to detect it.

---

## Teacher Side

### 1. Preparing Items for Error Capture

Teachers build the content that students will engage with. The pipeline is:

**Browse Corpus → Generate Translations → Review Queue → Publish Items → Build Exercise → Assign to Class**

#### 1.1 Corpus Selection (Browse Corpus)

Teachers select source segments from parallel corpora (Europarl, DGT-TM, EurLex, UNPC) using filters:

- **Domain**: parliamentary, legal, institutional
- **Direction**: FR→EN or EN→FR
- **Register**: formal, semi-formal
- **Token length**: 5–100 tokens
- **Text search**: keyword filtering in source or reference

Selected segments become candidates for MT translation and error injection.

#### 1.2 Translation Generation

Teachers choose MT systems (Google Translate, DeepL, LLM-based) and configure translation prompts (EU Formal, General, Legal presets). The system generates translations through two pathways:

- **Controlled pathway**: Errors are programmatically injected into human reference translations. Each `InjectedError` includes the original text, the injected error text, span offsets, classification metadata, and multi-layer explanations.
- **Authentic pathway**: Real MT errors are detected via quality estimation (xCOMET, GEMBA-MQM) and stored as `DetectedError` objects with confidence scores.

#### 1.3 Review Queue

Teachers review generated items before they reach students. Each item displays:

- Source text and translation (with errors) side by side
- Reference translation (hidden from students)
- **Error manifest**: expandable cards for each error showing:
  - Category (selectable from 10 PrimaryTag options)
  - Error type (e.g., `false_cognate`, `word_sense`)
  - Severity level
  - Error text vs. correct text
  - **Layer 1 — Contrastive explanation**: MT interpretation, actual meaning
  - **Layer 2a — Conceptual explanation**: error mechanism (why MT systems make this error)
- Teacher notes field
- Action buttons: **Approve & Publish**, **Save as Reviewed**, **Reject**

Teachers can modify error classifications, adjust explanations, and add pedagogical notes before publishing.

#### 1.4 Exercise Builder

Teachers compose exercises from published items and configure the gamification parameters:

| Setting | Options | Purpose |
|---------|---------|---------|
| **Name** | Free text | Descriptive title for students |
| **Mode** | `evaluation`, `postediting`, `both` | Whether students detect errors, fix them, or both |
| **Scaffolding Level** | `navigator` (L0), `guided` (L1), `independent` (L2), `expert` (L3) | Controls how much support is provided |
| **Justification type** | `free_text`, `structured`, `both` | How students explain their reasoning |
| **Item ordering** | `manual`, `difficulty`, `random` | Sequence strategy |
| **Domain / Direction** | Free text | Metadata labels |
| **False annotation ratio** (L0 only) | 0.0–0.5 | Fraction of pre-annotations that are deliberately incorrect (forces critical evaluation) |
| **Clean segment ratio** (L3 only) | 0.0–0.4 | Fraction of segments with no errors (tests false-positive discipline) |

#### 1.5 Class Management & Assignment

- Create class groups (e.g., "MT Post-Editing 2026 — Group A")
- Add student accounts individually or via CSV import (username, display_name, password)
- Set default scaffolding levels per class
- Override individual student levels based on performance
- Assign exercises to entire classes (auto-creates `ExerciseAssignment` for each student)
- Track research consent status (Tier 1: interaction data, Tier 2: publication excerpts)

#### 1.6 Analytics Dashboard (Teacher Monitoring)

Teachers monitor Capture the Error performance through:

- **Class Overview**: detection rate by MQM category, skill radar charts, over-editing tendency
- **Individual Students**: per-student performance vs. class average, blind spot alerts
- **ToM Blind Spot Analysis**: MQM × ToM heatmap highlighting systematic weaknesses (e.g., a student consistently misses `2nd_reader` level mistranslations)

---

## Student Side

### 1. Login & Consent

Students log in with credentials provided by their teacher. On first login, they are shown a research consent form with two optional tiers:

- **Tier 1**: Consent for interaction/annotation data to be used in research (anonymized)
- **Tier 2**: Consent for short anonymized justification excerpts in publications

Declining does not affect grades or platform access.

### 2. Exercise Selection

After login, students see a card-based list of assigned exercises. Each card shows:

- Exercise name
- Level label (L0 Navigator / L1 Guided / L2 Independent / L3 Expert)
- Mode (Evaluation / Post-Editing / Both)
- Number of items
- Domain and direction metadata
- Status: **Not started** / **In progress (X/Y)** / **Completed — Score: Z%**
- Action button: **Start Exercise** / **Continue** / **Review Feedback**

### 3. The Three-Phase Workflow

Each item within an exercise follows a strict three-phase structure. A visual phase indicator at the top tracks progress: **1 Annotate → 2 Justify → 3 Feedback**.

---

#### Phase 1: Annotate (Error Capture)

This is the core "game" — students must find and classify errors in the MT output.

**What students see:**

- **Source text** (French or English) displayed in a styled reading panel
- **Translation text** rendered in an interactive span selector with click-drag functionality
- **Error Types Guide** (collapsible accordion) with definitions and examples for all 8 student-facing categories
- **MQM category pill buttons** for classification
- **Subtype dropdown** (appears after category selection, e.g., `false_cognate`, `word_sense` for MISTRANSLATION)
- **Severity selector** (minor / major / critical)

**How error capture works:**

1. **Select**: Student clicks and drags over suspicious text in the translation. The span selector uses inline JavaScript to compute character offsets and communicates the selection to the backend via a hidden textbox.
2. **Classify**: Student clicks an MQM category pill button (color-coded dots: Mistranslation, Omission, Addition, Grammar, Terminology, Style, Locale, Untranslated), then selects a subtype.
3. **Set severity**: Student chooses minor, major, or critical.
4. **Add**: Student clicks "Add Error" to register the annotation. The text re-renders with the error span highlighted in the category's color, and an annotation chip appears below showing: colored dot + category label + span text excerpt + severity + remove button.
5. **Repeat**: Student continues selecting and classifying until satisfied.
6. **Proceed**: Student clicks "Proceed to Justification →" to advance to Phase 2.

**Scaffolding variations by level:**

| Feature | L0 Navigator | L1 Guided | L2 Independent | L3 Expert |
|---------|-------------|-----------|----------------|-----------|
| Error locations shown | Yes (full pre-annotations with MQM labels, severity badges) | Approximate regions (yellow highlights, ±10 chars) | No | No |
| Student must select spans | No (verify/dispute pre-annotations) | Yes (within highlighted regions) | Yes (anywhere) | Yes (anywhere) |
| Category labels visible | Yes (badges on spans) | Hint text only | No | No |
| ToM perspective hints | Yes ("Think about what the MT system understood") | No | No | No |
| Guiding questions | Yes ("Does this phrase match the source meaning?") | No | No | No |
| Clean segments present | No | No | Optional | Yes (20–40% are error-free) |
| False annotations present | Yes (25–50% are deliberately wrong) | No | No | No |
| Task description | "Verify each annotation: confirm correct ones, dispute incorrect ones" | "Within each region, select the exact error span" | "Select any text you believe contains an error" | "Some segments may be error-free — marking a correct segment counts against your score" |

**Visual rendering details:**

- Highlighted spans use category-specific background colors from `TAG_COLORS`
- L0 Navigator: full badges appear as superscript labels (e.g., "Accuracy > Mistranslation · Major")
- L1 Guided: yellow highlight regions (`#FEF9C3`) mark approximate error locations
- L2/L3: no pre-existing highlights; student annotations appear as they are added
- Annotation chips below the text provide a summary of all marked errors with remove buttons

---

#### Phase 2: Justify (Cognitive Forcing)

Before seeing any feedback, students must explain their reasoning. This "cognitive forcing" step prevents superficial pattern-matching and promotes genuine Theory of Mind engagement.

**Free-text mode:**

A single textbox with the prompt:
> "What did the MT system misunderstand? What was the author's intent? How would a reader misinterpret this?"

**Structured ToM mode:**

Three separate textboxes:
1. **"What did the MT system misunderstand?"** — Placeholder: "The MT system likely interpreted..."
2. **"What was the author's actual intent?"** — Placeholder: "The author meant..."
3. **"How would a reader misinterpret this?"** — Placeholder: "A reader would think..."

The teacher configures which mode (`free_text`, `structured`, or `both`) appears per exercise.

After writing their justification, students click "Submit & See Feedback" to advance to Phase 3.

---

#### Phase 3: Feedback (Score & Learn)

The system scores the student's annotations against the ground-truth error manifest and presents detailed feedback.

**Summary bar:**

| Metric | Description |
|--------|-------------|
| **Detected** | X/Y errors correctly identified |
| **Missed** | Errors present but not found |
| **False positives** | Spans marked as errors that aren't |
| **Score** | Percentage score |

**Per-error feedback cards:**

Each card shows:
- Status icon: green checkmark (Found) or red X (Missed)
- Error category with color-coded badge
- Severity label
- The error span text and the correct text (with arrow showing correction)

**Justification review:**
- Student's own reasoning is displayed in a green-bordered box ("Your reasoning:")
  - Free-text: shown as-is
  - Structured: displayed as labeled fields (MT misunderstanding / Author intent / Reader impact)

**Multi-layer explanations (progressive disclosure):**

1. **Layer 1 — Contrastive explanation** (always shown after submission):
   - *MT interpretation*: "The MT system likely interpreted X as..."
   - *Actual meaning*: "The source actually means..."
   - *Reader impact*: "A target reader would understand this as..."
   - *Correction rationale*: "The correct translation is Y because..."

2. **Layer 2a — How It Works** (collapsible `<details>` element):
   - Popular science explanation of why MT systems make this type of error
   - Pattern generalization: "You can expect similar errors when you see..."

3. **Layer 2b — Under the Hood** (collapsible, optional):
   - Technical NLP explanation with proper terminology
   - Key concepts (e.g., "BPE splits", "shared subword vocabularies")
   - Academic references

**False positive cards:** shown in a yellow-bordered box indicating the span does not contain an error.

After reviewing feedback, students click "Next Item →" to advance. When all items are completed, the exercise is marked as complete with an overall score.

---

### 4. Post-Editing Mode (Alternative to Evaluation)

When the exercise mode is set to `postediting`, Phase 1 changes:

- Instead of selecting and classifying error spans, students **edit the translation directly** in a text area
- The system detects changes (insertions, deletions, modifications) and maps them to the error manifest
- Students then justify significant edits in Phase 2
- Phase 3 feedback compares their edits against expected corrections

When mode is `both`, students first annotate errors (evaluation), then edit the translation (post-editing).

### 5. Progress Tracking

The **My Progress** tab shows:
- Completed exercises and scores
- Performance trends over time
- Skill development across MQM categories and ToM levels

---

## Scoring Mechanics

| Component | Scoring Rule |
|-----------|-------------|
| **True positive (correct detection)** | +1 point per correctly identified error span |
| **Category match** | Bonus for correct MQM category classification |
| **Severity match** | Bonus for correct severity assignment |
| **False positive** | Penalty for marking error-free text as erroneous |
| **Missed error** | No points (counts toward "missed" tally) |
| **Justification quality** | Qualitative assessment (displayed but may factor into progression decisions) |

The final score is expressed as a percentage: `detected / total_errors * 100`, adjusted for false positives.

---

## Data Flow Summary

```
Teacher                                  Student
───────                                  ───────
Corpus Browse                            Login + Consent
    ↓                                        ↓
Select Segments                          Exercise List
    ↓                                        ↓
Generate Translations                    Open Exercise
    ↓                                        ↓
Review Queue                             Phase 1: Annotate
  ├─ Edit errors                           ├─ Select span (click-drag)
  ├─ Edit explanations                     ├─ Classify (MQM category + subtype)
  └─ Approve / Reject                     ├─ Set severity
    ↓                                      └─ Add annotation
Published Items                              ↓
    ↓                                    Phase 2: Justify
Exercise Builder                           ├─ Free-text reasoning
  ├─ Select items                          └─ Structured ToM prompts
  ├─ Configure level/mode                      ↓
  └─ Set scaffolding params             Phase 3: Feedback
    ↓                                      ├─ Score summary
Assign to Class                            ├─ Per-error cards
    ↓                                      ├─ Layer 1: Contrastive
Analytics Dashboard                        ├─ Layer 2a: How It Works
  ├─ Class overview                        └─ Layer 2b: Under the Hood
  ├─ Individual tracking                       ↓
  └─ ToM blind spot heatmap             Next Item → Exercise Complete
```

---

## Technical Architecture

| Component | Technology | File |
|-----------|-----------|------|
| Teacher dashboard | Streamlit | `src/tompe/interfaces/teacher_app.py` |
| Student interface | Gradio | `src/tompe/interfaces/student_app.py` |
| Span selector widget | HTML/JS + Gradio | `src/tompe/interfaces/components/span_selector.py` |
| Error models | Pydantic | `src/tompe/schemas/error.py` |
| Annotation models | Pydantic | `src/tompe/schemas/annotation.py` |
| Assessment items | Pydantic | `src/tompe/schemas/item.py` |
| Session/exercise models | Pydantic | `src/tompe/schemas/session.py` |
| Enums (tags, levels, skills) | Python Enum | `src/tompe/schemas/enums.py` |
| Color scheme | Python dict | `src/tompe/interfaces/components/colors.py` |
| API client | HTTP client | `src/tompe/interfaces/api_client.py` |
| Backend API | FastAPI | `src/tompe/services/api.py` |
