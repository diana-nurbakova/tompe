# ToM-PE User Interface Specification
## Student & Teacher Interfaces — v1.0 (March 2026)

**Companion to**: ToM-PE System Specification v0.2, Error Injection & Annotation Spec v1.1
**Scope**: Complete specification of all user-facing interfaces: student annotation/PE interface (Gradio), teacher management interface (Streamlit), authentication, deployment, and inter-interface coordination.

---

## 1. Architecture Overview

### 1.1 Two-Interface Design

| Interface | Technology | Users | Deployment | Purpose |
|---|---|---|---|---|
| **Student App** | Gradio | Translation students | Shareable Gradio link (online) | Annotation, PE, justification, feedback, progress |
| **Teacher App** | Streamlit | Translation instructors | Localhost initially, online later | Corpus management, item generation, review, exercise building, analytics, settings |

**Rationale**: Two separate apps rather than one because (a) students and teachers have fundamentally different workflows, (b) Gradio excels at interactive annotation widgets while Streamlit excels at dashboards and data management, (c) deployment contexts differ — students need a shareable URL, teachers need a management console.

**Communication**: Both apps connect to the same FastAPI backend (`services/api.py`) and shared data store (`data/`). The teacher app writes item manifests, exercises, and configurations; the student app reads them and writes session logs and responses.

### 1.2 Deployment Model

```
┌─────────────────────────────────────────────────────────────────┐
│  TEACHER'S MACHINE (or server)                                  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Teacher App  │  │ FastAPI      │  │ Data Store           │  │
│  │ (Streamlit)  │──│ Backend      │──│ (JSON/CSV → Postgres)│  │
│  │ localhost    │  │ :8000        │  │                      │  │
│  └──────────────┘  └──────┬───────┘  └──────────────────────┘  │
│                           │                                     │
│  ┌──────────────┐         │                                     │
│  │ Student App  │─────────┘                                     │
│  │ (Gradio)     │                                               │
│  │ :7860        │──── Gradio share link ──── students access    │
│  └──────────────┘         online via browser                    │
│                                                                 │
│  ┌──────────────┐                                               │
│  │ MT Services  │  Google Translate API, DeepL API, LLM APIs    │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Gradio share links**: Gradio natively supports `share=True` which creates a temporary public URL (72h). For persistent deployment, the teacher can deploy to Hugging Face Spaces or a university server. The teacher interface includes a **"Launch Student App"** button that starts the Gradio server and displays the shareable link.

**Future**: For production deployment, both apps would run on a shared server (university VM or cloud) with proper domain names and HTTPS.

### 1.3 User-Friendly Launch

Given the audience (translation studies teachers, not developers), the system needs a simple launch mechanism:

**Option A (v1 prototype)**: A single shell script `./launch.sh` that:
1. Starts the FastAPI backend
2. Starts the Streamlit teacher app (opens in browser)
3. Starts the Gradio student app with `share=True`
4. Prints the shareable student link

**Option B (v2)**: A desktop launcher (Electron wrapper or Python GUI) with a "Start ToM-PE" button, status indicators, and the student link displayed prominently.

**Option C (v3 production)**: Docker Compose with all services, deployed to a university server. Teacher accesses via `https://tompe.university.edu/teacher`, students via `https://tompe.university.edu/student`.

---

## 2. Authentication & Identity

### 2.1 Student Authentication

**Method**: Simple username + password (teacher-created accounts).

**Flow**:
1. Teacher creates student accounts via Class Management (bulk import from CSV or one-by-one)
2. Each account has: `student_id`, `username`, `display_name`, `password_hash`, `class_id`, `created_at`
3. Student opens the Gradio link → login screen → enters username/password
4. Session token stored in browser (Gradio state) → all interactions tagged with `student_id`
5. Cross-session persistence: the `student_id` links all session logs, response data, and analytics

**Login screen** (Gradio):
```
┌──────────────────────────────────────┐
│         ToM-PE                       │
│    Translation Quality Training      │
│                                      │
│    Username: [____________]          │
│    Password: [____________]          │
│                                      │
│         [ Log In ]                   │
│                                      │
│    ─────────────────────             │
│    Forgot password? Contact          │
│    your instructor.                  │
└──────────────────────────────────────┘
```

**No self-registration** in v1 — the teacher controls who has access. This prevents unauthorized access and ensures every student is assigned to a class.

### 2.2 Teacher Authentication

**v1**: Single-user mode. The teacher app runs on localhost and is implicitly authenticated.
**v2**: Multi-teacher support with admin accounts + per-teacher credentials.

### 2.3 Data Model

```python
class StudentAccount(BaseModel):
    student_id: str              # UUID
    username: str                # Unique, for login
    display_name: str            # Shown in UI and analytics
    password_hash: str           # bcrypt
    class_id: str                # FK to class
    created_at: datetime
    is_active: bool
    current_level: str           # L0/L1/L2/L3 — teacher-controlled
    allowed_levels: List[str]    # Which levels this student can access

class ClassGroup(BaseModel):
    class_id: str
    class_name: str              # e.g., "MT Post-Editing 2026 — Group A"
    teacher_id: str
    default_levels: List[str]    # Default allowed levels for the class
    created_at: datetime
```

---

## 3. Student Interface — Complete Specification

### 3.1 Global Navigation

```
┌─────────────────────────────────────────────────────────────────┐
│  ToM-PE  │  📝 Exercises  │  📈 My Progress  │  👤 [username] │
└─────────────────────────────────────────────────────────────────┘
```

Two main tabs:
- **Exercises**: The core annotation/PE workflow — lists assigned exercises, allows the student to start/continue them
- **My Progress**: Personal dashboard showing skill development over time

