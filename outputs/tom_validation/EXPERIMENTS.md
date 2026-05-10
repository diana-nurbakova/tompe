# ToM Hierarchy Validation — Experiment Documentation

**Output directory:** [outputs/tom_validation/](.)
**Pipeline source:** [experiments/tom_validation/](../../experiments/tom_validation/)
**Spec:** [specs/tom-validation-experiment-spec.md](../../specs/tom-validation-experiment-spec.md)
**Run date (artifacts):** 2026-04-07

---

## 1. Purpose

The pipeline validates the **Theory-of-Mind (ToM) error hierarchy** used in ToM-PE: an ordinal scale (L0–L3) that ranks MT post-editing errors by the cognitive depth of perspective-taking required to detect and repair them.

The validation reuses an external, fully-public expert-annotation dataset (described in §2) where each segment-system pair has been independently annotated by 3 of 6 expert raters. We treat **inter-rater detection agreement** as a behavioural difficulty proxy: if the hierarchy is valid, errors that demand higher-order perspective-taking should be detected by *fewer* of the 3 raters. **No ToM-PE in-house data is used in this validation** — the experiment relies exclusively on the public WMT 2020 MQM corpus.

### Hypotheses tested

| ID | Hypothesis | Test |
|----|-----------|------|
| **H1** (primary) | Detection rate decreases monotonically with ToM level. | V1 — Jonckheere–Terpstra |
| **H2** (secondary) | The ToM effect persists after controlling for severity, segment length, system quality, and crossed random effects of `system` and `doc`. | V3 — ordinal regression / CLMM |
| **H3** (exploratory) | Raters differ in their sensitivity to ToM-level difficulty. | V4 — logistic GLMM with random slopes |

A monotonic-decrease (V1) and a 4-way distributional difference (V2) are tested non-parametrically; covariate-adjusted analyses (V3, V4) are tested with mixed-effects models. Eight pre-registered sensitivity analyses (S1–S8) probe robustness to category-mapping ambiguity, severity weighting, IoU threshold, and per-system heterogeneity.

---

## 2. Dataset

### 2.1 Identity and provenance

| Field | Value |
|-------|-------|
| **Name** | WMT 2020 MQM Human Evaluation — `newstest2020`, English → German |
| **Reference** | Freitag, Foster, Grangier, Ratnakar, Tan & Macherey (2021). *Experts, Errors, and Context: A Large-Scale Study of Human Evaluation for Machine Translation.* TACL. |
| **Source repository** | `github.com/google/wmt-mqm-human-evaluation` |
| **License** | Apache 2.0 |
| **File on disk** | [data/wmt-mqm/mqm_newstest2020_ende.tsv](../../data/wmt-mqm/mqm_newstest2020_ende.tsv) |
| **Format** | Tab-separated, 79,024 data rows + 1 header |

The corpus is an **expert MQM re-annotation of the WMT 2020 News Translation shared task** EN→DE submissions. The original WMT crowd ratings are *not* used here; we use Google's professionally re-annotated MQM layer (the data underlying Freitag et al.'s "Experts, Errors, and Context"), which provides span-level error markup with MQM categories and severities.

### 2.2 What's in the file

Schema (one error annotation per row):

```
system    doc    doc_id    seg_id    rater    source    target    category    severity
```

Inside `target`, every error span is wrapped in `<v>…</v>` tags. Example:

```
… um Titelseiten zu <v>bekommen,</v> behauptet ehemaliger Bodyguard
                       ↑ rater4 marked this span as Accuracy/Mistranslation, Major
```

Rows where a rater found nothing wrong appear once with `category = No-error`, `severity = no-error`, and no `<v>` tags.

### 2.3 Scale of the corpus

Counts taken directly from the TSV used in this run:

| Quantity | Value |
|---------|-------|
| Source segments (`seg_id` values) | **1,418** unique news sentences |
| News documents (`doc` values) | **123** unique articles |
| News domains | ABC News, Al Jazeera, BBC/Guardian/Telegraph, CNN, CNBC, Reuters, Fox News, NDTV, NYTimes, Seattle Times, Sky, etc. |
| Systems evaluated | **10** (see §2.4) |
| Raters | **6** professional translators (`rater1` … `rater6`) |
| Raters per segment-system pair | **3 of 6** (round-robin assignment) |
| Total rows in TSV | 79,024 |
| Raw error spans after parsing | **64,557** (`metadata.n_raw_errors` in [all_results.json](all_results.json)) |
| Unique aligned errors at IoU = 0.5 | **45,936** (`metadata.n_aligned_errors`) |

