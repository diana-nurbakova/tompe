# ToM-PE Error Injection, Competency Mapping & Annotation System
## Specification Document — v1.1 (March 2026)

**Companion to**: ToM-PE System Specification v0.2
**Scope**: This document specifies three tightly coupled subsystems: (1) the LLM-based error injection pipeline with its tagging format and prompt architecture, (2) the mapping between MQM error taxonomy and student competencies/skills, and (3) the progressive annotation scaffolding system. These subsystems share data structures and must be designed together.

**Grounding principle**: Every design decision in this document is traceable to published research. Citations are provided inline in the format `[Author Year]` to enable direct verification and to support the EC-TEL and CIKM papers.

---

## 1. Error Injection Tagging Format

### 1.1 Design Rationale

Research on span-level annotation in LLM prompts converges on a clear hierarchy:

1. **Semantically meaningful XML tags with attributes and brief explanations** outperform all alternatives. This is supported by three independent research streams:
   - *In-context learning theory*: [Min et al. 2022, EMNLP] showed that label space and format consistency matter more than label correctness for ICL, but semantically coherent labels outperform arbitrary ones. [Krishna Kumar et al. 2025] found that semantic anchors in tag tokens create rigid constraints that ICL alone cannot override — a 0% semantic override rate across 8 LLMs.
   - *Task Recognition vs. Task Learning*: [Pan et al. 2023, Findings of ACL] decomposed ICL into Task Recognition (activating pre-trained knowledge) and Task Learning (learning new mappings). Meaningful tags like `<MISTRANSLATION>` engage both pathways; abstract tags like `<error_1>` force reliance on TL alone, requiring more demonstrations.
   - *Instruction-tuned model amplification*: [Wei et al. 2023] showed that instruction tuning strengthens TR more than TL, making descriptive tags especially critical for models like GPT-4 and Claude.