### 3.2 Exercise List View

When the student logs in, they see their assigned exercises:

```
┌─────────────────────────────────────────────────────────────────┐
│  📝 YOUR EXERCISES                                              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Exercise 1: Introduction to Error Detection             │   │
│  │  Level: L0 Navigator  │  Mode: Evaluation                │   │
│  │  Items: 5  │  Domain: Parliamentary  │  EN→FR            │   │
│  │  Status: ● Not started                                   │   │
│  │                                    [ Start Exercise → ]  │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  Exercise 2: Accuracy Errors — Guided Detection          │   │
│  │  Level: L1 Guided  │  Mode: Evaluation                   │   │
│  │  Items: 8  │  Domain: Legal  │  EN→FR                    │   │
│  │  Status: ● In progress (3/8)                             │   │
│  │                                    [ Continue → ]        │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  Exercise 3: Full Evaluation                             │   │
│  │  Level: L2 Independent  │  Mode: Evaluation + PE         │   │
│  │  Items: 10  │  Domain: Mixed  │  Both directions         │   │
│  │  Status: ✓ Completed — Score: 72%                        │   │
│  │                                    [ Review Feedback ]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ℹ️ Exercises are assigned by your instructor. New exercises    │
│     appear here automatically.                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Level access control**: The student only sees exercises at levels the teacher has enabled for them. If a student is at L1, they cannot access L2 exercises even if one were assigned by mistake — the system enforces the teacher's level settings.

### 3.3 Item View — Core Annotation Workflow

The item view adapts to the scaffolding level. All levels share a common layout with level-specific behavior.

#### 3.3.1 Common Layout (All Levels)

```
┌─────────────────────────────────────────────────────────────────┐
│  Exercise: [name]  │  Item 3 of 8  │  Level: L2 Independent    │
│  ◄ Previous  │  Progress: ████████░░  │  Next ►                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📋 TASK DESCRIPTION                                            │
│  [Level-specific instructions — see §3.3.2]                     │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SOURCE TEXT                                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  [Source text in FR or EN]                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  TRANSLATION                                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  [Translation text — interaction depends on level/mode]  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ▸ IATE Glossary (3 terms)           ▸ Error Types Guide        │
│                                                                 │
│  ─── PHASE INDICATOR ────────────────────────────────────────   │
│  ① Annotate  ──→  ② Justify  ──→  ③ Feedback                   │
│                                                                 │
│  [Phase-specific content — see §3.3.3–3.3.5]                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.3.2 Task Descriptions by Level

| Level | Mode | Task Description |
|---|---|---|
| **L0 Navigator** | Verification | "Pre-annotated errors are highlighted below. Your task is to verify each annotation: **confirm** correct ones, **dispute** incorrect ones, and explain your reasoning. ⚠️ Some annotations may be incorrect — do not accept them uncritically." |
| **L1 Guided** | Evaluation | "Approximate error regions are highlighted in yellow. Within each region, **select the exact error span** by clicking and dragging. Then classify the error type, assign a severity, and explain your reasoning." |
| **L2 Independent** | Evaluation | "Read the source text and translation carefully. **Select any text you believe contains an error** by clicking and dragging. Classify each error by type and severity, then explain your reasoning." |
| **L2 Independent** | Post-editing | "Read the source text and translation carefully. **Edit the translation directly** to correct any errors. For each significant edit, explain why the change was needed." |
| **L3 Expert** | Evaluation | "Evaluate this translation independently. Note: some segments may be error-free — marking a correct segment as erroneous counts against your score. Select errors by clicking and dragging." |
| **L3 Expert** | Comparison | "Three translations of the same source are shown. **Rank them by quality** (1 = best, 3 = worst), evaluate each independently, and **identify which (if any) was produced by a human translator**." |

All task descriptions include: "To mark an error, **click and drag** over the problematic text in the translation. A classification panel will appear."

#### 3.3.3 Error Types Guide — Persistent Glossary Panel

A collapsible panel available at all levels. **Open by default at L0**, collapsed at L1+.

```
┌─────────────────────────────────────────────────────────────────┐
│  ▾ ERROR TYPES GUIDE                                            │
│                                                                 │
│  ● Mistranslation                                               │
│    The translation conveys a different meaning than the source.  │
│    Example: FR "sensible" → EN "sensible" (should be            │
│    "sensitive")                                                  │
│    ▸ How It Works: Why MT makes this error                      │
│                                                                 │
│  ● Omission                                                     │
│    Content present in the source is missing from the             │
│    translation.                                                  │
│    Example: "Minister of Health" instead of "Minister of Health  │
│    and Prevention"                                               │
│    ▸ How It Works: Why MT makes this error                      │
│                                                                 │
│  ● Addition                                                     │
│    The translation includes content not present in the source.   │
│                                                                 │
│  ● Grammar                                                      │
│    The translation violates grammatical rules of the target      │
│    language.                                                     │
│                                                                 │
│  ● Terminology                                                  │
│    A domain-specific term is incorrect or inconsistent with      │
│    reference terminology (e.g., IATE).                           │
│                                                                 │
│  ● Style / Register                                             │
│    The translation is grammatical but reads unnaturally or       │
│    uses inappropriate level of formality.                        │
│                                                                 │
│  ● Locale Convention                                            │
│    Formatting (dates, numbers, currency) does not match target   │
│    locale conventions.                                           │
│                                                                 │
│  ● Untranslated                                                 │
│    Source language text left untranslated in the target.          │
└─────────────────────────────────────────────────────────────────┘
```

Each entry shows:
- Color dot matching the annotation color scheme
- One-line definition (from codebook)
- One concrete FR-EN example
- Expandable "How It Works" → Layer 2a conceptual explanation of why MT makes this error