### 2.4 Systems covered

Ten translation outputs, mixing humans and MT engines (the suffix is the WMT submission ID):

| System | Type |
|--------|------|
| `Human-A.0` | Human reference A |
| `Human-B.0` | Human reference B |
| `Human-P.0` | Human reference P |
| `eTranslation.737` | EU Commission MT |
| `Huoshan_Translate.832` | ByteDance/Volcano |
| `OPPO.1535` | OPPO |
| `Online-A.1574` | Anonymous online MT |
| `Online-B.1590` | Anonymous online MT |
| `Tencent_Translation.1520` | Tencent |
| `Tohoku-AIP-NTT.890` | Tohoku/AIP/NTT academic submission |

The three Human-* outputs serve as references and are dropped in sensitivity analysis **S7** (`_filter_s7` in [sensitivity.py](../../experiments/tom_validation/sensitivity.py)) to confirm the trend holds on MT-only data.

### 2.5 MQM error taxonomy used

The 17 MQM subcategories observed in the data are mapped to L0–L3 via [config.py](../../experiments/tom_validation/config.py)'s `MQM_TO_TOM` table (full mapping in §5.1 below). Three labels are excluded as unmappable: `No-error`, `Other`, `Fluency/Inconsistency`. Severities are `Major` (weight 5), `Minor` (weight 1), `Neutral` (weight 0).

### 2.6 Why this dataset

- **Independence:** the corpus is built and released by a third party (Google), not by the ToM-PE team — no risk of circularity between the hierarchy and the ground truth.
- **Multiple raters per item:** 3 independent expert annotations per segment-system pair give a discrete detection-rate signal (1/3, 2/3, 3/3) that maps directly to perceived difficulty.
- **Span-level markup:** `<v>…</v>` offsets enable IoU-based cross-rater alignment (§4) — without them, "the same error" could not be defined.
- **Scale:** ~46k aligned errors across L0–L3 give well-powered tests for all four hypotheses, including pairwise post-hoc and per-system breakdowns.

---

## 3. Pipeline Overview

The end-to-end pipeline is orchestrated by [run_all.py](../../experiments/tom_validation/run_all.py). One invocation reproduces every artifact in this directory:

```
python -m experiments.tom_validation.run_all
```

| # | Stage | Module | Purpose |
|---|-------|--------|---------|
| 1 | Parse | [parse_mqm.py](../../experiments/tom_validation/parse_mqm.py) | Extract error spans from TSV |
| 2 | Align | [align_errors.py](../../experiments/tom_validation/align_errors.py) | IoU-based cross-rater span matching |
| 3 | Assign ToM | [assign_tom.py](../../experiments/tom_validation/assign_tom.py) | Map MQM subcategory → ToM level; build covariates |
| 4 | Descriptive | [descriptive.py](../../experiments/tom_validation/descriptive.py) | Table 1: per-level summary stats |
| 5 | V1 | [test_trend.py](../../experiments/tom_validation/test_trend.py) | Jonckheere–Terpstra trend test |
| 6 | V2 | [test_trend.py](../../experiments/tom_validation/test_trend.py) | Kruskal–Wallis + Dunn's post-hoc |
| 7 | V3 | [mixed_models.py](../../experiments/tom_validation/mixed_models.py) + [clmm_analysis.R](../../experiments/tom_validation/clmm_analysis.R) | Cumulative-link (mixed) ordinal regression |
| 8 | V4 | [mixed_models.py](../../experiments/tom_validation/mixed_models.py) + [rater_glmm.R](../../experiments/tom_validation/rater_glmm.R) | Logistic GLMM with random slopes by rater |
| 9 | Sensitivity | [sensitivity.py](../../experiments/tom_validation/sensitivity.py) | S1–S8 robustness checks |
| 10 | Figures | [figures.py](../../experiments/tom_validation/figures.py) | Publication-quality plots |

R-based analyses (V3 CLMM, V4 GLMM) are run via [r_runner.py](../../experiments/tom_validation/r_runner.py); Python-only fallbacks exist when R is unavailable.

---

## 4. Stage 1 — Parsing the MQM corpus

**Module:** [parse_mqm.py](../../experiments/tom_validation/parse_mqm.py)
**Input:** `data/wmt-mqm/mqm_newstest2020_ende.tsv`

