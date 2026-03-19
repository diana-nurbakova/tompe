# ToM Framework — EC-TEL Experimental Specification
## Retroactive Validation Against Published Empirical Data
### v1.0 (March 2026)

---

## 1. Overview

This document specifies five experiments that validate the ToM framework's predictions against published empirical data. No new student data is required. Each experiment tests a specific claim derived from the framework against independently published findings from different research groups, language pairs, and years.

**Core logic**: The framework is validated not by collecting new data, but by demonstrating that it provides the first unified theoretical account of multiple disconnected empirical findings. Convergence across independent studies constitutes evidence for the framework's explanatory power.

---

## 2. MQM-to-ToM Mapping (Foundation for All Experiments)

All experiments rely on mapping published error categories to our 7-skill / ToM-level model. This mapping must be declared upfront and applied consistently.

### 2.1 Primary Mapping

| ToM Level | Order | Skills | MQM Categories | Cognitive Demand |
|---|---|---|---|---|
| 1st_machine (form) | 1st | S1 Surface, S2 Grammar | Spelling, Punctuation, Grammar, Word form | Recognise surface deviance from TL norms |
| 1st_machine (meaning) | 1st-2nd | S3 Meaning | Mistranslation, Wrong sense, False cognate, Number | Compare ST-TT meaning correspondence |
| 1st_author | 2nd | S4 Completeness | Omission, Addition, Untranslated | Recover author intent, detect absence |
| 2nd_reader | 3rd | S5 Terminology, S6 Pragmatic | Terminology, Register, Style, Locale | Model reader inference from TT |
| recursive | 4th+ | S7 Discourse | Coherence, Cohesion, Connectives | Multi-sentence, multi-agent reasoning |

### 2.2 Mapping Rules for External Studies

Many studies use different taxonomies. We apply these rules:

1. If a study uses MQM directly: map subcategories per §2.1
2. If a study uses Temnikova's 10-level scheme: map each level to the closest skill (documented in Exp 1)
3. If a study reports broad categories (e.g., "accuracy" vs. "fluency"): Fluency → S1+S2, Accuracy → S3+S4, other → S5+S6
4. If mapping is ambiguous: report the ambiguity and test with both possible mappings
5. S7 Discourse is only scored when studies report inter-sentential or document-level errors

### 2.3 ToM Ordinal Scale

For rank correlation tests, the ToM ordering is:

```
S1 < S2 < S3 < S4 ≤ S5 ≤ S6 < S7
```

S4, S5, S6 are treated as tied at the same ordinal rank (all require 2nd+ order ToM). For analyses requiring a strict ordering, we use: S1=1, S2=2, S3=3, S4=4, S5=4, S6=4, S7=5.

---

## 3. Experiment 1: ToM Ordering vs. Published Difficulty Rankings

### 3.1 Prediction

Error types requiring higher-order ToM are harder to detect and require more cognitive effort.

### 3.2 Data Sources

#### Source 1A: Temnikova (2010) — Cognitive Difficulty Ranking

10-level ranking from easiest to hardest, derived from psycholinguistic literature and validated across Arabic, Russian, Spanish, Bulgarian (Temnikova et al. 2016, 92% inter-annotator agreement).

| Temnikova Rank | Error Type | Our Skill | ToM Level |
|---|---|---|---|
| 1 (easiest) | Correct word, incorrect form | S2 | 1st_machine |
| 2 | Incorrect style synonym | S6 | 2nd_reader |
| 3 | Incorrect word | S3 | 1st_machine (meaning) |
| 4 | Extra word | S4 | 1st_author |
| 5 | Missing word | S4 | 1st_author |
| 6 | Idiomatic expression | S6 | 2nd_reader |
| 7 | Wrong punctuation | S1 | 1st_machine |
| 8 | Missing punctuation | S1 | 1st_machine |
| 9 | Word order (word level) | S2 | 1st_machine |
| 10 (hardest) | Word order (phrase level) | S2/S7 | 1st_machine / recursive |