At L0, clicking the "How It Works" expander shows the popular-science explanation. This is the student's first exposure to Layer 2 content.

#### 3.3.4 Phase-Specific Interaction

**Phase ① Annotate** (behavior varies by level):

| Level | Translation Text Behavior | Student Action | Classification UI |
|---|---|---|---|
| L0 | Pre-highlighted errors with color + tag labels + severity badges + ToM icons | Confirm/Dispute each via buttons | Confirm ✓ / Dispute ✗ buttons per annotation |
| L1 | Approximate regions in yellow with hint labels | Click-drag within regions to select exact spans | Color-coded pill buttons (§3.3.6) |
| L2 | Plain text, no highlighting | Click-drag anywhere to select spans | Color-coded pill buttons |
| L3 (eval) | Plain text; 20-30% segments are clean | Click-drag; "No errors in this segment" button available | Color-coded pill buttons + "No errors" option |
| L3 (compare) | Multiple translations shown side by side | Rank (1-2-3 buttons per system) + identify human translation | Ranking interface + human/MT discrimination |
| L2 (PE mode) | Editable text area | Direct text editing | Justification per significant edit |

**L0 false annotations**: 1 false annotation per 3-4 true annotations (configurable by teacher). False annotations vary in type:
- Wrong category (marks a correct translation as an error)
- Wrong severity (minor marked as critical)
- Wrong span (highlights adjacent correct text instead of the actual error)

The student's false annotation detection rate is tracked as an additional L0 competency metric.

**Phase ② Justify** (cognitive forcing — identical across levels):

Blocked until Phase ① is complete. For each error/decision:

**Mode A — Free-text** (single text area):
> "Before seeing the feedback, explain your reasoning:
> What did the MT system misunderstand? What was the author's intent? How would a reader misinterpret this?"

**Mode B — Structured ToM prompts** (three separate fields):
> 🔵 "What did the MT system misunderstand?" [text area]
> 🟢 "What was the author's actual intent?" [text area]
> 🟡 "How would a reader misinterpret this?" [text area]

Teacher configures Mode A or B per exercise. Submit button disabled until at least one justification is non-empty.

**Phase ③ Feedback** (revealed after submission):

Summary statistics bar:
- Detected: X/Y errors found
- Missed: Z errors not found (revealed in red)
- False positives: W correct spans incorrectly flagged
- (L0 only) False annotations disputed: A/B

Per-error feedback cards showing:
1. Detection status (✓ found / ✗ missed)
2. Student's own justification (displayed first)
3. System Layer 1 explanation (contrastive, four ToM fields)
4. Expandable "How It Works" (Layer 2a)
5. Expandable "Under the Hood" (Layer 2b)
6. Skill tag and ToM level indicator

**Label conventions** (student-facing):
- Layer 2a: **"How It Works"**
- Layer 2b: **"Under the Hood"**

#### 3.3.5 Span Selection — Custom Gradio Component

**Interaction pattern** (modeled on Anthea/MQM annotation tools):

1. Student **clicks and drags** over text in the translation area to select a span
2. Selected text is highlighted with a temporary blue selection
3. A **classification panel** slides in below the text area
4. Student classifies using color-coded pill buttons (§3.3.6)
5. Student clicks "Add Error" → the span is permanently highlighted in the category color
6. Student can select additional spans or click "No more errors" / "Proceed to Justification"

**First-session tutorial overlay** (shown once per student):
```
┌─────────────────────────────────────────────────────────────────┐
│  QUICK TUTORIAL (Step 1 of 3)                                   │
│                                                                 │
│  To mark an error, click and drag over the text:                │
│                                                                 │
│  "The Minister of [̲H̲e̲a̲l̲t̲h̲] announced new measures."          │
│                      ↑ drag here                                │
│                                                                 │
│  Try it now: select the underlined word above.                  │
│                                                                 │
│                               [ Next → ]  [ Skip tutorial ]     │
└─────────────────────────────────────────────────────────────────┘
```

Three tutorial steps: (1) select a span, (2) classify it, (3) write a justification. Completed in under 60 seconds.

**Implementation**: Custom Gradio component (`interfaces/components/span_selector.py`) wrapping an HTML/JS text container with:
- `mousedown` / `mouseup` / `mousemove` events for span selection
- Dynamic inline styling for highlights (colored `<span>` elements)
- Callback to Python with `(start_offset, end_offset, selected_text)` on each selection
- Support for multiple non-overlapping highlights with different colors
- "Remove" button (×) on each highlight to delete an annotation

#### 3.3.6 Color-Coded Pill Button Classification

Replaces dropdown menus. All MQM categories visible at once as horizontal pills:

```
┌─────────────────────────────────────────────────────────────────┐
│  Classify: "eventually"                                         │
│                                                                 │
│  [● Mistranslation] [● Omission] [● Addition] [● Grammar]     │
│  [● Terminology] [● Style] [● Locale] [● Untranslated]        │
│                                                                 │
│  Subtype: [false cognate] [word sense] [number] [literal]      │
│           [negation] [ambiguity]                                │
│                                                                 │
│  Severity:  [minor]  [MAJOR]  [critical]                       │
│                                                                 │
│                          [ Add Error ]  [ Cancel ]              │
└─────────────────────────────────────────────────────────────────┘
```

- Each pill has a **colored dot** matching the annotation highlight color
- Clicking a category reveals its subtypes as smaller pills below
- Only one category active at a time; clicking another deselects the first
- Severity buttons work as radio group — exactly one active
- "Add Error" disabled until category is selected