For every row whose `category` is not `No-error` and not in `{Other, Fluency/Inconsistency}`, all `<v>…</v>` spans are extracted from the `target` field. Each span becomes one `ErrorSpan` record carrying:

- `segment_id`, `system`, `doc`, `rater`
- `category`, `severity`
- character-level `span_start`, `span_end` on the **cleaned** target (tags stripped)
- `span_text`, `source_text`, `target_clean`

A row containing a category but no `<v>` tags falls back to a single span covering the full cleaned target.

**Result for the run on file:** **64,557 raw error spans** (`metadata.n_raw_errors`).

---

## 5. Stage 2 — Cross-rater span alignment

**Module:** [align_errors.py](../../experiments/tom_validation/align_errors.py)

The dataset is grouped by `(segment_id, system)`. Within each group, every rater contributes 0+ spans. Spans are linked into clusters using **character-level IoU**:

```
IoU(s_a, s_b) = |s_a ∩ s_b| / |s_a ∪ s_b|
```

Two spans from *different* raters merge into the same cluster when `IoU ≥ τ`. Clustering is **transitive**: a span joins a cluster if it overlaps any existing member from a different rater. Each resulting cluster is one *aligned error location* and yields an `AlignedError` with:

- union start/end offsets,
- `detection_count` ∈ {1, 2, 3} (number of distinct raters in the cluster),
- `detection_rate = detection_count / 3` (3 raters per pair, by the WMT design),
- majority-vote `category`, max-severity (`Major > Minor > Neutral`),
- the `raters_detected` / `raters_missed` lists used downstream by V4.

**IoU thresholds:**

| Setting | τ | Used for |
|---------|---|----------|
| Primary | **0.5** | Main analyses (V1–V4) |
| Lenient | 0.3 | Sensitivity S5 |
| Strict | 0.7 | Sensitivity S6 |

For the recorded run, `--skip-iou-variants` was active, so S5/S6 are reported as skipped (`metadata.skip_iou_variants = true`).

**Result:** **45,936 aligned errors** at τ = 0.5 (`metadata.n_aligned_errors`).

---

## 6. Stage 3 — ToM level assignment and covariates

**Module:** [assign_tom.py](../../experiments/tom_validation/assign_tom.py); mapping in [config.py](../../experiments/tom_validation/config.py).

### 6.1 MQM → ToM mapping (Spec §3.1)

| ToM | MQM subcategories |
|-----|-------------------|
| **L0** — target-only pattern matching | Fluency/Spelling, Fluency/Punctuation, Fluency/Character encoding, Non-translation!, Fluency/Grammar (conservative, Spec §3.3 Option 1) |
| **L1** — source consultation needed | Accuracy/Untranslated text |
| **L2** — source-author model required | Terminology/Inappropriate for context, Terminology/Inconsistent use of terminology, Accuracy/Omission, Accuracy/Addition, Accuracy/Mistranslation (Spec §3.2 Strategy A) |
| **L3** — reader-facing impact | Style/Awkward, Fluency/Register, Locale convention/{Currency, Address, Date, Time} format |

`Other`, `Fluency/Inconsistency`, and `No-error` are excluded as unmappable. A row's `is_ambiguous` flag is set when `category == Accuracy/Mistranslation` (used by sensitivity S1).

### 6.2 Covariates (Spec §4.4)

For every aligned error, three covariates are computed:

- `segment_length` — token count of the source.
- `system_quality` — proxy: `−n_errors_for_system` (more errors → worse quality), then *z*-standardised in V3.
- `error_density` — errors per source token within the segment-system pair.

`is_major = 1{severity == "Major"}` is the binary severity covariate used in V3/V4.

**Result for the run:** 45,936 errors retained — **L0: 13,586, L1: 1,368, L2: 22,002, L3: 8,980** (`v1_jonckheere_terpstra.group_sizes`).

---

## 7. Stage 4 — Descriptive statistics (Table 1)

**Module:** [descriptive.py](../../experiments/tom_validation/descriptive.py)

For each level, the pipeline reports `n`, mean/SD/median detection rate, the (1/3, 2/3, 3/3)-rater distribution, and per-severity counts and means. A second table breaks the same statistics down by exact MQM subcategory (`mapping_table`, used to colour [V2_category_heatmap.png](V2_category_heatmap.png)).

**Headline numbers from [all_results.json](all_results.json):**

