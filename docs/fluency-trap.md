# Fluency Trap — Gamified Error Detection in ToM-PE

## Overview

**Fluency Trap** is the core gamified activity in ToM-PE (Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training). Students receive machine-translated text and must identify, classify, and justify translation errors. The activity is structured as a three-phase workflow — **Annotate → Justify → Feedback** — with progressive scaffolding levels (L0–L3) that systematically remove support as students develop expertise.

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
| **Justification type** | `per_error_short`, `per_error_structured`, `global_free_text`, `none` | How students explain their reasoning (see Phase 2 details) |
| **Item ordering** | `manual`, `difficulty`, `random` | Sequence strategy |
| **Domain / Direction** | Free text | Metadata labels |
| **False annotation ratio** (L0 only) | 0.0–0.5 | Fraction of pre-annotations that are deliberately incorrect (forces critical evaluation) |
| **Clean segment ratio** (L3 only) | 0.0–0.4 | Fraction of segments with no errors (tests false-positive discipline) |

#### 1.5 Class Management & Assignment

- Create class groups (e.g., "MT Post-Editing 2026 — Group A"). Duplicate class names are rejected (case-insensitive).
- Add student accounts individually or via CSV import (username, display_name, password)
- **Reassign students between classes** via a dropdown in the student table. Changing class auto-assigns the new class's exercises.
- Set default scaffolding levels per class
- Override individual student levels based on performance
- Assign exercises to entire classes (auto-creates `ExerciseAssignment` for each student)
- Track research consent status (Tier 1: interaction data, Tier 2: publication excerpts)

#### 1.6 Analytics Dashboard (Teacher Monitoring)

Teachers monitor Fluency Trap performance through four tabs:

- **Class Overview**: summary metrics (Students, Items Evaluated, Avg Precision/Recall/F1), per-student performance table, and detection breakdown charts. When per-skill (S1–S7) data is available, a skill profile bar chart is shown. Otherwise, side-by-side MQM and ToM detection rate charts display the real scoring breakdowns from `detection_by_mqm` and `detection_by_tom`.
- **Individual Students**: per-student metrics (Items Evaluated, Avg F1, Latest F1), F1 performance over time, and detection breakdowns by MQM category and ToM level. When sufficient per-skill data (3+ of 7 skills observed) exists, a **Wasserstein Transport** visualization replaces the bar charts — showing current skill mastery vs. expert target with optimal transport arrows indicating where mastery needs to flow, the MasteryGap (W₁) distance metric, and a teacher-facing interpretation ("Strong on X. Focus next on Y."). Uses `plot_student_profile_with_transport()` from `experiments/wasserstein/dashboard_visualizations.py` and the M3 weighted graph ground metric.
- **ToM Blind Spot Analysis**: an **MQM × ToM heatmap** built from per-error cross-tabulation (re-matching student responses against ground-truth item errors). Each cell shows detection rate + counts (e.g., "67% (2/3)") with RdYlGn colorscale. Below the heatmap, marginal bar charts show detection rates by MQM category and ToM level, with red bars (< 50%) highlighting systematic blind spots.
- **Data Export**: CSV and JSON export of student response data.

Additional analytics features:

- **Badge Distribution Heatmap**: rows = students, columns = badges, cells coloured by tier. Highlights which specialisation badges are most/least common.
- **Badge Visibility Toggle**: teachers can enable or disable badge display per class (tracking continues internally). Default: enabled.
- **Threshold Override**: teachers can adjust specialisation badge thresholds per class to account for item pool composition. Changes apply prospectively only.

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

Before seeing any feedback, students must explain their reasoning. This "cognitive forcing" step prevents superficial pattern-matching and promotes genuine Theory of Mind engagement. Each justification is stored with its `error_id` for traceability, enabling per-error analysis of reasoning quality against detection accuracy.

The teacher configures the justification mode per exercise. Four modes are available:

**`per_error_short` (default — recommended):**

One textbox per annotated error (up to 8). Each error is shown as a card displaying the span text, MQM category, and severity. The prompt adapts to the error's cognitive demand:

| Error type | Adaptive prompt |
| ---------- | --------------- |
| Surface (spelling, punctuation, grammar) | "What's wrong here?" |
| Meaning / terminology (mistranslation, omission, addition, untranslated, terminology) | "Why is this a problem?" |
| Pragmatic / discourse (style, locale) | "Why is this a problem and how would a reader misinterpret this?" |

This mode balances traceability with student effort — surface errors need only a brief note, while deeper errors prompt more reasoning.

**`per_error_structured` (advanced, stage 4–5):**

Three ToM-guided fields per annotated error:

1. **"What did the MT system misunderstand?"**
2. **"What was the author's actual intent?"**
3. **"How would a reader misinterpret this?"**

Best suited for advanced students who need to practice explicit multi-perspective reasoning.

**`global_free_text` (legacy):**

A single textbox for the entire item with the prompt:
> "What did the MT system misunderstand? What was the author's intent? How would a reader misinterpret this?"

Simpler but provides no per-error traceability.

**`none`:**

Skips the justification phase entirely — students go straight from annotation to feedback. Useful for timed exercises or when the focus is purely on detection speed.

After writing their justification(s), students rate their confidence (1–5 scale) and click "Submit & See Feedback" to advance to Phase 3.

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

### 5. Progress Tracking & Gamification

The **My Progress** tab shows three panels: a summary bar, the Badge Collection, and the Skill Radar.

#### 5.1 Summary Bar

Four metric cards at the top:

| Card | Value |
|------|-------|
| **Exercises** | Total completed |
| **Avg Score** | Mean detection rate (%) |
| **Level** | Current scaffolding level (Navigator / Scout / Analyst / Expert) |
| **XP** | Cumulative experience points |

#### 5.2 Badge System

Badges provide visual recognition of student progress across three axes. They are earned automatically based on tracked performance data. All badges share a circular 64×64 px display format with a dark navy (#1B2838) background.

**Design principles:**

- **Pedagogically grounded** — every badge maps to a measurable learning outcome. No badges reward speed, volume, or streak-based behaviours.
- **Non-competitive** — badges reflect individual mastery, not relative ranking.
- **Progressive disclosure** — earned badges display in full colour; unearned badges appear as greyscale locked silhouettes with criteria visible on hover.

##### Progression Badges (4 badges)

Awarded once per scaffolding level. They are the primary visual indicator of a student's current skill level.

| Badge | Level | Trigger | Icon |
|-------|-------|---------|------|
| **Navigator** | L0 | Complete first exercise at L0 | Compass rose with glowing needle |
| **Scout** | L1 | BKT mastery at L0 (p ≥ 0.98) + teacher approval → L1 unlocked | Binoculars with lens flare |
| **Analyst** | L2 | BKT mastery at L1 + teacher approval → L2 unlocked | Magnifying glass over highlighted text |
| **Expert** | L3 | BKT mastery at L2 + teacher approval → L3 unlocked | Diamond gem radiating light |

##### Specialisation Badges (10 categories × 3 tiers = 30 badges)

Reward demonstrated expertise in detecting specific MQM error categories. Each category has three tiers — Bronze, Silver, Gold — earned by accumulating correct detections at L1 or above (L0 detections are excluded because pre-annotations make the category visible).

| Badge | MQM Tag | Bronze | Silver | Gold |
|-------|---------|--------|--------|------|
| **Accuracy Hunter** | `MISTRANSLATION` | 10 | 25 | 50 |
| **Gap Finder** | `OMISSION` | 10 | 25 | 50 |
| **Surplus Spotter** | `ADDITION` | 8 | 20 | 40 |
| **Code Switcher** | `UNTRANSLATED` | 5 | 15 | 30 |
| **Grammar Guard** | `GRAMMAR` | 10 | 25 | 50 |
| **Sharp Eye** | `SPELLING` | 8 | 20 | 40 |
| **Punctuation Pro** | `PUNCTUATION` | 8 | 20 | 40 |
| **Term Specialist** | `TERMINOLOGY` | 8 | 20 | 40 |
| **Style Sentinel** | `STYLE` | 8 | 20 | 40 |
| **Locale Expert** | `LOCALE` | 5 | 15 | 30 |

A detection counts when: (1) span IoU ≥ 0.5 with ground truth, and (2) correct MQM category at the primary tag level. Severity match is not required. When a higher tier is earned, it replaces the lower one (only the highest tier is displayed).

Tier visual treatment:

| Tier | Border colour | Style |
|------|--------------|-------|
| Bronze | Copper (#B87333) | Matte, 3 px |
| Silver | Steel (#C0C0C0) | Polished, 3 px |
| Gold | Gold (#D4AF37) | Luminous, 3 px with outer glow |

##### Behaviour Badges (3 badges)

Reward specific performance patterns reflecting high-quality cognitive engagement.

| Badge | Trigger | Repeatable |
|-------|---------|------------|
| **False Positive Discipline** | Complete an L3 exercise (≥ 5 items) with zero false positives | No |
| **Clean Sheet** | Score 100 % on a single segment: all errors detected, correct categories, zero false positives | Yes (counter ×N) |
| **Trap Detector** | Correctly dispute ≥ 10 false annotations at L0 | No |

#### 5.3 XP Scoring System

XP accumulates across all exercises and provides a single visible progression metric alongside badges.

**Base XP per action:**

| Action | Base XP |
|--------|---------|
| Correct error detection (span IoU ≥ 0.5) | +10 |
| Correct MQM category match | +5 |
| Correct severity match | +3 |
| False positive | −5 |
| Missed error | 0 |

**Difficulty multipliers** — XP per detection is multiplied by two factors:

*ToM level multiplier* (cognitive difficulty of the error):

| ToM level | Multiplier |
|-----------|-----------|
| L0 surface fluency (`1st_machine`) | ×1.0 |
| L1 source comparison (`1st_author`) | ×1.25 |
| L2 bilingual analysis (`2nd_reader`) | ×1.5 |
| L3 recursive/contextual (`recursive`) | ×2.0 |

*Scaffolding level multiplier* (how much support the student had):

| Scaffolding level | Multiplier |
|-------------------|-----------|
| L0 Navigator | ×0.5 |
| L1 Scout | ×1.0 |
| L2 Analyst | ×1.5 |
| L3 Expert | ×2.0 |

**Formula:** `XP = ceil(base_xp × tom_multiplier × scaffolding_multiplier)`

This ensures detecting the same error independently at a higher scaffolding level earns roughly 3× more XP than at L0 with pre-annotations visible.

#### 5.4 Skill Radar

A heptagonal SVG radar chart displays the student's current BKT mastery probability for each of the seven competency skills (S1–S7) on a 0.0–1.0 scale.

| Axis | Skill | Error types mapped | ToM level |
|------|-------|--------------------|-----------|
| S1 | Surface form | Spelling, Punctuation | L0 |
| S2 | Grammar | Grammar | L0 |
| S3 | Lexical accuracy | Mistranslation | L2 |
| S4 | Completeness | Omission, Addition, Untranslated | L2 |
| S5 | Terminology | Terminology | L2 |
| S6 | Style & register | Style, Locale | L3 |
| S7 | Contextual coherence | Cross-sentence, recursive reasoning | L3 |

A dashed gold circle marks the mastery threshold (0.98). The fill area uses the student's current progression-level accent colour (amber for Navigator, teal for Scout, blue for Analyst, gold for Expert).

#### 5.5 Badge Notification Toasts

When a badge is earned during an exercise, a toast notification appears at the end of Phase 3 (Feedback) for the item that triggered it. The toast shows the badge icon, name, tier (if applicable), and a short description. It also displays the XP earned for that item. Multiple badges earned in a single exercise are shown together. The toast uses a slide-in animation (`badgeFadeIn`) and does not block the workflow.

---

## Scoring Mechanics

| Component | Scoring Rule |
|-----------|-------------|
| **True positive (correct detection)** | +1 point per correctly identified error span (+ XP per formula above) |
| **Category match** | Bonus for correct MQM category classification (+5 base XP) |
| **Severity match** | Bonus for correct severity assignment (+3 base XP) |
| **False positive** | Penalty for marking error-free text as erroneous (−5 base XP) |
| **Missed error** | No points (counts toward "missed" tally, 0 XP) |
| **Justification quality** | Qualitative assessment (displayed but may factor into progression decisions) |

The final score is expressed as a percentage: `detected / total_errors * 100`, adjusted for false positives. XP earned is computed separately using the multiplier formula and accumulates in the student's profile.

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
Exercise Builder                           ├─ Per-error adaptive prompts
  ├─ Select items                          └─ or structured / global / none
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
| Badge & XP models | Pydantic | `src/tompe/schemas/badges.py` |
| Enums (tags, levels, skills) | Python Enum | `src/tompe/schemas/enums.py` |
| Color scheme | Python dict | `src/tompe/interfaces/components/colors.py` |
| API client | HTTP client | `src/tompe/interfaces/api_client.py` |
| Backend API | FastAPI | `src/tompe/services/api.py` |
| Scoring engine | Python | `src/tompe/services/scoring.py` |
| Response/justification models | Pydantic | `src/tompe/schemas/response.py` |
| Scoring result models | Pydantic | `src/tompe/schemas/scoring.py` |
| Badge service | Python | `src/tompe/services/badges.py` |
| Badge definitions | JSON config | `config/badges.json` |
| Badge icon assets | JPG images | `assets/badges/` |
| Wasserstein metrics | Python + POT | `experiments/wasserstein/metrics.py` |
| Wasserstein dashboard viz | Matplotlib | `experiments/wasserstein/dashboard_visualizations.py` |
| Ground metrics (M1–M5) | Python | `experiments/wasserstein/ground_metrics.py` |
| Skill/target config | Python | `experiments/wasserstein/config.py` |