**Grounding**: This pattern is faster than dropdowns (one click vs. click→scroll→select), keeps all options visible for taxonomy learning, and visually maps to the highlight colors in the text [Label Studio MQM configuration uses a similar visible-label approach].

#### 3.3.7 Annotation Color Scheme

Consistent across all levels and interfaces. Colorblind-safe palette (verified against Deuteranopia, Protanopia, Tritanopia simulations):

| Category | Highlight Color | Hex | Color Dot |
|---|---|---|---|
| Mistranslation | Light red | `#FEE2E2` | `#E84855` |
| Omission | Light purple | `#F3E8FF` | `#7B2D8E` |
| Addition | Light orange | `#FFF7ED` | `#F18F01` |
| Grammar | Light blue | `#DBEAFE` | `#2E86AB` |
| Terminology | Light teal | `#CCFBF1` | `#0B7A75` |
| Style/Register | Light green | `#ECFCCB` | `#8DB580` |
| Locale | Light brown | `#FEF3C7` | `#A0522D` |
| Untranslated | Light dark-red | `#FDE8E8` | `#9B2335` |
| Clean (L3) | Light green border | `#D1FAE5` | `#44AF69` |
| Region hint (L1) | Light yellow | `#FEF9C3` | `#D97706` |

### 3.4 Post-Editing Mode

When the exercise mode is PE, the translation text area becomes editable:

```
┌─────────────────────────────────────────────────────────────────┐
│  TRANSLATION — edit directly                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  The Minister of Health| announced new measures to      │   │
│  │  fight against the pandemic. He eventually confirmed    │   │
│  │  that the restrictions would be strengthened.           │   │
│  └─────────────────────────────────────────────────────────┘   │
│  💡 Edit the translation to correct any errors you find.        │
│     Your changes are tracked automatically.                     │
│                                                                 │
│  Changes detected: 2                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Change 1: "Health" → "Health and Prevention"           │   │
│  │  Change 2: "eventually" → "possibly"                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [ Proceed to Justification → ]                                 │
└─────────────────────────────────────────────────────────────────┘
```

- The system computes a **character-level diff** between the original and edited text in real-time
- Each detected change is listed below the text area with before → after
- In Phase ②, the student justifies each significant change (not trivial whitespace edits)
- Scoring: HTER vs. reference, unnecessary edits (changes to correct spans), missed errors (unchanged error spans)

### 3.5 L3 Expert — Comparison View

Multi-system comparison with human-vs-MT discrimination:

```
┌─────────────────────────────────────────────────────────────────┐
│  SOURCE                                                         │
│  Les États membres doivent transposer la directive dans un      │
│  délai de deux ans.                                             │
│                                                                 │
│  ┌─────────────────────────────────────────────┬──────────┐    │
│  │ System A                                    │ Rank: ○1 ○2 ○3│
│  │ "The Member States must transpose the       │          │    │
│  │  directive within a period of two years."   │          │    │
│  ├─────────────────────────────────────────────┼──────────┤    │
│  │ System B                                    │ Rank: ○1 ○2 ○3│
│  │ "Member States shall transpose the          │          │    │
│  │  directive within two years."               │          │    │
│  ├─────────────────────────────────────────────┼──────────┤    │
│  │ System C                                    │ Rank: ○1 ○2 ○3│
│  │ "The member states have to transpose the    │          │    │
│  │  directive in a delay of two years."        │          │    │
│  └─────────────────────────────────────────────┴──────────┘    │
│                                                                 │
│  Which translation was produced by a human?                     │
│  [System A] [System B] [System C] [None / Can't tell]          │
│                                                                 │
│  [ Submit & Reveal → ]                                          │
└─────────────────────────────────────────────────────────────────┘
```

At L3, system labels are generic ("System A/B/C") until feedback phase. After submission, the reveal shows which was human, which MT system produced each, and contrastive feedback on discriminating features.

### 3.6 My Progress — Student Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  📈 MY PROGRESS                                                 │
│                                                                 │
│  ┌──── Overall Detection Rate ────────────────────────────┐    │
│  │  [Line chart: detection rate over sessions]             │    │
│  │  Current: 68%  │  Trend: ↑ improving                   │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──── Skill Radar ──────────┐  ┌──── By Error Type ────┐     │
│  │  [Radar chart: S1-S7      │  │  Mistranslation: 78%   │     │
│  │   detection rates vs.     │  │  Omission: 45%  ⚠️     │     │
│  │   class average]          │  │  Addition: 62%         │     │
│  │                           │  │  Grammar: 85%          │     │
│  │                           │  │  Terminology: 55%      │     │
│  └───────────────────────────┘  │  Style: 41%  ⚠️        │     │
│                                  └───────────────────────┘     │
│                                                                 │
│  ┌──── Recent Sessions ──────────────────────────────────┐     │
│  │  Session 5: Exercise "Guided Detection" — 72%          │     │
│  │  Session 4: Exercise "Navigator Intro" — 88%           │     │
│  │  Session 3: Exercise "Navigator Intro" — 81%           │     │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──── Over-Editing Rate ────────────────────────────────┐     │
│  │  Current: 12% (target: ≤ 20%)  ✓                       │     │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Current level: L1 Guided                                       │
│  ℹ️ Your instructor manages level progression.                  │
└─────────────────────────────────────────────────────────────────┘
```

Charts use Plotly (Gradio's `gr.Plot` component). ⚠️ icons flag skills below threshold.

---

## 4. Teacher Interface — Complete Specification

### 4.1 Global Navigation

```
SIDEBAR:
├── 📂 Corpus & Generation
│   ├── Browse Corpus
│   ├── Upload Corpus
│   └── Generate Translations
├── 📋 Review Queue
│   ├── Pending Review (12)
│   └── Published Items
├── 📚 Exercise Builder
│   ├── Create Exercise
│   └── Manage Exercises
├── 👥 Class Management
│   ├── Student Accounts
│   ├── Level Configuration
│   └── Assign Exercises
├── 📊 Analytics Dashboard
│   ├── Class Overview
│   ├── Individual Students
│   └── ToM Blind Spot Analysis
└── ⚙️ Settings
    ├── API Credentials
    ├── MT Systems
    └── System Configuration