| Level | n | Mean det. | % 1/3 | % 2/3 | % 3/3 | Major n | Minor n |
|-------|----|-----------|-------|-------|-------|--------|---------|
| L0 | 13,586 | 0.513 | 61.2 | 23.6 | 15.2 | 505 | 12,956 |
| L1 |  1,368 | 0.499 | 63.6 | 23.1 | 13.3 | 242 | 1,061 |
| L2 | 22,002 | 0.462 | 70.4 | 20.7 |  9.0 | 5,186 | 16,214 |
| L3 |  8,980 | 0.411 | 80.2 | 16.2 |  3.6 | 569 | 7,823 |

The mean detection rate falls monotonically (0.513 → 0.499 → 0.462 → 0.411), and the share of unanimous (3/3) detections collapses from 15.2 % at L0 to 3.6 % at L3 — a strong descriptive signal in favour of H1.

---

## 8. Stage 5 — V1: Jonckheere–Terpstra trend test (H1)

**Module:** [test_trend.py](../../experiments/tom_validation/test_trend.py)

Tests `H₀:` distributions of `detection_rate` are equal across L0–L3 against `H₁:` they are stochastically ordered (decreasing with level). The implementation:

1. Computes the J statistic by counting concordant pairs across each ordered pair of groups (with 0.5 weight on ties).
2. Standardises J using its expected value and a tie-corrected variance (Daniel/Lehmann formula).
3. Reports the one-sided p-value for *decreasing* trend.
4. Adds **Kendall's τ-b** as a paired effect size between `tom_level` and `detection_rate`.

**Result (`v1_jonckheere_terpstra`):**

- J = 380,433,016, p < 1e-6
- τ-b = **−0.1409**, p < 1e-6
- Direction: decreasing
- Interpretation: **CONFIRMED — significant monotonic decrease.**

H1 is supported.

---

## 9. Stage 6 — V2: Kruskal–Wallis + Dunn's post-hoc

**Module:** [test_trend.py](../../experiments/tom_validation/test_trend.py)

Tests whether `detection_rate` differs across the four ToM levels (`H₀:` all four distributions identical). Pairwise Dunn's tests (rank-based z statistics) follow with **Holm–Bonferroni** correction.

**Result (`v2_kruskal_wallis`):**

- H(3) = 1101.17, p < 1e-6 — **significant.**
- Dunn pairwise (adjusted):

  | Comparison | z | p_adj | Sig. |
  |-----------|----|-------|------|
  | L0 vs L2 | 16.11 | <1e-6 | * |
  | L0 vs L3 | 26.34 | <1e-6 | * |
  | L1 vs L2 |  4.62 | 8e-6 | * |
  | L1 vs L3 | 10.72 | <1e-6 | * |
  | L2 vs L3 | 14.56 | <1e-6 | * |
  | L0 vs L1 |  1.66 | 0.096 | n.s. |

5 of 6 pairs separate; only adjacent low-volume L0/L1 fails to reach significance — consistent with the small L1 cell (n = 1,368) and the conservative Fluency/Grammar→L0 assignment (Spec §3.3 Option 1).

---

## 10. Stage 7 — V3: ordinal regression with crossed random effects (H2)

Two complementary fits are produced.

### 10.1 Python fixed-effects approximation

**Module:** [mixed_models.py](../../experiments/tom_validation/mixed_models.py) (uses `statsmodels.miscmodels.OrderedModel`).

Cumulative-logit (proportional-odds) model for `detection_count ∈ {1, 2, 3}`:

```
logit P(det ≤ k) = θ_k − ( β1·tom_linear + β2·is_major + β3·seg_len_z + β4·sys_qual_z )
```

A nested-model **likelihood-ratio test** drops `tom_linear` to gauge incremental fit (`df = 1`).

**Result (`v3_ordinal_regression`):**

| Term | β | SE | z | p |
|------|----|----|----|----|
| `tom_linear` | **−0.331** | 0.010 | −34.72 | <1e-6 |
| `is_major` |  1.178 | 0.027 |  43.45 | <1e-6 |
| `seg_len_z` | −0.168 | 0.011 | −15.35 | <1e-6 |
| `sys_qual_z` | −0.313 | 0.011 | −28.36 | <1e-6 |

LR test (with vs. without ToM): χ²(1) = 1219.5, p < 1e-6. AIC = 70,203.7. **Significant negative ToM effect** controlling for severity, segment length, and system quality.

### 10.2 R-based CLMM (proper §5.4)