**Note**: Temnikova's ranking reflects PE difficulty (effort to correct), not detection difficulty. These are related but not identical. The framework predicts the correlation should still hold because higher-ToM errors are both harder to detect and harder to correct.

**Complication**: Temnikova rank 2 ("incorrect style synonym") maps to S6 (2nd_reader) but is ranked easy. This may reflect that *correcting* a style issue is simple (swap one word) even though *detecting* it requires reader modeling. We report this as a partial mismatch and discuss the detection-vs-correction distinction.

#### Source 1B: Daems et al. (2017) — Cognitive Effort by Error Type

13 professionals + 10 students, EN→NL, eye-tracking + keystroke logging. Reports fixation duration, pause ratio, production units per error type.

Key data to extract (from their Tables 3–5):
- Fixation duration by error type (proxy for cognitive load)
- HTER contribution by error type
- Student vs. professional interaction (used in Exp 3)

Mapping their categories:
- "Coherence" → S7
- "Meaning shift" → S3
- "Grammar/structural" → S2
- "Agreement/spelling" → S1
- "Style" → S6

#### Source 1C: ES→EN Trainee Detection Rates

From the empirical compendium (cited in multiple sources):
- Syntax errors: 93% detection → S1/S2
- Mistranslation: 80% → S3
- Omission: 67% → S4

#### Source 1D: Yamada (2019) — Student Correction Rates

28 students, EN→JA, Google NMT. Overall 68% correction rate. Per-type breakdown available for X1 (addition), X2 (omission), X3 (mistranslation), X4 (grammar), and others.

#### Source 1E: Popović (2018) — EN-DE/EN-SR Error Analysis

Reports error frequencies and types for NMT vs. PBMT. Categories map to our skills.

### 3.3 Analysis

For each source:
1. Extract the difficulty/effort measure per error type
2. Map error types to ToM levels using §2.1
3. Compute Kendall's τ between ToM ordinal rank and observed difficulty rank
4. Report τ, p-value, and n (number of error types in the comparison)

**Aggregate test**: Pool all sources into a single meta-analytic rank correlation. Each source provides one (ToM rank, observed rank) pair per error type. Weight by sample size of the original study.

### 3.4 Expected Outcome

τ > 0 across most sources, indicating positive correlation between ToM level and difficulty. Strength likely moderate (τ ≈ 0.4–0.7) because the mapping is approximate and some error types span multiple ToM levels.

### 3.5 What Would Disconfirm

τ ≤ 0 in multiple sources, or a consistent pattern where high-ToM errors are easier than low-ToM errors. The Temnikova rank 2 (style synonym) anomaly is expected; if more than 2 out of 5 sources show systematic inversions, the ordering needs revision.

---

## 4. Experiment 2: Fluency Paradox as ToM-Selective Detection Impairment

### 4.1 Prediction

NMT's fluency improvement selectively impairs detection of high-ToM errors (S3+: meaning, omission, pragmatic) while leaving low-ToM error detection (S1–S2: surface, grammar) largely unaffected. Mechanism: fluent surface form satisfies 1st-order machine modeling, disengaging higher-order ToM processes.

### 4.2 Data Sources

#### Source 2A: Yamada (2019)

NMT correction rate: 68%. SMT correction rate: 77%. The 9-point drop should be concentrated in high-ToM categories.

Data needed: per-type correction rates for NMT vs. SMT. If Yamada reports these (check Tables 4–6 in the original paper), compute:
- Low-ToM drop = SMT_detection(S1,S2) − NMT_detection(S1,S2)
- High-ToM drop = SMT_detection(S3+) − NMT_detection(S3+)

Prediction: High-ToM drop >> Low-ToM drop.

#### Source 2B: Bentivogli et al. (2018)