```

### 4.2 Corpus & Generation

#### 4.2.1 Browse Corpus

```
┌─────────────────────────────────────────────────────────────────┐
│  📂 BROWSE CORPUS                                               │
│                                                                 │
│  Source: [Europarl ▾] [DGT-TM ▾] [EUR-Lex ▾] [UNPC ▾]        │
│          [My Uploads ▾]                                         │
│  Domain: [All ▾]  Direction: [Both ▾]  Register: [All ▾]       │
│  Length:  [10] — [50] tokens                                    │
│  Terminology density: [Any ▾]                                   │
│  Search: [________________________________] [🔍]               │
│                                                                 │
│  ┌──── Results: 1,247 segments ────────────────────────────┐   │
│  │ ☐ │ Source (FR)                │ Reference (EN)         │   │
│  │───│────────────────────────────│────────────────────────│   │
│  │ ☑ │ Le ministre de la Santé   │ The Minister of Health │   │
│  │   │ et de la Prévention a...  │ and Prevention...      │   │
│  │   │ 📁 parliamentary │ 🔤32 tok│ IATE: 3 terms         │   │
│  │───│────────────────────────────│────────────────────────│   │
│  │ ☐ │ Les États membres doivent │ Member States shall    │   │
│  │   │ transposer la directive...│ transpose the...       │   │
│  │   │ 📁 legal │ 🔤18 tok       │ IATE: 5 terms         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Selected: 3 segments                                           │
│  [ Generate MT Translations → ] [ Inject Errors Directly → ]   │
└─────────────────────────────────────────────────────────────────┘
```

- Pre-loaded corpora are searchable and filterable
- Each row shows source, reference, domain, token count, IATE term count
- Teacher selects segments with checkboxes
- Two action paths: generate MT first, or inject errors directly into the reference

#### 4.2.2 Upload Corpus

```
┌─────────────────────────────────────────────────────────────────┐
│  📤 UPLOAD CORPUS                                               │
│                                                                 │
│  Supported formats:                                             │
│  • TMX (Translation Memory Exchange)                            │
│  • TSV (tab-separated: source \t target)                        │
│  • Aligned text (two files, one line per segment)               │
│                                                                 │
│  [ 📁 Choose file(s)... ]                                       │
│                                                                 │
│  Corpus name: [________________________]                        │
│  Source language: [FR ▾]  Target language: [EN ▾]               │
│  Domain: [________________________]                              │
│  Register: [Formal ▾]                                           │
│                                                                 │
│  [ Upload & Index ]                                             │
│                                                                 │
│  Uploaded corpora:                                              │
│  • "EU Environmental Directives" (FR→EN, 342 segments, legal)  │
│  • "UN Security Council 2024" (FR→EN, 156 segments, diplomatic)│
└─────────────────────────────────────────────────────────────────┘
```

#### 4.2.3 Generate Translations

After selecting segments from the corpus browser:

```
┌─────────────────────────────────────────────────────────────────┐
│  🔄 GENERATE TRANSLATIONS                                       │
│                                                                 │
│  Selected: 3 segments from Europarl (FR→EN)                     │
│                                                                 │
│  Translation methods (select one or more):                      │
│                                                                 │
│  MT SYSTEMS                                                     │
│  ☑ Google Translate          [✓ Connected]                      │
│  ☑ DeepL                     [✓ Connected]                      │
│  ☐ NLLB-200 (local)         [Not configured]                   │
│                                                                 │
│  LLM AS TRANSLATOR                                              │
│  ☑ GPT-4.1                   [✓ Connected]                      │
│  ☐ Claude                    [Not configured]                   │
│  ☑ DeepSeek V3               [✓ Connected]                      │
│                                                                 │
│  Translation prompt (for LLMs):                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ You are a professional EU translator. Translate the      │   │
│  │ following French text into English, maintaining formal   │   │
│  │ register and EU terminology conventions.                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│  [ Load preset: EU Formal ▾ ] [ Save as preset ]               │
│                                                                 │
│  MANUAL TRANSLATION                                             │
│  ☑ Allow manual translation / editing of MT output              │
│                                                                 │
│  [ Generate → ]                                                 │
└─────────────────────────────────────────────────────────────────┘
```

After generation:

```
┌─────────────────────────────────────────────────────────────────┐
│  TRANSLATION RESULTS — Segment 1 of 3                           │
│                                                                 │
│  Source: "Le ministre de la Santé et de la Prévention a..."     │
│  Reference: "The Minister of Health and Prevention..."          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Google:  "The Minister of Health announced..."   [Edit] │   │
│  │ DeepL:   "The Health Minister announced..."      [Edit] │   │
│  │ GPT-4.1: "The Minister of Health and Prevention  [Edit] │   │
│  │           has announced..."                              │   │
│  │ Manual:  [_____________________________________] [Save] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Base for error injection: (●) Reference  (○) Google  (○) DeepL │
│                                                                 │
│  [ ← Previous segment ]  [ Proceed to Error Injection → ]      │
└─────────────────────────────────────────────────────────────────┘
```

- Each MT output is shown with an **[Edit]** button for manual correction
- A **Manual** row allows the teacher to type a translation from scratch
- The teacher selects which text becomes the base for error injection (reference, one of the MT outputs, or the manual translation)
- For L3 comparison exercises, all MT outputs are preserved and used as-is (no error injection — real MT errors become the assessment content)

### 4.3 Review Queue

Two-column layout: queue sidebar (left) + detail panel (right).

**Queue sidebar**: Filterable list of items by status (Draft/Reviewed/Published/Rejected), domain, direction, MQM category, difficulty. Each item shows ID, status badge, source snippet, MQM mini-profile, QE delta badge.

**Detail panel** (see teacher interface mockup for full design):
- **Top**: Source and injected translation side by side (two-column grid)
- **Below top**: Reference translation in gray
- **Summary strip**: Status, QE delta, GEMBA detection rate, domain, direction, difficulty, error count, MQM profile, ToM/skill breakdown
- **Error manifest**: Expandable cards per error with full editing (category, type, severity, ToM, skill, span text, correct text, Layer 1 four-field explanation, Layer 2a Conceptual, Layer 2b Technical)
- **Teacher notes**: Internal text field
- **Actions**: Reject (red) / Regenerate (orange) / Approve & Publish (green)

**Label conventions** (teacher-facing):
- Layer 2a: **"Conceptual"**
- Layer 2b: **"Technical"**

**Batch operations**: Checkboxes in queue sidebar + "Approve selected" / "Reject selected" toolbar buttons for quick triage.

### 4.4 Exercise Builder

Two sections:

**AI-Suggested Exercises** (top, from blind spot analysis):
- Shows recommendation with rationale: "Class detection rate for OMISSION is 32% — below S4 threshold."
- "Accept & Create" auto-selects relevant items and pre-fills configuration
- "Dismiss" hides the suggestion

**Manual Selection** (main):
- Filter dropdowns: MQM category, difficulty, domain, direction, skill, status
- Checkbox list of published items with inline metadata
- Exercise configuration panel:
  - Exercise name
  - Mode: Evaluation only / PE only / Both (student choice)
  - Scaffolding level: L0 / L1 / L2 / L3
  - Justification type: Mode A (free-text) / Mode B (structured ToM)
  - Clean segments: No / 20% / 30% (L3 only)
  - False annotations: No / 1 per 3-4 true / 1 per 2-3 true (L0 only)
  - Item ordering: Manual / Auto (by difficulty ascending) / Random
  - Assign to: Class / Individual students

### 4.5 Class Management

#### 4.5.1 Student Accounts

```
┌─────────────────────────────────────────────────────────────────┐
│  👥 STUDENT ACCOUNTS                                            │
│                                                                 │
│  Class: [MT Post-Editing 2026 — Group A ▾]                      │
│                                                                 │
│  [ + Add Student ]  [ 📤 Import CSV ]  [ 📥 Export ]            │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Username │ Display Name │ Level  │ Sessions │ Avg Score │ │ │
│  │──────────│──────────────│────────│──────────│───────────│ │ │
│  │ marie.d  │ Marie Dupont │ L1 ▾   │ 5        │ 72%       │ │ │
│  │ jean.m   │ Jean Martin  │ L0 ▾   │ 2        │ 61%       │ │ │
│  │ alice.b  │ Alice Bernard│ L2 ▾   │ 8        │ 81%       │ │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  CSV format: username, display_name, password                   │
│  (passwords are hashed on import)                               │
└─────────────────────────────────────────────────────────────────┘
```

The **Level** column is a dropdown — the teacher can promote or restrict individual students directly from this table.

#### 4.5.2 Level Configuration

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 LEVEL CONFIGURATION                                         │
│                                                                 │
│  Class default levels:                                          │
│  ☑ L0 Navigator    ☑ L1 Guided    ☐ L2 Independent   ☐ L3 Expert│
│                                                                 │
│  ℹ️ Students can only access exercises at their enabled levels.  │
│     Individual overrides take precedence over class defaults.   │
│                                                                 │
│  Progression recommendations (from analytics):                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Marie Dupont: S1=92%, S2=85%, S3=71% — Ready for L2?  │   │
│  │  [ Promote to L2 ]  [ Keep at L1 ]                      │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  Jean Martin: S1=78%, S2=60% — Not yet ready for L1    │   │
│  │  Weak areas: Grammar detection (60%)                    │   │
│  │  [ Keep at L0 ]                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Mastery thresholds (adjustable):                               │
│  S1 Surface:  [90]%  │  S2 Grammar: [80]%                      │
│  S3 Meaning:  [70]%  │  S4 Complete: [65]%                     │
│  S5 Term:     [70]%  │  S6 Pragmatic: [60]%                    │
│  S7 Discourse: [55]%  │  Over-editing: ≤ [20]%                  │
│  Window: Last [3] sessions                                      │
│                                                                 │
│  [ Save Thresholds ]                                            │
└─────────────────────────────────────────────────────────────────┘
```