2. **The xTower inline XML pattern** is the proven MT-specific format. [Treviso et al. 2024, Findings of EMNLP] use `<error1 severity="major">span</error1>` for MT error annotation with natural-language explanations, achieving state-of-the-art explainable QE.
3. **ERRANT-level granularity** (~55 types) hits the sweet spot for controlled injection. [Stahlberg & Kumar 2021, BEA Workshop] showed tagged corruption models with ERRANT-granularity tags outperform untagged models by >3 F0.5 points. Finer tags (GECToR's ~5000) offer diminishing returns for LLM-based generation.
4. **Inline explanations** improve annotation quality for large models. [Lampinen et al. 2022, Findings of EMNLP] found that explanations in few-shot examples improve performance, with hand-tuned explanations offering substantially larger benefits.
5. **Format restrictions degrade reasoning** by 10–15% [Tam et al. 2024, "Let Me Speak Freely?"]. Mitigation: two-step NL-to-Format approach (§2.1).

### 1.2 Canonical Tag Format

Every error span in few-shot examples, codebook entries, and LLM outputs uses this format:

```xml
<ERROR_TYPE type="subtype" severity="major|minor|critical" 
            tom="1st_machine|1st_author|2nd_reader|recursive"
            desc="brief natural-language explanation">
  error span text
</ERROR_TYPE>
```

**Tag naming rules:**
- Tag name = MQM top-level or salient subcategory, UPPER_SNAKE_CASE
- Must be semantically meaningful (activates LLM pre-trained knowledge)
- Must be consistent across all examples and prompts
- Max 25 characters

**Attribute rules:**
- `type` = MQM subcategory or FR-EN-specific subtype (lowercase_snake_case)
- `severity` = `minor` | `major` | `critical`
- `tom` = ToM level required for detection (see §3)
- `desc` = 5–15 word natural-language explanation of *why* this is an error
- `dir` = (optional) primary direction: `fr_en` | `en_fr` | `both` — marks types that are direction-specific (see §1.4)

### 1.2.1 Severity: Context-Dependent, Not Fixed per Type

**Critical design note**: MQM officially defines four severity levels (Neutral, Minor, Major, Critical) with formal criteria [Lommel, Burchardt & Uszkoreit 2014; Gladkoff et al. 2024], but **does not prescribe fixed severity-per-error-type**. The official MQM position is that severity depends on the error's impact in context — the same grammar error can be Minor (does not affect meaning) or Major (causes confusion or changes meaning). The WMT campaigns [Freitag et al. 2021] use only Minor/Major/Non-translation, omitting Critical because it is "often context-specific."

For our pedagogical purposes, each codebook entry specifies a `severity_range` (e.g., `["minor", "major"]`) indicating the plausible range for that error type. The teacher selects the target severity when configuring an exercise. The LLM prompt specifies the exact severity to inject, and the injected error's severity must be justified by the context (e.g., a false cognate that reverses meaning = major; one that only shifts nuance = minor).

**Severity definitions (adapted from MQM + WMT):**

| Severity | Weight | Definition | Pedagogical Gloss |
|---|---|---|---|
| Minor | 1 | Does not impede understanding; noticeable quality issue | "A reader would notice but not misunderstand" |
| Minor (Punctuation) | 0.1 | Locale-specific punctuation only [Freitag et al. 2021] | "Appearance only, not meaning" |
| Major | 5 | Seriously affects understanding or changes meaning | "A reader would be confused or misled" |
| Critical | 25 | Renders content unfit or poses risk of harm | "A reader would act on wrong information" |

### 1.2.2 Direction-Specific Error Types

Some error types manifest primarily or exclusively in one translation direction. These are marked with a `dir` attribute in the codebook and used for exercise targeting:

| Direction | Dominant Error Types | Reason |
|---|---|---|
| EN→FR | `agreement_gender`, `agreement_number`, `relative_pronoun` | French has grammatical gender; English does not |
| FR→EN | `false_cognate`, `article` (over-insertion of "the") | English lacks partitive articles; FR-EN cognate interference |
| Both | `omission`, `addition`, `terminology`, `locale` | Language-pair-independent patterns |

### 1.3 Tag Inventory (Operational Subset)

We use a **two-tier tag system**: 8 primary tags (mapped to MQM top-level + key subcategories) and ~25 `type` attribute values (mapped to MQM leaf nodes). This balances semantic activation (primary tags) with fine-grained control (type attributes).

#### Primary Tags

| Primary Tag | MQM Dimension | MQM Subcategories Covered |
|---|---|---|
| `<MISTRANSLATION>` | Accuracy | Mistranslation, Overtranslation, Undertranslation |
| `<OMISSION>` | Accuracy | Omission |
| `<ADDITION>` | Accuracy | Addition, MT Hallucination |
| `<UNTRANSLATED>` | Accuracy | Untranslated text |
| `<GRAMMAR>` | Linguistic conventions | Grammar (agreement, tense, word order, function words) |
| `<TERMINOLOGY>` | Terminology | Inappropriate for context, Inconsistent use |
| `<STYLE>` | Style | Awkward, Unidiomatic, Register |
| `<LOCALE>` | Locale conventions | Date, number, currency, address format |

Plus two special-purpose tags:

| Special Tag | Purpose |
|---|---|
| `<SPELLING>` | Fluency > Spelling (including diacritics, capitalization) |
| `<PUNCTUATION>` | Fluency > Punctuation (weight 0.1 for minor) |

#### Type Attribute Values

Each primary tag accepts a constrained set of `type` values. These correspond to MQM leaf nodes and/or FR-EN-specific error patterns:

**`<MISTRANSLATION type="...">`**
- `false_cognate` — Faux ami (sensible≠sensible, actuellement≠actually)
- `word_sense` — Wrong sense of polysemous word (avocat: lawyer vs. avocado)
- `number` — Numerical value error
- `entity` — Named entity error
- `overly_literal` — Source structure calqued into target
- `overtranslation` — More specific than source warrants
- `undertranslation` — Less specific than source warrants
- `ambiguity` — Ambiguous source resolved incorrectly
- `negation` — Negation added, removed, or misplaced

**`<OMISSION type="...">`**
- `clause` — Subordinate clause or phrase dropped
- `modifier` — Adjective, adverb, or prepositional phrase dropped
- `discourse_marker` — Connector/transition dropped
- `partial` — Part of a compound expression dropped

**`<ADDITION type="...">`**
- `hallucination` — Content fabricated with no source basis
- `explicitation` — Implicit information made explicit without warrant
- `qualifier` — Unnecessary intensifier or hedge added

**`<GRAMMAR type="...">`**
- `agreement_gender` — Gender agreement failure (critical for EN→FR)
- `agreement_number` — Number agreement failure
- `tense` — Wrong tense/aspect/mood
- `article` — Wrong/missing/extra determiner (critical for FR→EN)
- `preposition` — Wrong preposition
- `word_order` — Constituent order error
- `relative_pronoun` — Wrong relative pronoun (qui/que/dont)

**`<TERMINOLOGY type="...">`**
- `wrong_term` — Domain term replaced by general synonym
- `inconsistent` — Same concept rendered differently within text
- `institutional` — EU/UN specific term incorrect (IATE violation)

**`<STYLE type="...">`**
- `awkward` — Grammatical but reads unnaturally
- `unidiomatic` — Wrong collocation (posed a rabbit = stood up)
- `register_formal` — Inappropriately formal (vous where tu expected)
- `register_informal` — Inappropriately informal (tu where vous expected)

**`<LOCALE type="...">`**
- `date_format` — Wrong date convention (25/03 vs. March 25)
- `number_format` — Wrong decimal/thousands separator
- `currency_format` — Wrong currency symbol placement
- `time_format` — Wrong time convention (14h30 vs. 2:30 PM)

### 1.4 Full Example: Tagged Error in Few-Shot Prompt

**FR→EN direction:**

```
Source (FR): Il assiste à la conférence depuis ce matin.
Reference (EN): He has been attending the conference since this morning.
Injected (EN): He has been <MISTRANSLATION type="false_cognate" severity="major" 
  tom="1st_machine" desc="assister≠assist; FR assister à = attend">assisting 
  at</MISTRANSLATION> the conference since this morning.
```

**EN→FR direction:**

```
Source (EN): She went to Paris yesterday.
Reference (FR): Elle est allée à Paris hier.
Injected (FR): Elle est <GRAMMAR type="agreement_gender" severity="major" 
  tom="1st_machine" desc="past participle must agree with feminine subject 'elle'">
  allé</GRAMMAR> à Paris hier.
```

**Omission example (span in SOURCE, not target):**

```
Source (FR): Le ministre de la Santé <OMISSION type="modifier" severity="major" 
  tom="1st_author" desc="'et de la Prévention' dropped from title">et de la 
  Prévention</OMISSION> a annoncé de nouvelles mesures.
Injected (EN): The Minister of Health announced new measures.
```

---

## 2. Two-Step Prompt Architecture

### 2.1 Rationale

Research shows that structured format restrictions degrade LLM reasoning by 10–15% (Tam et al. 2024). The mitigation is a **NL-to-Format** approach: reason first in natural language, then produce structured output. For error injection, this means separating the *planning* step (where to inject, what kind) from the *execution* step (produce modified text with XML tags).

Additionally, requiring explanations in the returned output mirrors the explanations provided in few-shot examples, creating format symmetry that improves ICL performance.

### 2.2 Step 1: Error Planning (Reasoning)

```
SYSTEM PROMPT:
You are a translation quality expert specializing in French-English 
translation errors. You understand MQM error taxonomy and Theory of Mind 
in translation.

USER PROMPT:
Given the following source text and its correct English translation, 
identify ONE location where a {ERROR_TYPE} error of {SEVERITY} severity 
could be naturally introduced — the kind of error a {MT_SYSTEM} would 
plausibly produce.

Source (FR): {source_text}
Correct translation (EN): {reference_translation}
Domain: {domain}
Error to inject: {mqm_category} > {mqm_subcategory}
Severity: {severity}

Think through:
1. Which word(s) or phrase(s) in the translation are vulnerable to this 
   error type?
2. What would the MT system likely "misunderstand" about the source to 
   produce this error?
3. What would a target reader infer from the erroneous translation?
4. Is the planned error distinguishable from other error types?

Respond in JSON:
{
  "target_span": "the word(s) to modify",
  "planned_error": "what the span will become",
  "mt_reasoning": "what the MT system likely misinterpreted",
  "reader_impact": "what a reader would understand",
  "boundary_check": "why this is {mqm_subcategory} and not something else"
}
```

### 2.3 Step 2: Error Execution (Structured Output)

```
USER PROMPT:
Now produce the modified translation with the error injected. Use XML 
annotation to mark the error span.

Tag format: <{TAG_NAME} type="{subtype}" severity="{severity}" 
  tom="{tom_level}" desc="{5-15 word explanation}">{error text}</{TAG_NAME}>

Original translation: {reference_translation}
Planned modification: {step1_output}

Rules:
- Modify ONLY the identified span
- Keep all other text EXACTLY identical to the original
- The error must be plausible — something a real MT system would produce
- The surrounding text must remain grammatical

Respond in JSON:
{
  "injected_translation": "full text with <TAG> annotation inline",
  "error_span_text": "just the error span content",
  "original_span_text": "what was there before",
  "mqm_category": "{top_level}",
  "mqm_subcategory": "{specific_type}",
  "severity": "{severity}",
  "tom_level": "{tom_level}",
  "explanation": {
    "mt_interpretation": "The MT system likely interpreted ... as ...",
    "actual_meaning": "The source actually means ...",
    "reader_impact": "A target reader would understand this as ...",
    "correction_rationale": "The correct translation is ... because ..."
  }
}
```

### 2.4 Verification Step (Automated)

After LLM generates the injection:

1. **Span isolation**: Parse XML tags from `injected_translation`, extract error span boundaries
2. **Diff check**: Verify that non-tagged text is character-identical to reference
3. **Tag validation**: Confirm tag name, type, severity, and tom attributes are from the allowed inventory (§1.3)
4. **Category consistency**: Verify `mqm_category` matches tag name and `mqm_subcategory` matches type value
5. **QE check**: Run xCOMET on (source, injected_translation) — score should decrease vs. (source, reference)
6. **GEMBA check**: Run GEMBA-MQM on (source, injected_translation) — should detect the injected error
7. **Explanation completeness**: All four explanation fields non-empty and >10 words each

Items that fail verification enter a retry queue (max 3 attempts with rephrased prompts) before falling to manual review.

### 2.5 Granularity Decision

**Operational granularity: 10 primary tags × ~25 type values = ~35 actionable error types.**

This sits between:
- WMT subset (20 categories — too coarse for pedagogical targeting)
- MQM-Full (100+ types — too fine for LLM injection control)
- ERRANT (55 types — right ballpark but GEC-specific, not translation-specific)

The 35-type level was chosen because:
- Each type has a distinct FR-EN realization pattern (needed for examples)
- Each type maps to a distinct ToM demand (needed for competency tracking)
- Each type is semantically distinct enough to serve as an XML tag or attribute value
- The LLM can reliably distinguish between types at this granularity

**Extensibility**: New types are added by defining a new `type` attribute value under an existing primary tag, plus codebook entry. No schema changes required.

---

## 3. Error Taxonomy → Competency/Skill Mapping

### 3.1 Competency Model Overview

The ToM-PE competency model defines **7 core skills** that map to the intersection of MQM error detection, ToM perspective-taking, and PE action. Each skill is independently tracked, scored, and used for progression decisions.

**Grounding**: The 7-skill decomposition synthesizes three established frameworks:
- **MQM error dimensions** [Lommel, Burchardt & Uszkoreit 2014] provide the error-type axis
- **ToM orders of intentionality** [Dunbar 2009; Sturm 2020; Fernández 2025] provide the cognitive demand axis
- **Temnikova's cognitive difficulty ranking** [Temnikova 2010] and **Daems et al.'s effort study** [Daems et al. 2017, Frontiers in Psychology] provide the empirical difficulty ordering (surface → accuracy → terminology → coherence)
- **PACTE translation competence model** [Hurtado Albir et al. 2017] validates that PE competence is multi-dimensional with distinct sub-competences
- **Robert, Schrijver & Ureel** [2023–2024] confirm that PE competence is *not* a subset of translation competence — supporting our decision to define PE-specific skills rather than mapping to generic translation competence

The skill ordering (S1→S7) follows both the empirical difficulty gradient from the literature and the ToM demand gradient from our framework. This ordering drives the progression path (§3.4).

### 3.2 The Seven Core Skills

| Skill ID | Skill Name | Description | Primary MQM Categories | Primary ToM Level |
|---|---|---|---|---|
| **S1** | Surface Error Detection | Detect spelling, punctuation, capitalization, and character encoding errors | Spelling, Punctuation | 1st_machine |
| **S2** | Grammatical Error Detection | Detect morphosyntactic errors: agreement, tense, word order, articles | Grammar | 1st_machine |
| **S3** | Meaning Transfer Verification | Detect mistranslation, false cognates, sense errors by comparing source-target meaning | Mistranslation | 1st_machine + 1st_author |
| **S4** | Completeness Verification | Detect omissions and additions by verifying all source content is present in target | Omission, Addition, Untranslated | 1st_author |
| **S5** | Terminology Verification | Detect domain-specific term errors by checking against terminological resources | Terminology | 2nd_reader |
| **S6** | Pragmatic & Style Evaluation | Detect register, idiomaticity, style, and locale convention errors | Style, Locale | 2nd_reader |
| **S7** | Coherence & Discourse Evaluation | Detect inter-sentential coherence breaks, anaphoric errors, discourse flow issues | (cross-category) | recursive |

### 3.3 Full MQM × ToM → Skill Mapping Matrix

This matrix is the authoritative reference for the system. Every error type maps to exactly one primary skill and zero or more secondary skills.

| Primary Tag | Type | Severity Range | ToM Level | Primary Skill | Secondary Skills | Typical Difficulty |
|---|---|---|---|---|---|---|
| MISTRANSLATION | false_cognate | major–critical | 1st_machine | **S3** | — | Medium |
| MISTRANSLATION | word_sense | major | 1st_machine | **S3** | S5 (if domain term) | Medium–High |
| MISTRANSLATION | number | minor–major | 1st_machine | **S3** | — | Low–Medium |
| MISTRANSLATION | entity | minor–major | 1st_machine | **S3** | — | Low–Medium |
| MISTRANSLATION | overly_literal | minor–major | 1st_machine | **S3** | S6 | Medium |
| MISTRANSLATION | overtranslation | minor | 1st_author | **S3** | S4 | Medium–High |
| MISTRANSLATION | undertranslation | minor | 1st_author | **S3** | S4 | Medium–High |
| MISTRANSLATION | ambiguity | major | 1st_machine | **S3** | — | High |
| MISTRANSLATION | negation | critical | 1st_machine | **S3** | — | Medium |
| OMISSION | clause | major–critical | 1st_author | **S4** | — | Medium–High |
| OMISSION | modifier | minor–major | 1st_author | **S4** | — | High |
| OMISSION | discourse_marker | minor | 1st_author | **S4** | S7 | High |
| OMISSION | partial | minor–major | 1st_author | **S4** | — | Medium |
| ADDITION | hallucination | major–critical | 1st_machine | **S4** | S3 | Medium |
| ADDITION | explicitation | minor | 1st_machine | **S4** | S6 | High |
| ADDITION | qualifier | minor | 1st_machine | **S4** | S6 | High |
| UNTRANSLATED | — | major–critical | 1st_machine | **S4** | — | Low |
| GRAMMAR | agreement_gender | minor–major | 1st_machine | **S2** | — | Low (EN→FR) |
| GRAMMAR | agreement_number | minor–major | 1st_machine | **S2** | — | Low |
| GRAMMAR | tense | minor–major | 1st_machine | **S2** | S3 (if meaning changes) | Medium |
| GRAMMAR | article | minor | 1st_machine | **S2** | — | Low (FR→EN) |
| GRAMMAR | preposition | minor–major | 1st_machine | **S2** | S3 (if meaning changes) | Medium |
| GRAMMAR | word_order | minor–major | 1st_machine | **S2** | — | Medium |
| GRAMMAR | relative_pronoun | minor–major | 1st_machine | **S2** | S3 | Medium |
| TERMINOLOGY | wrong_term | major | 2nd_reader | **S5** | S3 | Medium–High |
| TERMINOLOGY | inconsistent | minor | 2nd_reader | **S5** | S7 | High |
| TERMINOLOGY | institutional | major | 2nd_reader | **S5** | — | High |
| STYLE | awkward | minor | 2nd_reader | **S6** | — | High |
| STYLE | unidiomatic | minor–major | 2nd_reader | **S6** | — | Medium–High |
| STYLE | register_formal | minor–major | 2nd_reader | **S6** | — | Medium |
| STYLE | register_informal | minor–major | 2nd_reader | **S6** | — | Medium |
| LOCALE | date_format | minor | 2nd_reader | **S6** | — | Low |
| LOCALE | number_format | minor | 2nd_reader | **S6** | — | Low |
| LOCALE | currency_format | minor | 2nd_reader | **S6** | — | Low |
| LOCALE | time_format | minor | 2nd_reader | **S6** | — | Low |
| SPELLING | — | minor | 1st_machine | **S1** | — | Low |
| PUNCTUATION | — | minor (wt 0.1) | 1st_machine | **S1** | S6 (if locale-specific) | Low |

### 3.4 Skill → Progression Stage Mapping

The 7 skills map onto the 5-stage progression path (from ToM-PE spec v0.2 §8) as follows:

| Stage | Name | Active Skills | Annotation Level | Exercise Modes |
|---|---|---|---|---|
| **1** | Orientation | S1, S2 (surface + grammar) | L0 Navigator | Evaluation only, Critical severity, EN→FR only |
| **2** | Guided Detection | S3, S4 (meaning + completeness) | L1 Guided | Evaluation, Major severity added |
| **3** | Independent Evaluation | S3, S4, S5, S6 (+ terminology, pragmatics) | L2 Independent | Evaluation + PE, mixed severity |
| **4** | Dual Mode | S1–S6 (all) | L2 Independent | Evaluation + PE, both directions |
| **5a** | Expert: Analytical | S1–S7 (all + discourse) | L3 Expert | Independent eval across MT systems (Skill A) |
| **5b** | Expert: Judgment | S1–S7 (all + discourse) | L3 Expert | Comparative ranking + PE triage (Skill B) |

### 3.5 Mastery Criteria per Skill

For teacher-gated progression (v1), the system computes and displays these metrics. The teacher uses them as guidance for promotion decisions.

| Skill | Metric | Suggested Threshold | Window |
|---|---|---|---|
| S1 | Detection rate (spelling + punctuation) | ≥ 90% | Last 3 sessions |
| S2 | Detection rate (grammar errors) | ≥ 80% | Last 3 sessions |
| S3 | Detection rate (mistranslation) | ≥ 70% | Last 3 sessions |
| S4 | Detection rate (omission + addition) | ≥ 65% | Last 3 sessions |
| S5 | Detection rate (terminology, with IATE) | ≥ 70% | Last 3 sessions |
| S6 | Detection rate (style + locale) | ≥ 60% | Last 3 sessions |
| S7 | Detection rate (coherence, multi-sentence) | ≥ 55% | Last 3 sessions |
| ALL | Over-editing rate (false positive) | ≤ 20% | Last 3 sessions |
| ALL | Justification depth (% rated "deep") | ≥ 40% | Last 3 sessions |

Lower thresholds for higher skills reflect their greater cognitive difficulty (higher ToM demand).

---

## 4. Annotation System Specification

### 4.1 Overview

The annotation system operates at **four scaffolding levels** (L0–L3), corresponding to the CCL framework's progression from Navigator to Expert. At each level, the system presents different amounts of annotation information to the student, gradually fading scaffolding as competence develops. Teacher-gated transitions control movement between levels.

**Grounding**: The four-level scaffolding design draws on three established principles:
- **Scaffolding fading** [Renkl & Atkinson 2003; Renkl 2014]: Gradually removing support as learner competence increases — the dominant instructional design strategy in worked-example research
- **Expertise reversal effect** [Kalyuga et al. 2003; Kalyuga 2007]: Scaffolding that helps novices can harm experts by imposing unnecessary cognitive load — motivating the L0→L3 progression
- **CCL framework** [Dadić & Ermakova 2026]: Transposing professional collaboration roles (Navigator → Reviewer → Scrum Master → Peer Reviewer → Editor) into a developmental model for critical AI evaluation — our L0 Navigator directly implements CCL Stage 1
- **Cognitive forcing functions** [Buçinca, Malaya & Gajos 2021]: Requiring commitment before revealing feedback — implemented across all levels through the justification-before-feedback protocol
- **QE4PE scaffolding evidence** [Sarti et al. 2025, TACL]: Word-level QE highlights provide meaningful scaffolding for PE, with effectiveness varying by editor speed — supports our L1 Guided level design where approximate location hints guide without fully revealing errors

### 4.2 Annotation Data Model

Every item in the system carries a full annotation manifest. What the student *sees* depends on the scaffolding level.

```python
class ErrorAnnotation(BaseModel):
    """Complete annotation for one error in an item.
    Different fields are revealed at different scaffolding levels."""
    
    # === Always stored (ground truth) ===
    error_id: str
    span_start: int                    # Character offset in target text
    span_end: int
    span_text: str                     # The error span content
    original_text: str                 # What should be there (reference)
    
    # === Error classification ===
    primary_tag: PrimaryTag            # e.g., MISTRANSLATION
    error_type: str                    # e.g., false_cognate
    severity: Severity                 # minor | major | critical
    tom_level: TOMLevel               # 1st_machine | 1st_author | 2nd_reader | recursive
    primary_skill: SkillID            # S1–S7
    secondary_skills: List[SkillID]
    
    # === Explanation layers ===
    layer1_explanation: ContrastiveExplanation  # Error-specific
    layer2_explanation: SystemBehaviorExplanation  # MT architecture/training
    
    # === Annotation display metadata ===
    highlight_color: str               # Computed from primary_tag
    region_hint: RegionHint            # For L1 Guided: approximate location

class RegionHint(BaseModel):
    """Approximate location hint for L1 Guided level.
    Deliberately imprecise — marks a region, not the exact span."""
    hint_start: int                    # Wider than actual span
    hint_end: int                      # Wider than actual span
    hint_label: str                    # "Look for an accuracy issue in this region"
```

### 4.3 What Students See at Each Level

#### L0 — Navigator (Full Scaffolding)

**Purpose**: Teach the annotation vocabulary and error taxonomy. Student practices *verifying* and *classifying*, not detecting.

**Visible to student:**
- Error spans highlighted with color-coding by primary tag
- Primary tag label shown (e.g., "MISTRANSLATION")
- Error type shown (e.g., "false_cognate")
- Severity badge shown (minor/major/critical)
- ToM perspective indicator shown (🔵 Machine / 🟢 Author / 🟡 Reader)

**Student task:**
1. For each highlighted error: confirm or dispute the classification
2. Select which ToM perspective is most relevant (dropdown)
3. Write a brief justification explaining *why* this is an error
4. Optionally: attempt a correction

**What is NOT shown at L0:**
- Layer 1 explanation (revealed after student justification)
- Layer 2 system behavior explanation (available as optional "Learn more")
- The reference translation (hidden — student must reason from source + MT)

**Scoring at L0:**
- Classification accuracy: did student confirm correctly / dispute correctly?
- ToM perspective match: did student identify the right perspective?
- Justification quality: surface / partial / deep

#### L1 — Guided (Location Hints Only)

**Purpose**: Transition from classification to detection. Student knows *where* to look but must identify *what* the error is.

**Visible to student:**
- Approximate region highlights (wider than actual span, ~±10 characters)
- Region hint label: "Look for a [MQM dimension] issue in this region"
- No error type, no severity, no ToM indicator

**Student task:**
1. Identify the exact error span within the highlighted region
2. Classify: select primary tag + type from dropdown
3. Assign severity
4. Write justification

**What is NOT shown at L1:**
- Exact span boundaries
- Error type / subtype
- Severity
- ToM perspective
- Explanations (revealed after submission)

**Scoring at L1:**
- Span overlap IoU (≥ 0.5 = match)
- Classification accuracy (exact match = full, same top-level = partial)
- Severity match (exact = full, ±1 = partial)
- Justification quality

#### L2 — Independent (No Annotations)

**Purpose**: Full independent error detection, classification, and correction.

**Visible to student:**
- Source text
- MT output (no highlighting, no hints)
- IATE glossary panel (optional, toggleable)
- MT system label

**Student task (Evaluation mode):**
1. Read source and target carefully
2. Identify all errors: select spans, classify, assign severity
3. Write justification per error
4. Submit

**Student task (PE mode):**
1. Read source and target
2. Edit the target text directly
3. Write justification for major edits
4. Submit

**Scoring at L2:**
- Precision, recall, F1 over error spans
- Per-skill detection rates
- HTER (PE mode)
- Unnecessary edits (PE mode)
- Justification quality

#### L3 — Expert (No Annotations + Clean Spans + Multi-System)

**Purpose**: Professional-level evaluation including clean-segment recognition and multi-system comparison.

**Additional features vs. L2:**
- 20–30% of segments are error-free (student must recognize correct translations)
- Multiple MT systems presented (2–3 per segment)
- Two exercise sub-types:
  - **Skill A (Analytical)**: Independent evaluation per system
  - **Skill B (Judgment)**: Comparative ranking + PE triage decision

**Scoring at L3 adds:**
- Clean segment recognition rate (true negatives)
- Over-editing penalty (edits to clean segments)
- Ranking accuracy (for Skill B)
- PE triage accuracy: did student correctly identify which system to post-edit vs. retranslate?

### 4.4 Annotation Color Scheme

Consistent across all levels. Colors are chosen for accessibility (colorblind-safe palette):

| Primary Tag | Highlight Color | Hex | Semantic Association |
|---|---|---|---|
| MISTRANSLATION | Red | `#E84855` | Meaning is wrong |
| OMISSION | Purple | `#7B2D8E` | Something is missing |
| ADDITION | Orange | `#F18F01` | Something extra |
| UNTRANSLATED | Dark red | `#9B2335` | Source language left in |
| GRAMMAR | Blue | `#2E86AB` | Structure is wrong |
| TERMINOLOGY | Teal | `#0B7A75` | Domain term is wrong |
| STYLE | Yellow-green | `#8DB580` | Reads unnaturally |
| LOCALE | Brown | `#A0522D` | Format is wrong |
| SPELLING | Light blue | `#6BAED6` | Surface form is wrong |
| PUNCTUATION | Gray | `#999999` | Punctuation issue |
| CLEAN (L3 only) | Green border | `#44AF69` | No error (correct) |

### 4.5 Annotation ↔ Error Injection Integration

The annotation system consumes the same error manifest produced by the injection pipeline. The relationship:

```
Error Injection Pipeline
    └─→ produces: List[ErrorAnnotation] per item
         │
         ├─→ L0 Navigator: show all fields except explanations
         ├─→ L1 Guided: show RegionHint only  
         ├─→ L2 Independent: show nothing (raw MT)
         └─→ L3 Expert: show nothing + add clean segments
         
Student Response
    └─→ produces: List[IdentifiedError] per item
         │
         └─→ Scoring Service: compare against ErrorAnnotation manifest
              │
              ├─→ Per-error match (IoU + classification + severity)
              ├─→ Per-skill detection rates (using primary_skill field)
              ├─→ Per-ToM detection rates (using tom_level field)
              └─→ Blind spot analysis (cross-session aggregation)
```

---

## 5. Error Injection Codebook (FR↔EN)

### 5.1 Codebook Entry Format

Each entry in the codebook is a structured record used both as documentation and as few-shot prompt material. The codebook is stored as a JSON file (`data/codebook/error_codebook_fr_en.json`) and loaded by the error injector.

```json
{
  "codebook_id": "ACC-MIST-FC-001",
  "primary_tag": "MISTRANSLATION",
  "error_type": "false_cognate",
  "mqm_path": "Accuracy > Mistranslation > False Friend",
  "severity_range": ["major", "critical"],
  "tom_level": "1st_machine",
  "primary_skill": "S3",
  
  "definition": "A word superficially similar in form to a word in the source language is used instead of the correct translation, producing an incorrect meaning transfer due to cognate interference.",
  
  "boundary_not": "If the wrong word is not a cognate but simply the wrong synonym, use word_sense instead. If the word is domain-specific, consider TERMINOLOGY > wrong_term.",
  
  "directions": ["fr_to_en", "en_to_fr"],
  
  "examples": [
    {
      "direction": "fr_to_en",
      "source": "Il assiste à la conférence depuis ce matin.",
      "reference": "He has been attending the conference since this morning.",
      "injected": "He has been <MISTRANSLATION type=\"false_cognate\" severity=\"major\" tom=\"1st_machine\" desc=\"assister à ≠ assist; means 'attend'\">assisting at</MISTRANSLATION> the conference since this morning.",
      "explanation": {
        "mt_interpretation": "The MT system mapped 'assiste à' to the English cognate 'assist at' due to surface-form similarity.",
        "actual_meaning": "In French, 'assister à' means 'to attend' or 'be present at', not 'to help'.",
        "reader_impact": "A reader would understand the subject is helping with the conference organization, not attending it.",
        "correction_rationale": "'Assister à' translates to 'attend'. The false friend 'assist' means 'aider' in French."
      }
    },
    {
      "direction": "fr_to_en",
      "source": "C'est une personne très sensible.",
      "reference": "She is a very sensitive person.",
      "injected": "She is a very <MISTRANSLATION type=\"false_cognate\" severity=\"major\" tom=\"1st_machine\" desc=\"sensible ≠ sensible; FR sensible = sensitive\">sensible</MISTRANSLATION> person.",
      "explanation": {
        "mt_interpretation": "The system preserved the surface form 'sensible' without translating it, since the word exists in both languages.",
        "actual_meaning": "French 'sensible' means 'sensitive' or 'easily affected'. English 'sensible' means 'raisonnable'.",
        "reader_impact": "A reader would think the person is practical and reasonable, not emotionally sensitive.",
        "correction_rationale": "The correct translation is 'sensitive'. The English 'sensible' would be 'raisonnable' in French."
      }
    },
    {
      "direction": "fr_to_en",
      "source": "Elle a éventuellement accepté de participer.",
      "reference": "She possibly agreed to participate.",
      "injected": "She <MISTRANSLATION type=\"false_cognate\" severity=\"major\" tom=\"1st_machine\" desc=\"éventuellement ≠ eventually; means 'possibly'\">eventually</MISTRANSLATION> agreed to participate.",
      "explanation": {
        "mt_interpretation": "The system mapped 'éventuellement' to its English lookalike 'eventually' based on form similarity.",
        "actual_meaning": "'Éventuellement' in French means 'possibly' or 'if the case arises'. 'Eventually' means 'finalement'.",
        "reader_impact": "A reader would understand she agreed after some delay, not that her agreement was uncertain.",
        "correction_rationale": "Correct: 'possibly' or 'potentially'. 'Eventually' implies temporal progression, not possibility."
      }
    }
  ]
}
```

### 5.2 Codebook Entries Summary

The full codebook contains entries for all ~35 error types. Below is the status of entries by primary tag:

| Primary Tag | # Types | # Examples (target) | FR→EN | EN→FR | Status |
|---|---|---|---|---|---|
| MISTRANSLATION | 9 | 27 | 18 | 9 | Draft |
| OMISSION | 4 | 12 | 6 | 6 | Draft |
| ADDITION | 3 | 9 | 5 | 4 | Draft |
| UNTRANSLATED | 1 | 3 | 2 | 1 | Draft |
| GRAMMAR | 7 | 21 | 7 | 14 | Draft |
| TERMINOLOGY | 3 | 9 | 5 | 4 | Draft |
| STYLE | 4 | 12 | 6 | 6 | Draft |
| LOCALE | 4 | 12 | 6 | 6 | Draft |
| SPELLING | 1 | 3 | 1 | 2 | Draft |
| PUNCTUATION | 1 | 3 | 1 | 2 | Draft |
| **TOTAL** | **37** | **111** | **57** | **54** | — |

Target: 3 examples per type, balanced across directions. EN→FR examples weighted toward Grammar (gender agreement is the dominant error pattern for EN→FR translation into L1).

### 5.3 Codebook Example Sourcing Strategy

**Existing annotated corpora to mine for examples (before manual authoring):**

| Source | Language Pair | Content | Usable for FR-EN? | Citation |
|---|---|---|---|---|
| WMT MQM data (Google) | EN→DE, ZH→EN | ~25K segment annotations with error spans, categories, severities | Pattern transfer only (no FR-EN data) | [Freitag et al. 2021, TACL] |
| SCATE corpus | EN→NL | Fine-grained error annotations with source-target alignment | Pattern transfer only | [Tezcan, Hoste & Macken 2017] |
| Anthea tutorial examples | EN→DE | Built-in tutorial examples in the annotation tool | Pattern transfer only | [google-research/google-research/anthea] |
| MTPEAS manual | EN→FR, FR→EN | PE annotation examples with 7 edit categories | Directly usable (FR-EN!) | [Bodart, Piette & Lefer 2024, Translation Spaces] |
| MultiTraiNMT coursebook | Multiple | 250+ PE activities with examples | Adaptable | [Nurminen et al. 2022, Language Science Press] |
| EU Interinstitutional Style Guide | All EU languages | Terminology and style conventions with examples | Directly usable for terminology/locale errors | [publications.europa.eu] |
| IATE database | 24 languages | 1.4M multilingual term entries | Directly usable for terminology examples | [iate.europa.eu] |

**Sourcing procedure:**
1. **Check MTPEAS manual** for existing FR-EN examples (directly reusable)
2. **Mine IATE** for institutional terminology examples (terminology error codebook entries)
3. **Adapt WMT MQM EN-DE patterns** to FR-EN equivalents (same error type, FR-specific realization)
4. **Generate candidate examples** using the injection pipeline itself (self-bootstrapping)
5. **Manual authoring** for any remaining gaps, especially FR-specific patterns (faux amis, gender agreement)
6. **Expert review** of all examples by a professional FR-EN translator

Target: 2 manually authored seed examples per type + 1 pipeline-generated example, all reviewed.

### 5.4 Explanation Sourcing Strategy

The system provides two layers of explanation (see ToM-PE spec v0.2 §4.4). Each layer draws from distinct knowledge sources:

#### Layer 1: Error-Specific Linguistic/Cultural Explanation

These explain *what* is wrong and the cultural/linguistic basis for the error. They are per-error-instance, generated at item creation time.

**Knowledge sources for Layer 1:**

| Error Category | Primary Source | Content Type |
|---|---|---|
| False cognates (FR↔EN) | Published faux ami lists: [Thody & Evans 1985; Granger & Swallow 1988]; online databases (85+ pairs documented) | Bilingual word pair + correct translation |
| Gender agreement | FR grammar references: [Grevisse & Goosse, *Le Bon Usage*]; contrastive analysis [Vinay & Darbelnet 1958/1995] | Grammatical rule + EN→FR transfer explanation |
| Article usage | Contrastive linguistics: [Chuquet & Paillard 1989, *Approche linguistique des problèmes de traduction*] | FR partitive/generic article vs. EN zero article |
| Register (tu/vous) | Sociolinguistic studies: [Fairslator/Měchura 2022]; Brown & Gilman 1960 T/V framework | Pragmatic context criteria for T/V selection |
| Locale conventions | EU Interinstitutional Style Guide; AFNOR NF Z 44-001 (French typographic conventions); ISO 8601 (dates) | Normative reference per locale-specific format |
| EU/UN terminology | IATE database; EUR-Lex glossary; UN Terminology database (UNTERM) | Authoritative term equivalents |

**Generation method**: LLM-generated from codebook definition + source/reference context, validated against the reference sources above.

#### Layer 2: MT System Behavior Explanation (Two Depth Levels)

These explain *why the MT system produces this type of error*. They are per-error-type (not per-instance), reusable across items.

**Layer 2a — Popular Science Level** (default, always shown):

Accessible explanations for translation students without NLP background. Written at "popular science" level — no jargon, concrete analogies, relatable comparisons.

| Error Pattern | Explanation Source | Example Explanation |
|---|---|---|
| False cognate errors | [Koehn & Knowles 2017] on rare words + training data patterns | "MT systems learn from millions of translated documents. When a French word looks like an English word, the system may keep the similar form because it appeared that way in training data." |
| Omission in fluent output | [Bentivogli et al. 2018] NMT vs. SMT error analysis | "Neural MT reads the whole sentence and generates a fluent translation, but sometimes 'forgets' parts of the input. Unlike older systems that translated piece by piece, neural MT can produce smooth text that's missing content." |
| Gender agreement failures | [Savoldi et al. 2021, TACL] on gender bias in MT | "When translating from English (which has no grammatical gender) to French, the system must 'guess' gender. It often defaults to masculine because masculine forms appear more frequently in training data." |
| Literal translation of idioms | [Koehn & Knowles 2017] on domain mismatch | "MT systems translate words and phrases based on patterns in their training data. Idiomatic expressions that aren't in the training data get translated word-by-word, producing nonsensical results." |
| Hallucination/Addition | [Martindale & Carpuat 2018; Raunak et al. 2021] | "LLM-based translators are trained to produce fluent text. Sometimes this 'fluency drive' causes them to add plausible-sounding content that wasn't in the original — a phenomenon called hallucination." |
| Locale format errors | Domain mismatch [Koehn & Knowles 2017] | "MT systems trained mainly on one locale's documents may apply that locale's formatting conventions. A system trained on American English data will produce US date formats even when translating French text for a UK audience." |

**Layer 2b — Technical Level** (optional, revealed via "Learn more" progressive disclosure):

Precise NLP explanations for students who want deeper understanding. Citable and technically accurate.

| Error Pattern | Technical Explanation Source | Key Technical Concepts |
|---|---|---|
| False cognates | Subword tokenization [Sennrich, Haddow & Birch 2016]; embedding space geometry | BPE splits, shared subword vocabularies in multilingual models, cognate embedding proximity |
| Omission | Attention mechanism coverage [Tu et al. 2016]; length bias in beam search [Koehn & Knowles 2017] | Soft attention coverage gap, length normalization, encoder bottleneck |
| Gender agreement | Training data statistics [Stanovsky, Webster & Ott 2019]; autoregressive left-to-right generation | Frequency-based gender defaults, lack of global agreement planning |
| Hallucination | Beam search pathologies [Koehn & Knowles 2017]; exposure bias [Ranzato et al. 2016] | Teacher forcing vs. inference discrepancy, probability mass on fluent but unfaithful sequences |
| Discourse coherence | Sentence-level translation paradigm [Toral et al. 2018; Läubli et al. 2018] | Context window limitations, anaphora resolution across segment boundaries |

**Generation method for Layer 2**: 
- Layer 2a: LLM-generated from codebook entry + curated source list above, then reviewed for accuracy and accessibility. Could also leverage xTower [Treviso et al. 2024] to generate draft explanations.
- Layer 2b: Manually authored by NLP-literate team members, citing the technical references. Stored as reusable templates per error type (not per instance).

### 5.5 Ablation Study Design: Tagging Strategy Comparison

To empirically validate our tagging format choices, we design a controlled ablation over four tagging strategies. This can be reported in the EC-TEL or CIKM paper as a technical contribution.

**Experimental conditions (between-subjects on tag format, within-subjects on error types):**

| Condition | Tag Format | Example |
|---|---|---|
| **C1: Bare** | `<error>span</error>` | `<error>assisting at</error>` |
| **C2: Categorical** | `<MISTRANSLATION>span</MISTRANSLATION>` | `<MISTRANSLATION>assisting at</MISTRANSLATION>` |
| **C3: Attributed** | `<MISTRANSLATION type="false_cognate" severity="major">span</MISTRANSLATION>` | Full attributes, no desc |
| **C4: Full (proposed)** | `<MISTRANSLATION type="false_cognate" severity="major" tom="1st_machine" desc="...">span</MISTRANSLATION>` | Full format from §1.2 |

**Metrics — Three-Layer Evaluation:**

**Layer 1 — Fully automatic (all items, all conditions, zero human cost):**
Measures *compliance* — did the LLM follow instructions?

| Metric | Type | Description |
|---|---|---|
| Parse success | Binary | Output contains valid XML matching tag schema |
| Span isolation | Binary + continuous | Diff between reference and injected confined to exactly one span; count of unintended character changes |
| QE delta | Continuous | xCOMET score drop for injected text vs. reference (higher drop = more detectable error) |
| GEMBA detection | Binary + categorical | GEMBA-MQM detects injected error AND classifies it under intended MQM category |

**Layer 2 — LLM-as-judge (all items, all conditions, moderate cost):**
A *separate* LLM (different from injector) evaluates each injection against codebook definition. Grounded in [Zheng et al. 2023, "Judging LLM-as-a-Judge"] methodology.

| Metric | Scale | Description |
|---|---|---|
| Type fidelity | Yes / Partial / No | Is the injected error actually an instance of the requested type, per codebook definition + boundary conditions? |
| Severity plausibility | Yes / No | Is the error's actual impact consistent with requested severity level? |
| Naturalness | 1–5 | Could this error plausibly come from a real MT system? (vs. artificially constructed) |
| Explanation coherence | 1–5 | Does the returned explanation correctly describe the error mechanism? (C3/C4 only) |

**Layer 3 — Expert human evaluation (stratified sample, highest cost):**
Professional FR-EN translator rates ~30 items per condition (stratified by error type, 120 total).

| Metric | Scale | Description |
|---|---|---|
| Same 4 metrics as Layer 2 | Same scales | Validates LLM-as-judge reliability (compute Cohen's κ between Layer 2 and Layer 3) |
| Pedagogical utility | 1–5 | "Would this be a useful training item for a translation student?" |
| Difficulty calibration | 1–5 | "How difficult is this error to detect?" — compared against intended difficulty from ToM/skill mapping |

**Key comparisons** (what each jump tells us):

| Comparison | Isolates the Effect of | Predicted by |
|---|---|---|
| C1 → C2 | Semantic tag names (bare → meaningful label) | [Krishna Kumar et al. 2025]: semantic anchors create rigid priors |
| C2 → C3 | Structured attributes (category only → + type + severity) | [Pan et al. 2023]: additional features improve Task Learning |
| C3 → C4 | Inline descriptions (attributes only → + desc) | [Lampinen et al. 2022]: explanations in examples improve accuracy |
| Cross-backend | Model sensitivity to format | [Wei et al. 2023]: instruction-tuned models amplify TR |

**Design details:**
- 10 error types × 3 examples each = 30 injection tasks per condition
- Test across 2–3 LLM backends (Claude, GPT-4.1, DeepSeek V3)
- Same codebook entries across conditions (only tag format varies in few-shot examples)
- Grounded in [Min et al. 2022]'s methodology of ablating demonstration components while holding format constant

**Statistical analysis:**
- Friedman test (non-parametric repeated measures) for ordinal metrics (naturalness, explanation coherence, pedagogical utility, difficulty calibration)
- McNemar's test for binary metrics (parse success, span isolation, GEMBA detection)
- Effect sizes reported as Kendall's W
- LLM-as-judge validation: Cohen's κ between Layer 2 and Layer 3 ratings on the same 120-item sample
- 30 items × 4 conditions × 3 backends = 360 injection runs total (Layer 1+2); 120 human-rated (Layer 3)

**Expected findings** (based on literature predictions):
- C1 (Bare) will produce the most diverse but least controlled errors
- C2 (Categorical) will show the largest jump in injection accuracy due to semantic activation [Krishna Kumar et al. 2025]
- C3→C4 will show marginal improvement in injection accuracy but significant improvement in explanation quality [Lampinen et al. 2022]
- Instruction-tuned models (Claude, GPT-4.1) will show larger C1→C2 gains than base/reasoning models [Wei et al. 2023]

---

## 6. Annotation Interface Specification

### 6.1 Student Annotation Workflow (Evaluation Mode)

The student-facing annotation interface differs by scaffolding level but shares a common structure:

```
┌──────────────────────────────────────────────────────────────┐
│  SOURCE TEXT (always visible)                                 │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Le ministre de la Santé et de la Prévention a annoncé  │ │
│  │ de nouvelles mesures pour lutter contre la pandémie.    │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  MT TRANSLATION   [MT System: Google Translate]   [EN→FR]    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ The Minister of Health announced new measures to fight  │ │
│  │ against the pandemic.                                   │ │
│  │                                                         │ │
│  │  [Level-dependent highlighting / interaction here]      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  IATE GLOSSARY (collapsible)                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ mesures → measures (EU term: "measures")                │ │
│  │ lutter contre → combat/fight against                    │ │
│  │ pandémie → pandemic                                     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  YOUR ANNOTATIONS                                            │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Error 1: [selected span]                                │ │
│  │   Category: [dropdown]  Severity: [radio]               │ │
│  │   Confidence: [Low / Medium / High]                     │ │
│  │   Justification: [text input]                           │ │
│  │     "What did the MT misunderstand?"                    │ │
│  │     "What was the author's intent?"                     │ │
│  │     "How would a reader misinterpret this?"             │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │ [+ Add another error]                                   │ │
│  │ [✓ No more errors in this segment]                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  [Submit for Scoring]                                        │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 Justification Prompt Variants

Two modes are available (teacher configures per exercise):

**Mode A — Free-text (default):**
```
Before seeing the feedback, explain your reasoning for each 
error you identified:
- What do you think the MT system misunderstood about the source?
- What was the author's actual intent?
- How would a target reader misinterpret this translation?
[Free text input]
```

**Mode B — Structured ToM prompts:**
```
For this error:
1. Which perspective matters most? 
   ○ Machine interpretation  ○ Author intent  ○ Reader inference
2. What the MT "thought": [text input]
3. What the author meant: [text input]  
4. What a reader would conclude: [text input]
```

Both modes are A/B tested; the teacher can assign Mode A or B per exercise.

### 6.3 Feedback Display (Post-Submission)

After submission, the interface reveals:

```
┌──────────────────────────────────────────────────────────────┐
│  FEEDBACK                                                     │
│                                                              │
│  Error 1: "et de la Prévention" — OMISSION (modifier)        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Status: ✗ MISSED                                       │ │
│  │  Severity: major                                        │ │
│  │  ToM: 🟢 Author intent                                  │ │
│  │  Skill: S4 (Completeness Verification)                  │ │
│  │                                                         │ │
│  │  LAYER 1 — Error Explanation:                           │ │
│  │  "The MT dropped 'et de la Prévention' from the         │ │
│  │   minister's title. The source refers to the Minister   │ │
│  │   of Health AND Prevention, but the translation only    │ │
│  │   says 'Minister of Health'. A reader would not know    │ │
│  │   this ministry covers prevention policy."              │ │
│  │                                                         │ │
│  │  LAYER 2 — Why MT Does This (expandable):               │ │
│  │  ▸ "NMT systems sometimes drop content from long noun   │ │
│  │    phrases, especially when the omitted element is       │ │
│  │    syntactically optional. The output remains fluent,    │ │
│  │    making the omission hard to detect without careful    │ │
│  │    source comparison."                                  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  SESSION SUMMARY                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Detection: 2/3 errors found (67%)                      │ │
│  │  Over-editing: 0 false positives                        │ │
│  │  By skill:                                              │ │
│  │    S2 Grammar: 1/1 ✓   S3 Meaning: 1/1 ✓              │ │
│  │    S4 Completeness: 0/1 ✗                               │ │
│  │  Justification: 1 deep, 1 partial                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Integration Points

### 7.1 How This Spec Connects to ToM-PE System Spec v0.2

| This Spec Section | Updates/Replaces in v0.2 |
|---|---|
| §1 Tag Format | New — extends §4.3 Error Injector with concrete prompt format |
| §2 Prompt Architecture | New — replaces the generic injection procedure in §4.3 |
| §3 Competency Mapping | New — fills the gap identified in v0.2 §12 Open Questions |
| §4 Annotation System | Extends v0.2 §5 Student Interface with L0–L3 scaffolding detail |
| §5 Codebook + Sourcing | New — provides the data structure for `data/codebook/` + sourcing strategies |
| §5.4 Explanation Sourcing | New — specifies knowledge sources for both explanation layers |
| §5.5 Ablation Study | New — empirical validation design for tagging format choices |
| §6 Annotation Interface | Extends v0.2 §5.1 Session Flow with level-specific views |

### 7.2 Files to Implement

| File | Purpose | Dependencies |
|---|---|---|
| `data/codebook/error_codebook_fr_en.json` | Full codebook with 37 types × 3 examples | None |
| `data/codebook/tag_schema.json` | Tag inventory (§1.3) for validation | None |
| `data/codebook/layer2a_explanations.json` | Per-error-type popular science explanations (§5.4) | tag_schema |
| `data/codebook/layer2b_explanations.json` | Per-error-type technical explanations (§5.4) | tag_schema |
| `pipeline/error_injector.py` | Two-step prompt + verification (§2) | Codebook, tag schema |
| `pipeline/prompt_templates/` | Step 1 and Step 2 prompt templates (§2.2–2.3) | Codebook |
| `pipeline/explanation_generator.py` | Layer 1 + Layer 2a generation from codebook + sources | Codebook, Layer 2a templates |
| `schemas/annotation.py` | ErrorAnnotation, RegionHint (§4.2) | Pydantic |
| `schemas/competency.py` | Skill definitions, mapping matrix (§3) | Pydantic |
| `services/scoring.py` | Per-skill scoring using competency map (§3) | annotation.py, competency.py |
| `services/progression.py` | Mastery criteria checks (§3.5) | competency.py |
| `interfaces/student_app.py` | Level-specific views (§6) | Gradio + custom span selector |
| `interfaces/components/span_selector.py` | Custom Gradio component for span selection + classification | Gradio, JS |
| `experiments/ablation_tagging.py` | Ablation study runner (§5.5) | Codebook, error_injector |

### 7.3 Resolved Design Questions (This Version)

| # | Question | Decision | Grounding |
|---|---|---|---|
| Q1 | Codebook example sourcing | Hybrid: check existing sources first (MTPEAS, IATE, WMT patterns), then manual + pipeline-generated (§5.3) | Minimizes manual effort while ensuring quality |
| Q2 | Tag format validation | Ablation study across 4 conditions with 3-layer evaluation (§5.5); run before committing codebook | [Min et al. 2022] methodology; reported in CIKM demo paper |
| Q3 | Direction-specific types | Yes — `dir` attribute added (§1.2.2) | Gender agreement is EN→FR only; false cognates weighted FR→EN |
| Q4 | Layer 2 explanation depth | Two levels: popular science (always shown) + technical (progressive disclosure via "Learn more") (§5.4) | [Kalyuga 2007] expertise reversal: novices need accessible; experts need precise |
| Q5 | Annotation interface | Custom Gradio component for span selection (constrained but integrates natively) | Start minimal, escalate if needed |
| Q6 | Severity per error type | Context-dependent, not fixed; codebook provides `severity_range`; teacher selects per exercise (§1.2.1) | MQM official position [Lommel et al. 2014] |
| Q7 | Layer 2b authoring | LLM-generated from technical papers ([Koehn & Knowles 2017], [Bentivogli et al. 2018]) + expert review; teacher can manually correct via teacher interface | Balances effort with accuracy |
| Q8 | xTower integration | Yes — integrate as benchmark for explanation generation + as comparison point for QE validation | [Treviso et al. 2024] is the state-of-the-art for explainable MT error annotation |
| Q9 | Ablation venue | CIKM 2026 demo paper (technical evaluation section) | System design contribution fits demo format |
| Q10 | Codebook versioning | Semantic versioning (v1.0.0) with changelog, stored in repository alongside tag schema | Standard practice for evolving data artifacts |

### 7.4 Open Questions (Remaining)

1. **GUI design brainstorm needed**: The teacher interface for reviewing/correcting Layer 2 explanations, the student annotation interface at each scaffolding level, and the blind spot analytics dashboard all need detailed wireframe design. Deferring to a dedicated GUI design session.

2. **LLM-as-judge prompt calibration**: The Layer 2 evaluation in the ablation study (§5.5) requires its own validated prompt. Need to design and validate the judge prompt against the expert human ratings before running the full ablation. This is a prerequisite for the CIKM evaluation section.

3. **xTower deployment logistics**: xTower is a 13B model requiring GPU inference. Options: (a) run locally on a GPU machine, (b) use a hosted inference endpoint (HuggingFace Inference API), (c) pre-compute all xTower outputs offline for the evaluation only. Decision depends on available compute.

4. **Clean segment sourcing**: For L3 Expert exercises, we need segments where the MT is actually correct (no errors). Do we use real MT output that xCOMET + GEMBA both rate as error-free, or do we use the human reference translation itself as a "MT output"? The former is more ecologically valid; the latter guarantees ground truth.

---

## Appendix A: FR-EN False Cognate Reference List

High-frequency false cognates for codebook examples (compiled from published lists):

| French | Wrong English (cognate) | Correct English | Reverse Direction |
|---|---|---|---|
| actuellement | actually | currently | currently ≠ actuellement (yes) |
| assister (à) | assist | attend | attend ≠ assister (partially) |
| blesser | bless | injure/wound | — |
| demander | demand | ask/request | demand = exiger |
| éventuellement | eventually | possibly | eventually = finalement |
| librairie | library | bookshop | library = bibliothèque |
| prétendre | pretend | claim | pretend = faire semblant |
| rester | rest | stay/remain | rest = se reposer |
| résumer | resume | summarize | resume = reprendre |
| sensible | sensible | sensitive | sensible = raisonnable |
| sympathique | sympathetic | likeable/nice | sympathetic = compatissant |
| regarder | regard | look at/watch | regard = considérer |
| avertissement | advertisement | warning | advertisement = publicité |
| coin | coin | corner | coin = pièce de monnaie |
| figure | figure | face | figure = chiffre/silhouette |
| location | location | rental | location = emplacement |
| monnaie | money | change/currency | money = argent |
| patron | patron | boss | patron = mécène |
| phrase | phrase | sentence | phrase = expression |
| travail | travel | work | travel = voyage |

---

## Appendix B: MQM Severity Weights

| Severity | Weight | FR-EN Pedagogical Note |
|---|---|---|
| Neutral | 0 | Acceptable alternative translation; used for style preferences |
| Minor | 1 | Noticeable but does not impede understanding (e.g., article error FR→EN) |
| Minor (Punctuation) | 0.1 | Locale-specific punctuation (guillemets, spacing before colons) |
| Major | 5 | Changes meaning or causes confusion (e.g., false cognate, omission of clause) |
| Critical | 25 | Renders content unfit (e.g., legal term reversal, safety-critical mistranslation) |