**Module:** [clmm_analysis.R](../../experiments/tom_validation/clmm_analysis.R) (R `ordinal::clmm`), invoked via [r_runner.py](../../experiments/tom_validation/r_runner.py).

Same fixed-effects structure, with crossed random intercepts for `system` and `doc`:

```
detection_count_ord ~ tom_linear + is_major + seg_len_z + sys_qual_z + (1 | system) + (1 | doc)
```

A reduced model omitting `tom_linear` provides the LR test on H2.

**Result (`v3_clmm_r`):**

| Term | β | SE | 95 % CI | p |
|------|----|----|---------|----|
| `tom_linear` | **−0.326** | 0.0099 | [−0.346, −0.307] | <1e-6 |
| `is_major` |  1.291 | 0.028 | — | <1e-6 |
| `seg_len_z` | −0.152 | 0.014 | — | <1e-6 |
| `sys_qual_z` | −0.327 | 0.044 | — | <1e-6 |

Random-effect SDs: `doc = 0.401`, `system = 0.144`. LR test (full vs. reduced): χ²(1) = 1106.08, p < 1e-6. AIC drops from 70,204 (FE-only) to **69,079** with crossed random effects, evidence that document-level clustering is non-trivial. The CLMM β is essentially identical to the fixed-effects estimate (−0.326 vs. −0.331), giving converging support for **H2**.

R environment recorded: R 4.2.3, ordinal 2023.12.4.

---

## 11. Stage 8 — V4: rater-level logistic regression (H3)