The system computes readiness but **never auto-promotes** — the teacher always decides. This is the "teacher-gated transitions" principle from our framework [Grounded in: PCK (Shulman 1986) — teacher expertise about student readiness cannot be fully automated].

### 4.6 Analytics Dashboard

#### 4.6.1 Class Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 CLASS OVERVIEW — MT Post-Editing 2026 — Group A             │
│                                                                 │
│  ┌──── Detection Rate by MQM Category ────────────────────┐    │
│  │  [Grouped bar chart: each MQM category, bars per        │    │
│  │   session, showing class average over time]              │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──── Skill Mastery (Class) ────┐  ┌── Most Missed ─────┐    │
│  │  [Radar chart: S1-S7          │  │  1. Omission: 32%   │    │
│  │   class average]              │  │  2. Style: 41%      │    │
│  │                               │  │  3. Terminology: 55% │    │
│  │  ━━ Class avg  ╌╌ Threshold   │  │  4. Addition: 58%   │    │
│  └───────────────────────────────┘  └─────────────────────┘    │
│                                                                 │
│  ┌──── Over-Editing Tendency ────────────────────────────┐     │
│  │  [Box plot: false positive rate distribution across     │     │
│  │   students, with 20% threshold line]                    │     │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──── Justification Quality ────────────────────────────┐     │
│  │  Surface: 35%  │  Partial: 42%  │  Deep: 23%           │     │
│  │  [Stacked bar over sessions]                            │     │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.6.2 Individual Student View