EN→DE, EN→FR. NMT reduced morphology and reordering errors (low-ToM) by ~50% vs. best PBMT. Lexical errors and omissions (high-ToM) were less reduced.

Data needed: error count reduction rates by category for NMT vs. PBMT.
- Morphology/reordering reduction → low-ToM improvement
- Lexical/omission reduction → high-ToM improvement

Note: This source reports MT *output* error rates, not student *detection* rates. But the framework predicts both: fewer low-ToM errors in the output AND lower detection rates for remaining high-ToM errors.

#### Source 2C: Van Brussel et al. (2018) — SCATE Corpus

EN→NL. NMT total errors ≈ half of SMT. But:
- Fluency errors: NMT < 50% of SMT (large reduction)
- Accuracy errors: NMT reduction smaller
- New category: "semantically unrelated" mistranslations (high-ToM)

Data needed: error counts by category for NMT vs. SMT.

#### Source 2D: Koponen, Salmi & Nikulin (2019)

33 students, EN→FI. Overlooked errors: NMT 49, SMT 56, RBMT 80. Edit type distributions differ significantly across systems.

Data needed: overlooked error breakdown by type for each MT system.

### 4.3 Analysis

For each source:
1. Compute the NMT improvement ratio per ToM level: R(ToM_level) = (SMT_measure − NMT_measure) / SMT_measure
2. Test whether R(high-ToM) < R(low-ToM) using paired comparison or chi-squared
3. Compute the interaction effect size (Cohen's d or odds ratio)

**Integrative visualisation**: Bar chart with ToM levels on x-axis, NMT improvement ratio on y-axis, one cluster per study. The framework predicts a declining slope from left (low-ToM, large improvement) to right (high-ToM, small or negative improvement).

### 4.4 Expected Outcome

Consistent asymmetry across sources: NMT improves low-ToM error rates substantially but high-ToM error rates modestly or not at all. This pattern has been described qualitatively in the literature ("NMT produces more fluent but not more accurate output") but never attributed to a cognitive mechanism. The ToM framework provides that mechanism.

### 4.5 What Would Disconfirm

NMT improving high-ToM detection rates equally or more than low-ToM. This would suggest the fluency paradox is not ToM-mediated but operates through some other mechanism (e.g., general cognitive load reduction).

---

## 5. Experiment 3: Experience × ToM Interaction

### 5.1 Prediction

The expert-novice performance gap widens with ToM level. Experts outperform novices most on high-ToM errors (pragmatic, coherence) and least on low-ToM errors (surface, grammar). Mechanism: expertise in PE is fundamentally the development of multi-agent perspective-taking capacity.

### 5.2 Data Sources

#### Source 3A: Daems et al. (2017) — Critical Source

13 professionals + 10 students, EN→NL. The key finding: different error types predict different effort indicators, and the student-professional interaction varies by error type.

Data needed (from their regression models):
- Student fixation duration increase per error type vs. professional increase
- Specifically: "coherence issues increased duration more for professionals than students" (professionals detected them; students missed them entirely)
- "Agreement and spelling errors impacted students' HTER more than professionals'" (students respond mechanically to surface errors)

This directly tests our prediction: the experience gap reverses direction across the ToM hierarchy. For low-ToM errors, students over-invest effort (high HTER impact). For high-ToM errors, professionals show effort but students show none (they don't even see the error).

#### Source 3B: Stasimioti & Sosoni (2021)

10 experienced + 10 novice translators, EN→EL. Experienced translators significantly faster (p = 0.02) but made significantly more redundant edits (M=8 vs. M=5, p = 0.03).

Data needed: if per-type edit breakdown is available, categorize redundant edits by ToM level. If only aggregate data, use as supporting evidence for the over-editing prediction (Exp 4).

#### Source 3C: De Almeida (2013)

20 participants, EN→FR/PT-BR. Most experienced translators made highest number of essential changes but also more preferential changes.

Data needed: essential vs. preferential changes by error type if available. If only aggregate: essential changes = high-ToM corrections, preferential = low-ToM surface preferences.

#### Source 3D: Schaeffer et al. (2019)

Students correct fewer errors and take longer per correction. If per-type data available, categorize by ToM level.

### 5.3 Analysis

For each source with per-type expert-novice data:
1. Compute the gap: Gap(type) = Expert_performance(type) − Novice_performance(type)
2. Map error types to ToM levels
3. Compute correlation between ToM level and Gap magnitude
4. Test for significance (Kendall's τ or Spearman's ρ)

For Daems (the strongest source): extract the interaction coefficients from their regression models. The interaction term (experience × error_type) predicting effort is exactly what the ToM framework predicts.

**Key visualisation**: Scatter plot with ToM level on x-axis, expert-novice gap on y-axis, one point per error type per study. The framework predicts a positive slope.

### 5.4 Expected Outcome

Positive correlation between ToM level and the experience gap. The Daems finding (coherence effort higher for professionals, surface effort higher for students) should map cleanly to the ToM hierarchy with professionals engaging higher-order ToM that students lack.

### 5.5 What Would Disconfirm

Flat or negative correlation. If experts and novices differ equally across all error types, then expertise is not ToM-structured but rather a uniform scaling of all evaluation abilities.

---

## 6. Experiment 4: Over-Editing as Misdirected ToM

### 6.1 Prediction

Unnecessary edits concentrate on low-ToM dimensions (S1–S2: surface form and grammar) where the student's 1st-order machine model generates false alarms ("MT systems make errors like this") without engaging the author model ("but the MT correctly captured the meaning here"). Over-editing is rare on high-ToM dimensions because students lack the confidence to change meaning-level content they cannot fully evaluate.

### 6.2 Data Sources

#### Source 4A: Koponen & Salmi (2017)

5 students, EN→FI. 34% of all edits unnecessary. The predominant unnecessary edit types: word-order changes and pronoun deletions.

Mapping: Word-order changes → S2 (grammar, 1st_machine). Pronoun deletions → S2/S4 (grammar/completeness). The framework predicts these cluster in low-to-mid ToM.

#### Source 4B: Koponen, Salmi & Nikulin (2019)

33 students, EN→FI. ~38% unnecessary edits. Breakdown by edit type available: word form changes, substitutions, insertions, deletions.

Data needed: categorise each edit type by ToM level, compute the proportion of unnecessary edits at each level.

#### Source 4C: Nitzke & Gros (2020)

1 unnecessary change per 22.3 words. 45.16 preferential changes per 1,008 words, with categorisation.

Data needed: preferential change categories mapped to ToM levels.

#### Source 4D: De Almeida (2013)

16–25% unnecessary edits for professionals. Per-type breakdown if available.

#### Source 4E: Mellinger & Shreve (2016)

60% of exact TM matches changed (none needed changing), 74% of fuzzy matches corrected (all needed correction). This is aggregate but powerfully illustrates the false-alarm pattern.

### 6.3 Analysis

For each source:
1. Categorise unnecessary edits by ToM level
2. Compute proportion of unnecessary edits at each level
3. Test whether unnecessary edit proportion decreases with ToM level (chi-squared or Cochran-Armitage trend test)

**Key visualisation**: Stacked bar chart. X-axis: ToM level (low to high). Y-axis: proportion of edits that are unnecessary vs. necessary. The framework predicts the "unnecessary" proportion shrinks from left to right.

### 6.4 Expected Outcome

Unnecessary edits concentrated in S1–S2 (surface, grammar). Few unnecessary edits in S3+ (meaning, omission, pragmatic). The mismatch between over-editing on surface and under-editing on meaning reflects the asymmetry between 1st-order machine modeling (overdeveloped) and higher-order ToM (underdeveloped).

### 6.5 Novel Insight

This experiment offers the framework's most novel prediction. Over-editing has been documented extensively but never explained cognitively. The ToM framework provides a specific mechanism: over-editing is not random or uniform. It is the behavioural signature of a student who has developed a strong 1st-order machine model ("I know what MT errors look like") without developing the corresponding author model ("but the MT got it right this time"). Recognising this pattern has direct pedagogical implications: training should include clean-segment exercises (our L3 design) to calibrate the machine model against reality.

---

## 7. Experiment 5: Integrative Convergence Table

### 7.1 Purpose

Synthesise findings from Experiments 1–4 into a single convergence table. Each row is a skill/ToM level. Each column is a data source. Each cell indicates whether the published finding aligns with (✓), partially aligns with (~), contradicts (✗), or lacks data for (—) the framework's prediction.

### 7.2 Table Structure

```
| Skill | ToM | Exp 1    | Exp 2      | Exp 3      | Exp 4      |
|       |     | Diffi-   | Fluency    | Expert-    | Over-      |
|       |     | culty    | paradox    | novice gap | editing    |
|       |     | ordering | asymmetry  | by ToM     | by ToM     |
|-------|-----|----------|------------|------------|------------|
| S1    | 1st | Tem Dam  | Yam Ben    | Dae Sta    | Kop Nit    |
|       |     | Yam Kop  | VBr Kop    | DeA Sch    | DeA Mel    |
| S2    | 1st | ...      | ...        | ...        | ...        |
| S3    | 1-2 | ...      | ...        | ...        | ...        |
| S4    | 2nd | ...      | ...        | ...        | ...        |
| S5-S6 | 3rd | ...      | ...        | ...        | ...        |
| S7    | 4th | ...      | ...        | ...        | ...        |
```

Each cell contains abbreviated source references (Tem = Temnikova, Dam = Daems, Yam = Yamada, etc.) with ✓/~/✗.

### 7.3 Aggregate Statistics

Count across the table:
- Total ✓ cells
- Total ~ cells
- Total ✗ cells
- Total — cells
- Convergence ratio: ✓ / (✓ + ✗)

A convergence ratio above 0.80 across 4 experiments and 5+ sources per experiment constitutes strong retroactive validation. Below 0.60 would indicate the framework needs revision.

### 7.4 Visualisation

Heatmap version of the convergence table, with colour intensity representing the strength of evidence (number of ✓ sources) at each Skill × Experiment cell. This becomes a key figure in the paper.

---

## 8. Data Extraction Protocol

### 8.1 Sources to Obtain Full Text

| Ref | Full Reference | Status | Key Tables/Figures |
|---|---|---|---|
| Temnikova 2010 | Cognitive evaluation approach for controlled language PE experiment | To extract | Difficulty ranking table |
| Temnikova+ 2016 | Cross-linguistic validation | To extract | Agreement data |
| Daems+ 2017 | Frontiers in Psychology: MT error types and PE effort | Available | Tables 3–5, regression models |
| Yamada 2019 | JoSTrans: Impact of Google NMT on PE by students | Available | Per-type correction rates |
| Bentivogli+ 2018 | Neural vs. phrase-based MT quality | To extract | Error reduction by category |
| Van Brussel+ 2018 | SCATE fine-grained error analysis | To extract | NMT vs. PBMT error counts |
| Koponen+ 2017 | Unnecessary edits | To extract | Edit categorisation |
| Koponen+ 2019 | Product and process analysis of PE corrections | Available | Per-system edit types |
| Stasimioti+ 2021 | Translation vs. PE of NMT | To extract | Edit type breakdown |
| De Almeida 2013 | Productivity and quality in PE | To extract | Essential vs. preferential |
| Nitzke+ 2020 | Over-editing analysis | To extract | Preferential change categories |
| Mellinger+ 2016 | TM match editing rates | To extract | Exact vs. fuzzy match data |
| Popović 2018 | Language-related issues NMT vs. PBMT | Available | Error type distributions |
| Schaeffer+ 2019 | Revision task comparison | To extract | Student vs. professional data |

### 8.2 Data Extraction Template

For each source, extract into a standardised JSON:

```json
{
  "source": "Daems2017",
  "n_participants": {"students": 10, "professionals": 13},
  "language_pair": "EN-NL",
  "mt_system": "SMT",
  "measures": [
    {
      "error_type": "coherence",
      "our_skill": "S7",
      "tom_level": "recursive",
      "tom_rank": 5,
      "measure_name": "fixation_duration_ms",
      "student_value": null,
      "professional_value": null,
      "notes": "Professionals showed increased duration; students did not"
    }
  ]
}
```

This gives us a structured dataset for all five experiments.

---

## 9. Statistical Tests Summary

| Experiment | Primary Test | Secondary Test | N (error types × sources) |
|---|---|---|---|
| Exp 1 | Kendall's τ (ToM rank vs. difficulty) | Per-source and aggregate | ~5 types × 5 sources = 25 |
| Exp 2 | Paired comparison: NMT improvement low-ToM vs. high-ToM | Chi-squared on category proportions | ~4 sources × 2 ToM groups |
| Exp 3 | Kendall's τ (ToM rank vs. expert-novice gap) | Interaction coefficient from Daems regression | ~5 types × 3–4 sources |
| Exp 4 | Cochran-Armitage trend test (unnecessary edit rate vs. ToM) | Chi-squared by category | ~5 types × 3–4 sources |
| Exp 5 | Convergence ratio: ✓ / (✓ + ✗) | Binomial test against chance | ~30 cells |

### 9.1 Multiple Comparisons

Five experiments. Within each, we report per-source results separately (no correction needed as they are independent replications). The aggregate tests across experiments (Exp 5 convergence ratio) use a single summary statistic. Bonferroni correction across the 5 aggregate tests: p < 0.01 required.

---

## 10. Integration Into Paper Structure

### 10.1 Where Each Experiment Appears

| Paper Section | Experiment(s) | Role |
|---|---|---|
| §3 Framework | Exp 1 results woven in | "The framework predicts this ordering; Temnikova (2010) independently found..." |
| §4 Scaffolding Design | Exp 4 motivation | "Over-editing concentrates on low-ToM errors, motivating clean-segment exercises" |
| §5 Validation | All 5, systematically | Main results section |
| §5.1 | Exp 1 (ordering) | Core prediction |
| §5.2 | Exp 2 (fluency paradox) | Explanatory power |
| §5.3 | Exp 3 (experience × ToM) | Developmental prediction |
| §5.4 | Exp 4 (over-editing) | Novel prediction |
| §5.5 | Exp 5 (convergence table) | Synthesis |
| Running examples | Exp 2 illustration | False cognate traced through the fluency paradox |

### 10.2 Key Figures for Paper

| Figure | Content | Section |
|---|---|---|
| F1 | The multi-agent ToM model (5 agents, nested intentionality) | §3 |
| F2 | MQM-to-ToM mapping table with skill hierarchy | §3 |
| F3 | Running example: false cognate through 5 agents | §3 |
| F4 | ToM ordering vs. published difficulty: scatter plot | §5.1 |
| F5 | Fluency paradox asymmetry: improvement ratio by ToM level | §5.2 |
| F6 | Convergence heatmap (Exp 5) | §5.5 |
| F7 | Scaffolding progression (L0→L2): running example | §4 |

### 10.3 Timeline

| Date | Task |
|---|---|
| Mar 20–22 | Obtain full texts; begin data extraction |
| Mar 23–26 | Complete data extraction for all 14 sources into JSON |
| Mar 27–30 | Run Exp 1–4 analyses; produce figures F4, F5 |
| Mar 31–Apr 3 | Build convergence table (Exp 5); write §5 |
| Apr 4–7 | Write §1–4; integrate running examples; produce F1–F3, F6–F7 |
| Apr 8–10 | Revise, polish, check formatting, submit |