`build_rater_level_data` ([assign_tom.py](../../experiments/tom_validation/assign_tom.py)) explodes each aligned error into one row per rater (`detected = 1` if the rater's span belonged to the cluster, else 0). Output: [rater_level_data.csv](rater_level_data.csv) — **120,397 rater-level observations** across **6 raters**.

### 11.1 Python fixed-effects logit

**Module:** [mixed_models.py](../../experiments/tom_validation/mixed_models.py).

Logistic regression:

```
detected ~ tom_level + is_major + seg_len_z
         + (rater dummies for raters 2..6)
         + (tom_level × rater interactions)
```

The Wald χ² jointly tests the 5 ToM × rater interaction coefficients (df = 5).

**Result (`v4_rater_logistic`):**

- Wald χ²(5) = **229.45**, p < 1e-6 — interactions jointly significant.
- Per-rater ToM slopes:

  | Rater | β(ToM) |
  |-------|--------|
  | rater1 | −0.217 |
  | rater2 | −0.143 |
  | rater3 | −0.170 |
  | rater4 | **+0.018** |
  | rater5 | −0.060 |
  | rater6 | −0.177 |

Five raters show a negative slope; rater4 is essentially flat / slightly positive. **H3 supported.**

### 11.2 R-based GLMM with random slopes (proper §5.5)

**Module:** [rater_glmm.R](../../experiments/tom_validation/rater_glmm.R) (R `lme4::glmer`).

```
detected ~ tom_level + is_major + seg_len_z + (1 + tom_level | rater) + (1 | system)
```

The full vs. random-intercept-only LR test isolates the **random slope** variance component. Because variance components are bounded below at 0, the p-value is reported under both naïve χ² and the **50:50 mixture χ²** appropriate for boundary tests.

**Result (`v4_glmm_r`):**

- Fixed effects: `tom_level` β = **−0.122** (z = −3.72, p = 2e-4), `is_major` β = 0.448, `seg_len_z` β = −0.156.
- Random-effect SDs: `rater intercept = 0.200`, `rater tom_level slope = 0.079`, `system intercept = 0.106`. Intercept–slope correlation r ≈ −0.44.
- LR test on random slopes: χ²(2) = **202.55**, p_mixture < 1e-6 — slopes are real, not noise.
- BLUP-derived per-rater slopes: −0.211 / −0.139 / −0.166 / **+0.019** / −0.060 / −0.172, almost identical to the FE fit.

H3 supported with mixed-model evidence. R environment: R 4.2.3, lme4 1.1.35.

---

## 12. Stage 9 — Sensitivity analyses (S1–S8)

**Module:** [sensitivity.py](../../experiments/tom_validation/sensitivity.py). Every variant re-runs **V1** on a re-filtered dataset; convergence is declared if V1 is significant in the primary analysis **and** in ≥ 5 of the 8 variants.

| ID | Filter | n | τ-b | Sig.? |
|----|--------|----|-----|-------|
| **S1** | Drop Accuracy/Mistranslation (Spec §3.2 Strategy B) | 31,578 | −0.178 | ✓ |
| **S2** | Binary ToM: L0–L1 vs. L2–L3 (Strategy C) | 45,936 | −0.126 | ✓ |
| **S3** | Drop `severity == Neutral` | 44,556 | −0.134 | ✓ |
| **S4** | Major-only | 6,502 | −0.078 | ✓ |
| S5 | Lenient IoU = 0.3 | — | — | skipped (`--skip-iou-variants`) |
| S6 | Strict IoU = 0.7 | — | — | skipped (`--skip-iou-variants`) |
| **S7** | Exclude Human references | 36,729 | −0.141 | ✓ |
| **S8** | Per-system V1 (10 systems) | — | 9 / 10 sig. | ✓ |

The S8 per-system breakdown is in [all_results.json](all_results.json) → `sensitivity.S8_per_system`. Only `eTranslation.737` fails (τ-b = −0.009, p = 0.24); the other nine systems all show significant negative trends, with the strongest effects on `Online-A.1574` (−0.219), `Online-B.1590` (−0.226), and `Tohoku-AIP-NTT.890` (−0.230).

**Convergence summary (`sensitivity._summary`):** 6 / 6 testable variants significant — convergence **MET**.

---

## 13. Stage 10 — Figures

| File | What it shows |
|------|---------------|
| [V1_detection_boxplot.png](V1_detection_boxplot.png) | Box plot of detection rate by ToM level with severity-coloured jitter and means annotated. |
| [V2_category_heatmap.png](V2_category_heatmap.png) | Horizontal bars of per-MQM-subcategory mean detection rate, coloured by ToM level. |
| [V3_rater_slopes.png](V3_rater_slopes.png) | Forest plot of per-rater ToM slopes from V4. |
| [sensitivity_summary.png](sensitivity_summary.png) | τ-b for each testable sensitivity variant; green = significant, grey = n.s. |

Generation code: [figures.py](../../experiments/tom_validation/figures.py).

---

## 14. Output artefacts

| File | Producer | Content |
|------|----------|---------|
| [tom_errors.csv](tom_errors.csv) | Stage 3 | Aligned errors with ToM level, severity, covariates — input for V1, V2, V3 (Python + R). |
| [rater_level_data.csv](rater_level_data.csv) | Stage 8 | Long-form rater × error rows — input for V4 (Python + R). |
| [clmm_results.json](clmm_results.json) | [clmm_analysis.R](../../experiments/tom_validation/clmm_analysis.R) | CLMM coefficients, random-effect variances, LR test. |
| [glmm_results.json](glmm_results.json) | [rater_glmm.R](../../experiments/tom_validation/rater_glmm.R) | GLMM fixed/random effects, per-rater BLUPs, mixture-χ² LR test. |
| [all_results.json](all_results.json) | [run_all.py](../../experiments/tom_validation/run_all.py) | Master JSON: metadata, descriptive, V1–V4 (both Python and R), sensitivity, figure paths. |

---

## 15. Reproducing the run

```powershell
# Full pipeline, primary IoU only (matches what produced the JSON in this folder)
python -m experiments.tom_validation.run_all --skip-iou-variants

# Full pipeline including S5/S6
python -m experiments.tom_validation.run_all

# Skip the R-based CLMM/GLMM (Python-only fallback)
python -m experiments.tom_validation.run_all --skip-r
```

The R analyses require R ≥ 4.2 with packages `ordinal` and `lme4` installed. If R is missing, [r_runner.py](../../experiments/tom_validation/r_runner.py) returns `skipped` records and the Python fixed-effects fits remain authoritative.

---

## 16. Headline conclusions

- **H1 confirmed:** detection rate decreases monotonically with ToM level (V1 J = 3.80e8, τ-b = −0.141, p < 1e-6).
- **H2 confirmed:** the ToM effect survives covariate adjustment and crossed random effects of `system` × `doc` (CLMM β = −0.326, 95 % CI [−0.346, −0.307]).
- **H3 supported:** raters differ systematically in ToM sensitivity (GLMM random-slope LR χ²(2) = 202.5, p < 1e-6); slopes range from −0.21 to +0.02.
- **Robustness:** V1 is significant in the primary analysis and in 6 / 6 testable sensitivity variants, including a per-system check where 9 / 10 MT systems show the predicted decreasing trend.

The hierarchy therefore predicts a behavioural difficulty ordering that is reproducible across category-mapping ambiguity, severity weighting, system identity, and modelling choice.