Accessible from Class Overview by clicking a student name, or from Student Accounts table.

Shows the same charts as the student's "My Progress" view, plus:
- Comparison against class average (overlaid on charts)
- Justification quality breakdown (surface/partial/deep per session)
- Blind spot alerts with specific item examples
- Full session history with per-item results

#### 4.6.3 ToM Blind Spot Analysis

The key novel view — cross-tabulates MQM category × ToM level × detection rate:

```
┌─────────────────────────────────────────────────────────────────┐
│  🔍 ToM BLIND SPOT ANALYSIS                                     │
│                                                                 │
│  ┌──── MQM × ToM Heatmap (class-wide) ───────────────────┐    │
│  │              │ 🔵 Machine │ 🟢 Author │ 🟡 Reader      │    │
│  │ Mistranslation │  78% ■■■■ │   62% ■■■ │  --           │    │
│  │ Omission       │  --       │   32% ■■  │  --           │    │
│  │ Addition       │  58% ■■■  │   --      │  --           │    │
│  │ Grammar        │  85% ■■■■ │   --      │  --           │    │
│  │ Terminology    │  --       │   --      │  55% ■■■      │    │
│  │ Style          │  --       │   --      │  41% ■■       │    │
│  │                                                         │    │
│  │  ■ ≥80%  ■ 60-79%  ■ 40-59%  ■ <40%                   │    │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ⚠️ ALERTS:                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  🔴 Author × Omission: 32% — well below S4 threshold    │   │
│  │     Students miss omissions when MT output reads fluently│   │
│  │     → [Generate targeted exercise]                       │   │
│  │                                                         │   │
│  │  🟡 Reader × Style: 41% — below S6 threshold            │   │
│  │     Students miss register/idiomaticity issues           │   │
│  │     → [Generate targeted exercise]                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  View: [Class-wide ▾]  or select student: [__________ ▾]       │
└─────────────────────────────────────────────────────────────────┘
```

The "[Generate targeted exercise]" button feeds the blind spot data directly into the Exercise Builder's AI suggestion engine.

### 4.7 Settings

#### 4.7.1 API Credentials

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚙️ API CREDENTIALS                                             │
│                                                                 │
│  ℹ️ Default credentials are loaded from environment variables.   │
│     Overrides below apply to this project only.                 │
│                                                                 │
│  MT SYSTEMS                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Google Translate                                         │   │
│  │ API Key: [••••••••••••••••••] [👁 Show] [🗑 Clear]       │   │
│  │ Source: ● Env var  ○ Override                            │   │
│  │ Status: ✓ Connected (tested 2 min ago)                   │   │
│  │                                      [ Test Connection ] │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ DeepL                                                    │   │
│  │ API Key: [________________________] [👁] [🗑]             │   │
│  │ Source: ○ Env var  ● Override                            │   │
│  │ Status: ⚠️ Not configured                                │   │
│  │                                      [ Test Connection ] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  LLM SERVICES                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ OpenAI (GPT-4.1)                                        │   │
│  │ API Key: [••••••••••••••••••] [👁] [🗑]                   │   │
│  │ Model: [gpt-4.1-nano ▾]                                 │   │
│  │ Source: ● Env var  ○ Override                            │   │
│  │ Status: ✓ Connected                  [ Test Connection ] │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ DeepSeek                                                 │   │
│  │ API Key: [________________________] [👁] [🗑]             │   │
│  │ Model: [deepseek-v3 ▾]                                  │   │
│  │ Source: ○ Env var  ○ Override  ● Not configured          │   │
│  │ Status: ⚠️ Not configured           [ Test Connection ] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  QE MODELS                                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ xCOMET: [Local ▾]  Path: [/models/xcomet-xl]           │   │
│  │ xTower: [Local ▾]  Path: [/models/xtower-13b]          │   │
│  │ GEMBA:  Uses OpenAI API key above                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [ Save Settings ]                                              │
└─────────────────────────────────────────────────────────────────┘
```

Each credential shows:
- Source indicator: env var (default) or manual override
- Masked key with show/hide toggle
- "Test Connection" button that makes a minimal API call and reports success/failure
- Status badge: Connected / Not configured / Error

#### 4.7.2 System Configuration

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚙️ SYSTEM CONFIGURATION                                        │
│                                                                 │
│  Student App                                                    │
│  Port: [7860]                                                   │
│  Share link: ☑ Enable (Gradio share=True)                       │
│  Current link: https://xxxxx.gradio.live                        │
│  [ 🔄 Regenerate Link ]  [ 📋 Copy Link ]                      │
│                                                                 │
│  Error Injection                                                │
│  Default LLM for injection: [GPT-4.1-nano ▾]                   │
│  Default LLM for explanations: [GPT-4.1-nano ▾]                │
│  Max retry attempts: [3]                                        │
│  QE validation threshold: [0.1] (minimum score drop)            │
│                                                                 │
│  Translation Prompt Presets                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ EU Formal: "You are a professional EU translator..."     │   │
│  │ General: "Translate the following text from {src}..."    │   │
│  │ Casual: "Translate naturally, as if for a blog post..."  │   │
│  │ [ + Add Preset ]                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Data                                                           │
│  Storage backend: [JSON/CSV (v1) ▾]                             │
│  Data directory: [./data]                                       │
│  [ Export All Data (ZIP) ]  [ Backup ]                          │
└─────────────────────────────────────────────────────────────────┘
```

The **"Launch Student App"** and **share link management** are prominently placed — this is how the teacher gives students access.

---

## 5. Cross-Interface Coordination

### 5.1 Data Flow Between Interfaces

```
Teacher App                    Backend API                Student App
───────────                    ───────────                ───────────
Corpus Browser ──→ POST /segments/select ──→ [stored]
Generate MT    ──→ POST /translations/generate ──→ [stored]
                   (manual edit: PUT /translations/{id})
Error Injection──→ POST /items/generate ──→ [stored]
Review/Edit    ──→ PUT /items/{id} ──→ [updated]
Approve        ──→ PUT /items/{id}/status ──→ [published]
Exercise Build ──→ POST /exercises ──→ [stored]
Assign         ──→ POST /assignments ──→              ──→ Exercise list
Level Config   ──→ PUT /students/{id}/levels ──→      ──→ Level gate

                                              ←── GET /exercises/{id}
                                              ←── GET /items/{id}
                                              POST /responses ←──── Submit annotations
                                              POST /justifications ←── Submit justifications
                                              GET /feedback/{id} ──→ Reveal feedback
                                              GET /progress ──→     Progress dashboard

Analytics      ←── GET /analytics/class
               ←── GET /analytics/student/{id}
               ←── GET /analytics/blindspots
```

### 5.2 Level Enforcement

The level gate works at two points:
1. **Exercise assignment**: Teacher can only assign exercises at levels enabled for the student/class
2. **Student app**: The Gradio app checks `allowed_levels` on login and filters the exercise list accordingly

If the teacher changes a student's level mid-session, the change takes effect on next login (not mid-exercise).

### 5.3 Real-Time vs. Batch

- **Student interactions**: Real-time (immediate scoring and feedback after submission)
- **Analytics**: Computed on-demand when the teacher opens the dashboard (acceptable latency for v1)
- **Blind spot analysis**: Aggregated after each completed session, available on next dashboard refresh
- **Progression recommendations**: Recomputed when the teacher opens Level Configuration

---

## 6. Implementation Priority

| Priority | Component | Technology | Effort | Blocks |
|---|---|---|---|---|
| **P0** | FastAPI backend + data models | Python | Medium | Everything |
| **P0** | Student auth (login + session) | Gradio + FastAPI | Small | Student app |
| **P0** | Custom span selector component | Gradio + JS | Medium | Student annotation |
| **P1** | Student: L2 Independent evaluation flow | Gradio | Medium | Core demo |
| **P1** | Teacher: Corpus browser + MT generation | Streamlit | Medium | Item creation |
| **P1** | Teacher: Review queue (view + approve) | Streamlit | Medium | Publishing items |
| **P2** | Student: L0 Navigator (with false annotations) | Gradio | Medium | Scaffolding |
| **P2** | Student: L1 Guided | Gradio | Small | Scaffolding |
| **P2** | Teacher: Exercise builder | Streamlit | Medium | Exercise assignment |
| **P2** | Student: Justification + feedback phases | Gradio | Medium | Cognitive forcing |
| **P2** | Teacher: Full error editing | Streamlit | Medium | Quality control |
| **P3** | Student: L3 Expert + comparison view | Gradio | Medium | Advanced exercises |
| **P3** | Student: PE mode | Gradio | Medium | Dual mode |
| **P3** | Teacher: Analytics dashboard | Streamlit + Plotly | Large | Blind spot analysis |
| **P3** | Teacher: Level configuration + class mgmt | Streamlit | Medium | Progression |
| **P3** | Settings: API credentials | Streamlit | Small | MT generation |
| **P4** | Student: My Progress dashboard | Gradio + Plotly | Medium | Student motivation |
| **P4** | Teacher: AI-suggested exercises | Streamlit | Medium | Adaptive targeting |
| **P4** | Deployment: share link + launch script | Shell/Python | Small | University pilot |

**Critical path for CIKM demo**: P0 + P1 + selected P2 items = core pipeline + student L2 evaluation + teacher review + exercise assignment. This gives a working end-to-end demo in ~6 weeks.

---

## 7. Open Questions

1. **Gradio version constraints**: Gradio's custom component API has changed across versions (3.x → 4.x → 5.x). Need to pin a version early and verify the span selector component works with it.

2. **Share link persistence**: Gradio's `share=True` creates 72h temporary links. For a semester-long course, we need either HuggingFace Spaces deployment, a university server, or a tunnel service (ngrok/cloudflare). Decision deferred to deployment phase.

3. **Concurrent users**: How many students will use the system simultaneously? Gradio handles concurrent users via queuing, but heavy loads may need a dedicated server. For a typical class (20-30 students), a single machine should suffice.

4. **Offline mode**: Should students be able to work offline (e.g., download exercises, annotate locally, sync later)? Not planned for v1, but the JSON-based data model would support it.

5. **Accessibility**: The span selection interaction (click-drag) may not work well with screen readers or keyboard-only navigation. Need to add keyboard shortcuts (e.g., arrow keys to move cursor, Shift+arrow to select, Enter to confirm) as an alternative interaction path.

6. **Mobile support**: Gradio renders responsively, but span selection via touch is imprecise. For v1, recommend desktop/laptop only. The task description should note this.
