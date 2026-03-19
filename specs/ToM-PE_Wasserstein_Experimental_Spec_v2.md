# Wasserstein Distance for Multi-Skill Learning Progress
## Experimental Specification — v2.1 (March 2026)

**Extends**: Wasserstein Formalization v1.0 (theoretical framework)
**Scope**: Detailed experimental design for validating the ToM-Wasserstein metric using (a) WMT MQM annotator data as a proxy for student annotation behavior, (b) empirically calibrated synthetic student trajectories, (c) comprehensive ground metric comparison (unweighted graph, weighted graph, 2D embedding, baselines), and (d) both normalized (balanced OT) and unnormalized (unbalanced OT) formulations.

---

## 1. Experimental Overview

### 1.1 Research Questions

**RQ1 (Discriminative Power):** Does W₁ with the ToM ground metric distinguish structurally different annotator/student profiles that Euclidean distance treats as equivalent?

**RQ2 (Coherence Detection):** Does W₁ detect coherent vs. incoherent skill progression patterns, and does it do so more reliably than pointwise metrics?

**RQ3 (Ground Metric Sensitivity):** How does the choice of ground metric (trivial, linear, graph-based) affect the metric's discriminative power? Specifically, does the ToM-ordered graph metric outperform alternatives?

**RQ4 (Practical Utility):** Does W₁-based mastery distance correlate better with pedagogically meaningful outcomes (progression readiness, teacher judgment) than traditional detection rate averages?

**RQ5 (Linearization vs. Graph):** How much information is lost by the computationally cheaper 1D linearization compared to the full graph-distance formulation?

**RQ6 (Normalization):** Does unnormalized (unbalanced OT) provide additional discriminative power over normalized (balanced OT) by capturing total mastery magnitude alongside profile shape?

**RQ7 (Empirical Calibration):** Do weighted ground metrics calibrated from empirical detection rate data outperform unweighted alternatives?

### 1.2 Two-Track Experimental Design

| Track | Data Source | What It Demonstrates | Section |
|---|---|---|---|
| **Track A** (first) | WMT MQM annotator data | W₁ applied to real error-detection profiles from professional annotators | §3 |
| **Track B** (informed by A) | Empirically calibrated synthetic student trajectories | W₁ applied to simulated learning progressions over multiple sessions | §4 |

**Execution order: Track A before Track B.** This is a deliberate methodological choice. Starting with real data (WMT MQM) ensures we *discover* whether the metric captures meaningful structure in actual annotation behavior before we *design* synthetic examples to demonstrate theoretical properties. Three specific reasons:

1. **Avoids circularity**: If we start with synthetic data, we design archetypes that W₁ will distinguish by construction, then confirm it works — proving the math, not the method. Starting with real data means we don't know what we'll find.

2. **Track A informs Track B**: WMT rater profiles may reveal annotation patterns that don't match our idealized archetypes. Real annotators may cluster into 3 types rather than 5, or the accuracy-vs-fluency dimension may dominate over our hypothesized ToM ordering. Whatever we discover becomes the empirical grounding for the synthetic archetypes, replacing or confirming our literature-based estimates.

3. **Publishability**: Real-data findings carry more weight than synthetic demonstrations. "We applied our metric to 42,000 MQM annotations and found..." is stronger than "we generated 20 synthetic students and found..."

Track A establishes that the metric works on real data. Track B then provides controlled conditions to demonstrate specific theoretical properties (coherence detection, trajectory efficiency, ground metric sensitivity) under known parameters — with those parameters now grounded in Track A findings rather than solely in literature estimates.

### 1.3 Normalization: Balanced vs. Unbalanced Optimal Transport

We implement two parallel formulations:

**Balanced W₁ (normalized profiles):** Student mastery vectors are normalized to probability distributions summing to 1. This captures the *shape* of the skill profile — where strengths and weaknesses lie relative to each other. Two students with profiles [0.9, 0.8, 0.7, ...] and [0.09, 0.08, 0.07, ...] receive the same normalized distribution.

$$\mu(t)(S_k) = \frac{P(L_k^t)}{\sum_{j=1}^{7} P(L_j^t)}, \quad \sum_k \mu(t)(S_k) = 1$$

**Unbalanced W₁ (raw mastery vectors):** No normalization — mastery vectors are used directly as non-negative measures that need not sum to 1. This captures both *shape* and *magnitude*. A student who improves across all skills simultaneously creates mass; one who regresses destroys mass. Standard OT requires mass conservation; unbalanced OT [Chizat et al. 2018] relaxes this via KL penalties:

$$UW_{1,\lambda}(\mu, \nu) = \inf_{\gamma \geq 0} \sum_{i,j} \gamma_{i,j} \cdot d(S_i, S_j) + \lambda_1 \text{KL}(\gamma \mathbf{1} \| \mu) + \lambda_2 \text{KL}(\gamma^T \mathbf{1} \| \nu)$$

where $\lambda_1, \lambda_2$ control the penalty for mass creation/destruction. Available in POT as `ot.unbalanced.sinkhorn_unbalanced2(a, b, M, reg, reg_m)`.

**When they diverge:** The two formulations produce different results when:
- A student improves uniformly on all skills (normalized: no change; unnormalized: mass increases)
- A student improves on one skill but regresses on another (normalized: shape change only; unnormalized: captures net effect)
- Comparing students with very different total mastery but similar shapes

We run all analyses with both formulations and report where they agree and diverge.

---

## 2. Ground Metric Design

The ground metric is the core theoretical contribution — it encodes the pedagogical theory into the distance function. We define and compare 5 ground metrics, organized from simplest to richest.

### 2.1 Skill Dependency Graph (Foundation)

All structured ground metrics derive from the ToM skill dependency graph:

```
S1 (Surface) ──→ S2 (Grammar) ──→ S3 (Meaning) ──→ S4 (Completeness)
                                        │
                                        ├──→ S5 (Terminology)
                                        │
                                        └──→ S6 (Pragmatic) ──→ S7 (Discourse)
```

### 2.2 Ground Metric M1: Trivial (Baseline)

$$d_{\text{trivial}}(S_i, S_j) = \begin{cases} 0 & \text{if } i = j \\ 1 & \text{if } i \neq j \end{cases}$$

W₁ with trivial ground metric = Total Variation distance. No structural information. This is the **null baseline** — any structured ground metric should outperform it.

```python
D_trivial = 1.0 - np.eye(7)
```

### 2.3 Ground Metric M2: Unweighted Graph Distance

$$d_{\text{graph}}(S_i, S_j) = \text{shortest path length in } G / \max(\text{all shortest paths})$$

Full normalized distance matrix:

$$D_{\text{graph}} = \frac{1}{4}\begin{pmatrix}
0 & 1 & 2 & 3 & 3 & 3 & 4 \\
1 & 0 & 1 & 2 & 2 & 2 & 3 \\
2 & 1 & 0 & 1 & 1 & 1 & 2 \\
3 & 2 & 1 & 0 & 2 & 2 & 3 \\
3 & 2 & 1 & 2 & 0 & 2 & 3 \\
3 & 2 & 1 & 2 & 2 & 0 & 1 \\
4 & 3 & 2 & 3 & 3 & 1 & 0
\end{pmatrix}$$

**Strengths:** Directly encodes the ToM prerequisite structure. Simple, interpretable. "How many developmental steps apart are these skills?"

**Limitation:** All edges have equal weight. The jump S2→S3 (grammar → meaning) is treated identically to S1→S2 (surface → grammar), yet empirically the cognitive gap is larger.

```python
from scipy.sparse.csgraph import shortest_path
ADJ = np.array([
    [0,1,0,0,0,0,0], [1,0,1,0,0,0,0], [0,1,0,1,1,1,0],
    [0,0,1,0,0,0,0], [0,0,1,0,0,0,0], [0,0,1,0,0,0,1], [0,0,0,0,0,1,0]
])
D_graph = shortest_path(ADJ, unweighted=True)
D_graph_norm = D_graph / D_graph.max()
```

### 2.4 Ground Metric M3: Weighted Graph Distance (Empirically Calibrated)

Same graph topology as M2, but edge weights are calibrated from the empirical detection rate gradient derived from our literature compendium:

**Calibration source:** Student detection rates by skill (from §3.1.1 of this spec):
- S1: 93%, S2: 85%, S3: 80%, S4: 67%, S5: ~65%, S6: ~50%, S7: ~35%

**Edge weight formula:** The weight of edge (Sᵢ → Sⱼ) is proportional to the absolute detection rate drop across that edge, normalized:

```
w(S1→S2) = |93% - 85%| = 8
w(S2→S3) = |85% - 80%| = 5
w(S3→S4) = |80% - 67%| = 13
w(S3→S5) = |80% - 65%| = 15
w(S3→S6) = |80% - 50%| = 30
w(S6→S7) = |50% - 35%| = 15
```

Normalized to [0, 1] by dividing by the maximum shortest-path weight.

**Interpretation:** The S3→S6 edge (meaning → pragmatic) is weighted 3.75× heavier than S2→S3 (grammar → meaning), reflecting the empirical reality that the jump to audience-level reasoning is much larger than the jump to source comparison.

```python
ADJ_weighted = np.zeros((7, 7))
ADJ_weighted[0, 1] = ADJ_weighted[1, 0] = 8   # S1-S2
ADJ_weighted[1, 2] = ADJ_weighted[2, 1] = 5   # S2-S3
ADJ_weighted[2, 3] = ADJ_weighted[3, 2] = 13  # S3-S4
ADJ_weighted[2, 4] = ADJ_weighted[4, 2] = 15  # S3-S5
ADJ_weighted[2, 5] = ADJ_weighted[5, 2] = 30  # S3-S6
ADJ_weighted[5, 6] = ADJ_weighted[6, 5] = 15  # S6-S7
# Replace 0s with inf for shortest path (except diagonal)
ADJ_sp = ADJ_weighted.copy()
ADJ_sp[ADJ_sp == 0] = np.inf
np.fill_diagonal(ADJ_sp, 0)
D_weighted = shortest_path(ADJ_sp, method='D')
D_weighted_norm = D_weighted / D_weighted.max()
```

### 2.5 Ground Metric M4: 2D Embedding (ToM Level × Linguistic Grain)

Skills are embedded in a 2D space with two pedagogically meaningful axes:
- **Axis 1: ToM Level** (cognitive depth — whose perspective is modeled)
- **Axis 2: Linguistic Grain** (scope of the text unit involved)

| Skill | ToM Level (y) | Linguistic Grain (x) | Coordinates |
|---|---|---|---|
| S1 Surface | 1 (machine form) | 1 (character/word) | (1, 1) |
| S2 Grammar | 1 (machine form) | 2 (phrase/clause) | (2, 1) |
| S3 Meaning | 2 (machine + author) | 2 (phrase/clause) | (2, 2) |
| S4 Completeness | 2 (author intent) | 3 (sentence) | (3, 2) |
| S5 Terminology | 3 (reader inference) | 1 (word/term) | (1, 3) |
| S6 Pragmatic | 3 (reader inference) | 3 (sentence) | (3, 3) |
| S7 Discourse | 4 (recursive) | 4 (multi-sentence) | (4, 4) |

**Ground metric:** Euclidean distance in this 2D space, normalized:

$$d_{\text{2D}}(S_i, S_j) = \sqrt{(x_i - x_j)^2 + (y_i - y_j)^2} / d_{\max}$$

```python
coords = np.array([
    [1, 1],  # S1: word-level, machine
    [2, 1],  # S2: phrase-level, machine
    [2, 2],  # S3: phrase-level, machine+author
    [3, 2],  # S4: sentence-level, author
    [1, 3],  # S5: word-level, reader
    [3, 3],  # S6: sentence-level, reader
    [4, 4],  # S7: multi-sentence, recursive
])
from scipy.spatial.distance import cdist
D_2d = cdist(coords, coords, metric='euclidean')
D_2d_norm = D_2d / D_2d.max()
```

**What this captures that M2/M3 miss:** S5 (Terminology, word-level, reader) and S4 (Completeness, sentence-level, author) are equidistant from S3 in the graph but occupy very different positions in the 2D space: S5 is high on ToM but low on linguistic grain (domain knowledge for individual terms), while S4 is moderate on ToM but high on linguistic grain (noticing something is missing requires sentence-level comprehension). The 2D embedding distinguishes these two qualitatively different competencies.

### 2.6 Ground Metric M5: Uniform Linear (Control)

Skills ordered 0–6 uniformly with no ToM or pedagogical information:

$$d_{\text{uniform}}(S_i, S_j) = |i - j| / 6$$

This preserves skill *ordering* (S1 < S2 < ... < S7) but treats all adjacent gaps as equal and imposes a single dimension. Acts as a control to test whether the ToM-specific structure (branching, weighting) adds value beyond simple ordering.

```python
D_uniform = np.abs(np.arange(7)[:, None] - np.arange(7)[None, :]) / 6.0
```

### 2.7 Ground Metric Summary

| ID | Name | Source | Structure | Key Property |
|---|---|---|---|---|
| M1 | Trivial | Null baseline | None | W₁ = Total Variation |
| M2 | Unweighted graph | ToM dependency graph | Graph topology | Encodes prerequisites |
| M3 | Weighted graph | Graph + detection rates | Graph + empirical weights | Calibrated difficulty gaps |
| M4 | 2D embedding | ToM level × linguistic grain | 2D Euclidean | Separates depth from scope |
| M5 | Uniform linear | Skill ordering only | 1D uniform | Controls for ordering effect |
| M_rand | Random (×10) | Permutation null | Random 7×7 metrics | Statistical baseline |

All 5 structured metrics (M1–M5) + 10 random matrices (M_rand) are used in every analysis to establish: (a) whether *any* structure helps (M2–M5 vs. M1), (b) whether *our specific* structure helps (M2–M5 vs. M_rand), (c) whether weighting helps (M3 vs. M2), (d) whether dimensionality helps (M4 vs. M2), (e) whether structure beyond ordering helps (M2–M4 vs. M5).

---

## 3. Track A: WMT MQM Annotator Analysis

### 3.1 Data Source

**Dataset**: WMT MQM Human Evaluation [Freitag et al. 2021, 2022, 2023]
**Access**: HuggingFace `RicardoRei/wmt-mqm-human-evaluation` (structured) + GitHub `google/wmt-mqm-human-evaluation` (raw TSV with error spans)
**Years**: 2020, 2021, 2022, 2023
**Language pairs**: EN→DE (primary, largest dataset), ZH→EN (secondary)
**Domains**: News (newstest), TED talks

**Data format** (raw TSV columns):
```
system | doc | docSegId | raterID | source | target | category | severity
```

Each segment is independently annotated by **3 professional raters**. Categories follow the MQM hierarchy: Accuracy/{Mistranslation, Omission, Addition, Untranslated}, Fluency/{Grammar, Spelling, Punctuation, Register}, Terminology, Style, Locale, Non-translation.

**Dataset sizes** (approximate):
- WMT 2020 EN→DE: ~1,418 segments × 10 systems × 3 raters = ~42,540 annotation instances
- WMT 2020 ZH→EN: ~2,000 segments × 10 systems × 3 raters = ~60,000 annotation instances
- WMT 2021 EN→DE: ~1,002 segments × 15 systems × 3 raters = ~45,090 annotation instances
- WMT 2022+2023: additional data with expanded system sets

### 3.2 Data Processing Pipeline

#### Step 1: Load and filter

```python
from datasets import load_dataset

# Load from HuggingFace
dataset = load_dataset("RicardoRei/wmt-mqm-human-evaluation", split="train")

# Filter for EN-DE 2020 (primary analysis)
data_ende_2020 = dataset.filter(
    lambda x: x["lp"] == "en-de" and x["year"] == 2020
)
```

For span-level analysis, use the raw TSV from GitHub:
```bash
git clone https://github.com/google/wmt-mqm-human-evaluation
# File: mqm_newstest2020_ende.tsv
```

#### Step 2: Extract per-rater error category profiles

For each rater, compute the distribution of errors they annotated across MQM categories:

```python
def extract_rater_profile(annotations, rater_id):
    """
    Given all annotations by a rater across all segments,
    compute their error category distribution.
    
    Returns a dict mapping our 7-skill categories to counts.
    """
    skill_map = {
        # MQM category → ToM-PE Skill
        "Accuracy/Mistranslation": "S3",
        "Accuracy/Omission": "S4",
        "Accuracy/Addition": "S4",
        "Accuracy/Untranslated": "S4",
        "Fluency/Spelling": "S1",
        "Fluency/Punctuation": "S1",
        "Fluency/Grammar": "S2",
        "Fluency/Register": "S6",
        "Terminology": "S5",
        "Style": "S6",
        "Locale": "S6",
        "Non-translation": "S3",  # Extreme accuracy failure
    }
    
    rater_annots = [a for a in annotations if a["raterID"] == rater_id]
    profile = {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": 0, "S6": 0, "S7": 0}
    
    for annot in rater_annots:
        category = annot["category"]
        skill = skill_map.get(category, "S3")  # Default to S3
        profile[skill] += 1
    
    return profile
```

**Note on S7 (Discourse)**: WMT MQM does not have a dedicated discourse/coherence category because annotation is segment-level. S7 will be zero in WMT data — we acknowledge this limitation. The analysis focuses on S1–S6.

#### Step 3: Compute pairwise inter-rater W₁

For each segment (or document), compute W₁ between the two raters' error profiles:

```python
import numpy as np
import ot
from ground_metrics import D_trivial, D_graph_norm, D_weighted_norm, D_2d_norm, D_uniform
# All ground metric matrices from §2 (M1–M5)

def profile_to_distribution(profile):
    """Convert count dict to probability distribution (balanced OT)."""
    vals = np.array([profile[f"S{k}"] for k in range(1, 8)], dtype=float)
    vals = np.maximum(vals, 1e-8)
    return vals / vals.sum()

def profile_to_raw(profile):
    """Convert count dict to raw vector (unbalanced OT)."""
    vals = np.array([profile[f"S{k}"] for k in range(1, 8)], dtype=float)
    return np.maximum(vals, 1e-8)

def compute_w1(profile_a, profile_b, cost_matrix, balanced=True):
    if balanced:
        mu_a = profile_to_distribution(profile_a)
        mu_b = profile_to_distribution(profile_b)
        return ot.emd2(mu_a, mu_b, cost_matrix)
    else:
        a = profile_to_raw(profile_a)
        b = profile_to_raw(profile_b)
        return ot.unbalanced.sinkhorn_unbalanced2(a, b, cost_matrix, reg=0.01, reg_m=1.0)
```

### 3.3 Analyses on WMT Data

#### Analysis A1: Inter-Rater Profile Distances

**Question**: Do raters differ more on hard-to-detect error categories (Accuracy) than on easy ones (Fluency)?

**Method**: For each segment with 3 raters, compute:
- W₁(rater_i, rater_j) for all 3 rater pairs, using all ground metrics M1–M5
- Euclidean distance between the same profiles
- Compare: do W₁ and Euclidean rank the rater pairs differently?

**Expected result**: Rater pairs that agree on Fluency (S1–S2) but disagree on Accuracy/Omission (S3–S4) should have lower W₁ (M2/M3) than pairs that disagree uniformly — because the graph metric treats Fluency and Accuracy as distant. Euclidean distance won't distinguish these cases.

**Statistical test**: Spearman correlation between W₁ rankings and Euclidean rankings of rater pairs. If ρ < 1.0, the metrics provide different information.

#### Analysis A2: Rater-as-Student Competency Profiles

**Question**: Can we characterize different annotator "styles" as skill profiles and show W₁ distinguishes them?

**Method**: For each rater (across all their annotations), compute their global profile (S1–S6 distribution). Cluster raters using W₁ as the distance metric (k-medoids) with each of M1–M5. Compare cluster quality (silhouette score) with clustering using Euclidean distance.

**Expected result**: W₁ clustering with M2/M3/M4 should produce more interpretable clusters — e.g., "accuracy-focused raters" (high S3/S4 weight) vs. "fluency-focused raters" (high S1/S2 weight) — because the ground metric groups adjacent skills.

#### Analysis A3: System Quality × Rater Agreement

**Question**: Does rater agreement (measured by W₁) vary with MT system quality?

**Method**: For each MT system (ranked by MQM score), compute average inter-rater W₁ under M2 (primary) and M3 (secondary). Plot W₁ vs. system quality.

**Expected result**: Better MT systems should produce higher inter-rater W₁ — when there are few errors, raters disagree more about what constitutes an error, and their profiles diverge. This would parallel the finding that high-quality NMT makes error detection harder [Yamada 2019].

#### Analysis A4: Ground Metric Comparison on Real Data

**Question**: Does the ToM graph metric add information beyond the trivial and linear alternatives on real annotation data?

**Method**: For all analyses above (A1–A3), report results under all 5 ground metrics M1–M5. Compare discriminative power (effect sizes, cluster quality).

**Key comparisons** (paralleling B5):
1. Structure vs. none: M2 vs. M1
2. Calibration vs. uniform: M3 vs. M2
3. 2D vs. 1D: M4 vs. M2
4. Structure vs. ordering: M2 vs. M5

**Statistical test**: Paired Wilcoxon signed-rank test on effect sizes across ground metrics.

---

## 4. Track B: Synthetic Student Trajectories

Track B is executed *after* Track A. The synthetic archetypes and parameters below are initialized from published literature, but are subject to revision based on Track A findings. Specifically:

- If WMT rater clustering (A2) reveals annotation patterns that map to different archetypes than our initial 5, we add or modify archetypes accordingly
- If the WMT per-rater error category distributions (A1) suggest different baseline detection rates per skill, we update §4.1.1
- If the ground metric comparison on real data (A4) shows M3 or M4 outperforming M2, we use the best-performing metric as the primary in Track B analyses

This dependency is the key methodological advantage of the A-before-B ordering: Track B's controlled demonstrations are grounded in Track A's empirical findings, not solely in literature estimates.

### 4.1 Empirically Calibrated Parameters (Initial — Subject to Track A Revision)

All synthetic parameters are grounded in published empirical data. These serve as initial values; Track A findings may lead to adjustments before Track B execution.

#### 4.1.1 Baseline Detection Rates (session 1)

From the empirical compendium (§2 of the research report):

| Skill | Student Detection Rate | Source | σ (variance) |
|---|---|---|---|
| S1 Surface | 90–95% | ES→EN trainee: 93% syntax | 0.05 |
| S2 Grammar | 80–90% | Daems et al. 2017; WMT annotator data | 0.08 |
| S3 Meaning | 70–85% | ES→EN trainee: 80% mistranslation | 0.10 |
| S4 Completeness | 55–70% | ES→EN: 67% omission; Yamada 2019: 68% overall | 0.12 |
| S5 Terminology | 50–65% | Bio-MQM domain gap; Herget 2021 term errors | 0.12 |
| S6 Pragmatic | 40–55% | Herget 2021: 30% accepted wrong register | 0.15 |
| S7 Discourse | 25–40% | Daems 2017: students missed coherence errors entirely | 0.15 |

**Overall calibration**: Yamada 2019 median correction rate **68%** (range 40–90%). Our profiles should span this range.

#### 4.1.2 Learning Rates (per session)

From Koponen 2015 (Helsinki PE course) and Mellinger & Shreve 2016:

| Skill | Learning Rate per Session | Source |
|---|---|---|
| S1 Surface | 0.03 (fast, ceiling quickly) | Temnikova: easiest errors |
| S2 Grammar | 0.025 | Daems: moderate effort |
| S3 Meaning | 0.02 | Lacruz et al. 2014: transfer errors harder |
| S4 Completeness | 0.015 | Yamada 2019: omission detection resistant to training |
| S5 Terminology | 0.015 | Domain knowledge builds slowly |
| S6 Pragmatic | 0.01 | Register sensitivity develops late |
| S7 Discourse | 0.008 | Daems: coherence is last to develop |

#### 4.1.3 Over-Editing Rates

From Koponen & Salmi 2017 and De Almeida 2013:
- Students: 34–38% of all edits unnecessary [Koponen et al. 2019]
- Professionals: 16–25% [De Almeida 2013]
- Starting rate: 35%, decreasing ~2% per session as skill develops

### 4.2 Student Archetypes

We generate 5 archetypal learning trajectories, each representing a distinct pattern observed in the literature:

#### Archetype 1: Coherent Learner (n=5 instances)

The "textbook" progression — masters skills sequentially along the ToM hierarchy. Based on the developmental ordering in Temnikova 2010 and the PACTE competence model.

```
Session 1: S1=0.65, S2=0.50, S3=0.35, S4=0.25, S5=0.20, S6=0.15, S7=0.10
Session 10: S1=0.95, S2=0.88, S3=0.72, S4=0.55, S5=0.48, S6=0.35, S7=0.22

Learning dynamic: Frontline skills (lowest mastered above threshold) improve 
fastest. Each skill's learning rate accelerates when its prerequisites are mastered.
```

#### Archetype 2: Scattered Learner (n=5 instances)

Improves on random skills each session. No developmental coherence. Same total improvement as Archetype 1 but distributed differently. Based on Herget 2021's finding of 4× variance with no clear progression pattern.

```
Session 1: S1=0.65, S2=0.50, S3=0.35, S4=0.25, S5=0.20, S6=0.15, S7=0.10
Session 10: S1=0.80, S2=0.55, S3=0.65, S4=0.30, S5=0.60, S6=0.20, S7=0.45

Learning dynamic: Each session, a random subset of skills improves. 
Total mastery gain equals Archetype 1.
```

#### Archetype 3: Fast Starter / Plateau (n=4 instances)

Rapid early improvement on surface skills, then stagnation. Based on Yamada 2019's finding that students reach a ceiling quickly for NMT PE.

```
Session 1: S1=0.65, S2=0.50, S3=0.35, S4=0.25, S5=0.20, S6=0.15, S7=0.10
Session 4: S1=0.92, S2=0.82, S3=0.55, S4=0.35, S5=0.30, S6=0.20, S7=0.12
Session 10: S1=0.93, S2=0.83, S3=0.58, S4=0.38, S5=0.32, S6=0.22, S7=0.14

Learning dynamic: Learning rates halve after session 4. Surface skills 
reach ceiling; deeper skills barely improve.
```

#### Archetype 4: Slow Steady (n=3 instances)

Gradual uniform improvement across all skills. Uncommon but represents a student who doesn't differentiate by difficulty. Based on the observation that some students show flat effort profiles [Daems et al. 2017].

```
Session 1: S1=0.65, S2=0.50, S3=0.35, S4=0.25, S5=0.20, S6=0.15, S7=0.10
Session 10: S1=0.82, S2=0.67, S3=0.52, S4=0.42, S5=0.37, S6=0.32, S7=0.27

Learning dynamic: All skills improve at the same absolute rate (+0.017/session).
```

#### Archetype 5: Surface-Only (n=3 instances)

Masters surface skills but cannot progress to meaning-level errors. Based on Stasimioti & Sosoni 2021's finding that some translators overcorrect surface issues while missing accuracy errors.

```
Session 1: S1=0.65, S2=0.50, S3=0.35, S4=0.25, S5=0.20, S6=0.15, S7=0.10
Session 10: S1=0.96, S2=0.92, S3=0.40, S4=0.28, S5=0.22, S6=0.18, S7=0.12

Learning dynamic: S1-S2 improve at 2× normal rate; S3+ improve at 0.3× normal rate.
Over-editing rate remains high (>30%) because student "edits" surface 
forms that are already correct.
```

### 4.3 Trajectory Generation

Each archetype generates multiple instances with added noise:

```python
import numpy as np

def generate_trajectory(archetype, n_sessions=10, noise_std=0.03, seed=None):
    """
    Generate a student trajectory based on archetype parameters.
    
    Returns: List of skill profile dicts, one per session.
    """
    rng = np.random.default_rng(seed)
    
    # Base detection rates at session 1
    base = np.array(archetype["initial"])  # 7 values
    learning_rates = np.array(archetype["learning_rates"])  # 7 values
    
    trajectory = []
    current = base.copy()
    
    for t in range(n_sessions):
        # Add noise
        noisy = current + rng.normal(0, noise_std, size=7)
        noisy = np.clip(noisy, 0.0, 1.0)
        
        trajectory.append({
            f"S{k+1}": float(noisy[k]) for k in range(7)
        })
        
        # Update based on archetype-specific learning dynamic
        current = archetype["update_fn"](current, learning_rates, t, rng)
        current = np.clip(current, 0.0, 1.0)
    
    return trajectory

# Total: 5+5+4+3+3 = 20 synthetic students × 10 sessions = 200 profiles
```

### 4.4 BKT Integration

For each synthetic student, we also run BKT to produce mastery estimates that may differ from raw detection rates:

```python
# Per-skill BKT parameters (from Analytics Spec §1.2, now calibrated)
BKT_PARAMS = {
    "S1": {"P_L0": 0.35, "P_T": 0.15, "P_G": 0.25, "P_S": 0.05},
    "S2": {"P_L0": 0.25, "P_T": 0.12, "P_G": 0.20, "P_S": 0.08},
    "S3": {"P_L0": 0.15, "P_T": 0.10, "P_G": 0.15, "P_S": 0.12},
    "S4": {"P_L0": 0.08, "P_T": 0.08, "P_G": 0.20, "P_S": 0.15},
    "S5": {"P_L0": 0.10, "P_T": 0.08, "P_G": 0.10, "P_S": 0.12},
    "S6": {"P_L0": 0.06, "P_T": 0.06, "P_G": 0.15, "P_S": 0.15},
    "S7": {"P_L0": 0.04, "P_T": 0.05, "P_G": 0.10, "P_S": 0.18},
}
```

We compute W₁ on both raw detection rates AND BKT mastery estimates, comparing whether BKT smoothing affects the metric's discriminative power.

---

## 5. Analyses

### 5.1 Analysis B1: Archetype Discrimination

**Question**: Does W₁ separate the 5 archetypes better than Euclidean distance?

**Method**:
1. For each pair of archetypes, compute the between-archetype W₁ and Euclidean distances (averaged across instances)
2. For each archetype, compute the within-archetype W₁ and Euclidean distances
3. Compute the Fisher discriminant ratio: between-class variance / within-class variance
4. Compare Fisher ratios for W₁ (graph), W₁ (linear), W₁ (trivial), Euclidean, and cosine

**Expected result**: W₁ (graph) should produce the highest Fisher ratio, indicating the best separation between meaningfully different learning patterns. Specifically, it should separate Coherent (Archetype 1) from Scattered (Archetype 2) better than Euclidean, because these two archetypes have similar total mastery but different structural coherence.

**Key comparison**: Archetype 1 vs. Archetype 2 at session 10. Both have similar average detection rates (~0.60), but Archetype 1's profile is concentrated on adjacent skills (high S1–S3, low S4–S7) while Archetype 2's is scattered. Euclidean distance: similar. W₁ (graph): should be significantly different because the "cost" of Archetype 2's scattered improvements is higher under the graph metric.

### 5.2 Analysis B2: MasteryGap Trajectory Comparison

**Question**: Does W₁ MasteryGap decrease faster for coherent learners than scattered learners?

**Method**:
1. Compute W₁(student(t), target) for each student at each session
2. Plot MasteryGap trajectories for all 20 students, grouped by archetype
3. Compute the area under the MasteryGap curve (AUC-MG) for each student
4. Compare AUC-MG across archetypes using Kruskal-Wallis test
5. Repeat with Euclidean MasteryGap for comparison

**Expected result**: Coherent Learners should have the steepest MasteryGap decrease (lowest AUC-MG) because their improvements are "cheap" in transport cost — they improve adjacent skills. Scattered Learners should have slower decrease despite similar total improvement. Fast Starters should show steep initial decrease then plateau. Surface-Only should plateau early with high remaining MasteryGap.

**Visualization**: Line plot with session on x-axis, MasteryGap on y-axis, one line per student (colored by archetype). This becomes a key figure in the paper.

### 5.3 Analysis B3: Trajectory Efficiency

**Question**: Can W₁ trajectory efficiency distinguish "direct" from "indirect" learning paths?

**Method**:
From the Wasserstein Formalization v1.0 §6.3:

$$\text{Efficiency} = \frac{W_1(\mu(t_1), \mu(t_T))}{\sum_{t=1}^{T-1} W_1(\mu(t), \mu(t+1))}$$

- 1.0 = perfectly direct path (each session moves strictly toward the final profile)
- <1.0 = detours (some sessions moved in "wrong" direction)

**Expected result**:
- Coherent Learner: efficiency ~0.85–0.95 (mostly direct, minor noise)
- Scattered Learner: efficiency ~0.50–0.70 (significant detours)
- Fast Starter/Plateau: efficiency ~0.40–0.60 (high early, near-zero later = wasted sessions)
- Slow Steady: efficiency ~0.90–0.95 (direct but slow)
- Surface-Only: efficiency ~0.70–0.80 (direct but limited scope)

### 5.4 Analysis B4: Peer Comparison (Class Barycenter)

**Question**: Does the Wasserstein barycenter provide a more meaningful "class average" than arithmetic mean of profiles?

**Method**:
1. Compute arithmetic mean of all 20 student profiles at session 10
2. Compute Wasserstein barycenter using `ot.barycenter(A, M, reg)` with graph metric
3. Compare: does the barycenter better represent the "typical student"?
4. Compute W₁(student, barycenter) and W₁(student, arithmetic_mean) for each student
5. Correlate each with teacher's readiness judgment (simulated as: student is ready for next level if MasteryGap < threshold)

**Expected result**: The Wasserstein barycenter should be "smoother" than the arithmetic mean — it preserves the ToM ordering in the average, while the arithmetic mean can produce profiles that don't correspond to any real student.

### 5.5 Analysis B5: Ground Metric Sensitivity

**Question**: How sensitive are all results to the specific ground metric, and does the ToM-informed structure add discriminative power?

**Method**: Run all analyses (B1–B4) with every ground metric from §2:

| ID | Ground Metric | What It Tests |
|---|---|---|
| M1 | Trivial | Null baseline (W₁ = Total Variation) |
| M2 | Unweighted graph | Does prerequisite structure help? |
| M3 | Weighted graph | Does empirical calibration help beyond topology? |
| M4 | 2D embedding | Does ToM × linguistic grain separation help? |
| M5 | Uniform linear | Does simple ordering suffice? |
| M_rand | Random ×10 | Statistical null: does *any* structure beat random? |

**Planned comparisons** (each tested via paired Wilcoxon on effect sizes across all B1–B4 analyses):

1. **Structure vs. none**: M2 vs. M1 — does graph structure beat trivial?
2. **Specific structure vs. random**: M2 vs. M_rand — does *our* graph beat random graphs?
3. **Calibration vs. uniform weighting**: M3 vs. M2 — do empirically weighted edges add value?
4. **2D vs. 1D**: M4 vs. M2 — does the second dimension (linguistic grain) add information?
5. **Structure vs. ordering**: M2 vs. M5 — does the branching structure matter, or does simple linear ordering suffice?
6. **Best ToM metric vs. best baseline**: max(M2, M3, M4) vs. max(M1, M5) — overall structured vs. unstructured

**Expected result hierarchy**: M3 ≥ M4 ≥ M2 > M5 > M1 ≈ M_rand. The weighted graph should perform best because it combines topological structure with empirical calibration. The 2D embedding should add modest improvement over unweighted graph by separating the ToM and linguistic dimensions. Any structured metric should substantially outperform trivial and random.

**Key figure** (F5): Heatmap with ground metrics on rows, analyses (B1–B4) on columns, cells colored by effect size. Demonstrates which metric wins on which analysis.

### 5.6 Analysis B6: Robustness to BKT Smoothing

**Question**: Does computing W₁ on BKT mastery estimates (smoothed) vs. raw detection rates (noisy) change the conclusions?

**Method**: Run B1–B3 using both:
- Raw profiles: direct detection rates per skill per session
- BKT profiles: P(L_k^t) estimates after BKT updating

**Expected result**: BKT smoothing should reduce noise in individual profiles, making archetype separation cleaner. But the *relative ordering* of metrics (W₁ graph > W₁ linear > Euclidean) should be preserved. If BKT smoothing eliminates the advantage of W₁ (because it already captures learning dynamics), that's an important finding about the interaction between the learner model and the progress metric.

### 5.7 Analysis B7: Balanced vs. Unbalanced Optimal Transport

**Question**: Does the unnormalized formulation (unbalanced OT) capture information that balanced W₁ misses?

**Method**:
1. For each synthetic student at each session, compute both:
   - Balanced W₁(normalized_μ(t), normalized_μ*) using `ot.emd2`
   - Unbalanced UW₁(raw_m(t), raw_m*) using `ot.unbalanced.sinkhorn_unbalanced2` with reg_m ∈ {0.1, 0.5, 1.0, 5.0}
2. Compare discriminative power (Fisher ratio on B1) under both formulations
3. Compute correlation between balanced and unbalanced MasteryGap trajectories (B2)
4. Identify cases where they diverge

**Key divergence scenario**: Archetype 4 (Slow Steady) improves uniformly across all skills by +0.017/session. Under balanced W₁, the normalized profile barely changes (shape is constant). Under unbalanced OT, the total mass increase is captured — the student *is* getting better, even though their relative profile stays the same. If unbalanced W₁ correctly identifies this improvement while balanced W₁ misses it, that demonstrates complementary value.

**Counterpoint scenario**: Two students with identical shapes but different magnitudes ([0.9, 0.8, 0.7, ...] vs. [0.45, 0.40, 0.35, ...]). Balanced W₁ says they're identical; unbalanced says the first is much closer to mastery. Both are "correct" — they answer different questions. We report both to give the teacher maximum information.

**Sensitivity to reg_m**: The unbalanced OT penalty parameter controls the cost of mass creation/destruction. Low reg_m → strict mass conservation (approaches balanced). High reg_m → permissive mass change. We test 4 values and report the effect on discrimination.

**Implementation**:
```python
import ot

def compute_unbalanced_w1(profile_a, profile_b, cost_matrix, reg=0.01, reg_m=1.0):
    """Unbalanced W1 using Sinkhorn with KL marginal penalty."""
    a = np.array([profile_a[f"S{k}"] for k in range(1, 8)], dtype=float)
    b = np.array([profile_b[f"S{k}"] for k in range(1, 8)], dtype=float)
    a = np.maximum(a, 1e-8)
    b = np.maximum(b, 1e-8)
    return ot.unbalanced.sinkhorn_unbalanced2(a, b, cost_matrix, reg, reg_m)
```

---

## 6. Statistical Analysis Plan

### 6.1 Summary of Tests

| Analysis | Test | Comparison | Expected Effect |
|---|---|---|---|
| A1 Inter-rater distances | Spearman ρ | W₁ vs. Euclidean rankings | ρ < 1.0 (different rankings) |
| A2 Rater clustering | Silhouette score | W₁-medoids vs. Euclidean-medoids | Higher silhouette for W₁ |
| A3 System quality × agreement | Pearson r | W₁ vs. system MQM score | Positive correlation |
| A4 Ground metric comparison | Paired Wilcoxon | Effect sizes across M1–M5 | M3 ≥ M4 ≥ M2 > M5 > M1 |
| B1 Archetype discrimination | Fisher discriminant ratio | W₁ (M2/M3/M4) vs. Euclidean | Higher Fisher for W₁ |
| B2 MasteryGap trajectories | Kruskal-Wallis | AUC-MG across archetypes | Significant difference |
| B3 Trajectory efficiency | Descriptive + ANOVA | Efficiency across archetypes | Coherent > Scattered |
| B4 Barycenter comparison | Correlation with readiness | W₁-barycenter vs. mean-based | Higher correlation for W₁ |
| B5 Ground metric sensitivity | 6 planned comparisons | M1–M5 + M_rand pairwise | Structured > unstructured |
| B6 BKT robustness | Paired comparison | Raw vs. BKT profiles | Consistent metric rankings |
| B7 Balanced vs. unbalanced | Fisher ratio + correlation | Balanced W₁ vs. UW₁ at 4 reg_m values | Complementary information |

### 6.2 Multiple Comparisons

With 10+ analyses, we apply Bonferroni correction within each track (A and B independently). Significant findings require p < 0.05 / (number of tests in track).

### 6.3 Effect Size Reporting

For all comparisons, report:
- Cohen's d (for continuous comparisons)
- Cliff's delta (for ordinal/non-parametric)
- 95% bootstrap confidence intervals

---

## 7. Expected Deliverables

### 7.1 Figures

| Figure | Content | Demonstrates |
|---|---|---|
| **F1** | Radar charts: 5 archetypes at session 1 and session 10 | Visual grounding of archetypes |
| **F2** | MasteryGap trajectory plot (20 students, colored by archetype) | W₁ distinguishes learning patterns over time |
| **F3** | Archetype discrimination: Fisher ratio bar chart across all ground metrics (M1–M5) and Euclidean | Ground metric matters |
| **F4** | Heatmap: pairwise W₁ between all 20 students at session 10 | Cluster structure visible |
| **F5** | Ground metric sensitivity heatmap: metrics (rows) × analyses (columns) × effect sizes (color) | Comprehensive ground metric comparison |
| **F6** | WMT inter-rater W₁ distribution by system quality | Real-data validation |
| **F7** | Linearized vs. graph W₁ scatter plot (correlation) | Quantifies information loss from linearization |
| **F8** | Transport plan visualization: what "moves where" from a student to the target profile | Pedagogical intuition for the EMD metaphor |
| **F9** | Ground metric matrices visualized as heatmaps (M1–M5 side by side) | Structural differences between metrics |
| **F10** | Balanced vs. unbalanced MasteryGap trajectories for Archetype 4 (Slow Steady) | Where normalization matters |
| **F11** | 2D embedding space visualization: skills as points, students as trajectory arrows | ToM × linguistic grain structure |
| **F12** | Permutation null distribution + observed M2/M3/M4 effect sizes | Statistical evidence for structural grounding |

### 7.2 Tables

| Table | Content |
|---|---|
| **T1** | All ground metric matrices (M1–M5) with formal definitions |
| **T2** | Archetype parameters + empirical sources (detection rates, learning rates, sources) |
| **T3** | Complete results matrix: all analyses (A1–A4, B1–B7) × all metrics (M1–M5, Euclidean, cosine) |
| **T4** | WMT MQM rater profile statistics (per-rater category distributions) |
| **T5** | Statistical test results with effect sizes, CIs, and Bonferroni-corrected p-values |
| **T6** | Balanced vs. unbalanced OT comparison: correlation and divergence cases |
| **T7** | B5 planned comparisons: effect sizes for each of the 6 pairwise ground metric tests |

### 7.3 Code Deliverables

| File | Purpose |
|---|---|
| `experiments/wasserstein/ground_metrics.py` | All 5 ground metric matrices (M1–M5) + random generator |
| `experiments/wasserstein/metrics.py` | Balanced W₁, unbalanced UW₁, efficiency, barycenter — all with configurable ground metric |
| `experiments/wasserstein/wmt_analysis.py` | Track A: WMT data loading, profile extraction, analyses A1–A4 |
| `experiments/wasserstein/synthetic_trajectories.py` | Track B: 5 archetype definitions, trajectory generation with BKT integration |
| `experiments/wasserstein/analysis.py` | All statistical analyses (B1–B7) with ground metric sweep |
| `experiments/wasserstein/visualizations.py` | Figure generation (F1–F12) |
| `experiments/wasserstein/run_all.py` | Full pipeline: data → analysis → figures → tables → LaTeX snippets |
| `experiments/wasserstein/config.py` | Archetype parameters, BKT priors, target profile, reg_m values — all in one place |

---

## 8. Limitations and Threats to Validity

### 8.1 Construct Validity

**WMT annotators are not students**: WMT MQM raters are professional translators, not translation students. Their error detection profiles may differ systematically from students (e.g., higher detection rates across all categories, different error-type preferences). Track A demonstrates the *metric* works, not that the *student profiles* are realistic — Track B addresses that with empirically calibrated synthetic data.

**S7 (Discourse) is unobservable in segment-level data**: Both WMT and our BKT model treat segments independently. Discourse-level errors spanning multiple segments cannot be captured. This means our 7-skill model is effectively a 6-skill model until we add multi-segment exercises.

**Normalization choice affects interpretation**: Balanced and unbalanced OT answer different questions ("what shape is the profile?" vs. "how much mastery and where?"). Neither is universally correct. We report both and explicitly state what each captures, but readers may conflate them if not careful.

### 8.2 Internal Validity

**Synthetic trajectories may not capture real learning dynamics**: We calibrate from published averages, but individual learning trajectories can be far more erratic. The 5 archetypes are idealized — real students may combine features of multiple archetypes or transition between them.

**BKT parameter sensitivity**: The BKT priors influence the mastery estimates, which influence the W₁ computation. We mitigate by testing both raw and BKT profiles (Analysis B6) and by reporting sensitivity to BKT parameter ranges.

**Ground metric circularity risk**: The weighted ground metric (M3) is calibrated from the *same* detection rate literature used to generate synthetic profiles. This could inflate M3's performance. Mitigation: M3's advantage over M2 (unweighted, no circularity) is the critical comparison. If M2 alone significantly outperforms M1/M5/M_rand, the contribution holds independently of calibration.

### 8.3 External Validity

**Language-pair specificity**: WMT data is EN→DE and ZH→EN. Our system targets FR↔EN. Error distributions differ by language pair (the empirical compendium shows 33% vs. 42% mistranslation rates for EN→DE vs. ZH→EN). The ToM skill ordering should be language-pair-independent (it's based on cognitive demands, not linguistic features), but the specific detection rates may shift.

**Generalizability of the ground metric**: Our ground metric is derived from the ToM hierarchy, which is specific to MT PE pedagogy. For other educational domains, a different ground metric would be needed. The *method* (optimal transport with pedagogical ground metric) generalizes; the *specific metric* does not.

**Generalizability of optimal transport to other ITS**: The approach — define a meaningful ground metric over your knowledge component space, then use W₁ to measure progress — is domain-independent. Any ITS with hierarchically structured KCs (math prerequisite chains, programming skill trees, language proficiency levels) could apply the same methodology with a domain-appropriate ground metric. We discuss this explicitly in the paper as a contribution beyond MT PE.

---

## 9. Timeline

### 9.1 Experimental Implementation (4 weeks)

| Week | Task | Deliverable | Rationale |
|---|---|---|---|
| 1 | Implement ground metrics (M1–M5 + random), balanced + unbalanced W₁ | `ground_metrics.py`, `metrics.py` | Foundation for both tracks |
| 1 | Download WMT data (HuggingFace), implement profile extraction pipeline | `wmt_analysis.py` | Track A data ready |
| 2 | **Run Track A analyses (A1–A4)** with all ground metrics | Track A results, figures F6–F7, F9 | **Real-data validation first** |
| 2 | Analyze Track A findings: rater clusters, detection patterns, ground metric ranking | Revised archetype parameters if needed | **Track A informs Track B** |
| 3 | Implement synthetic trajectory generation (archetypes calibrated from A + literature) | `synthetic_trajectories.py`, `config.py` | Grounded in real data |
| 3 | Run Track B core analyses (B1–B3, B5) with all ground metrics | Core results, figures F1–F5, F12 | Controlled demonstrations |
| 4 | Run Track B extended analyses (B4, B6–B7: barycenter, BKT, normalization) | Extended results, figures F10–F11 | Complete analysis suite |
| 4 | Statistical analysis, remaining figures/tables, write-up | All tables T1–T7, draft paper section | Publication-ready |

**Critical path**: Week 1 (infrastructure) → Week 2 (Track A — real data) → Week 3 (Track B — synthetic, informed by A) → Week 4 (extended analyses + write-up).

**Key decision point at end of Week 2**: After Track A results are in, review whether:
- The initial archetype parameters (§4.1) need revision based on observed rater profiles
- Any new archetypes should be added based on discovered clustering patterns
- The ground metric ranking from A4 changes which metric is primary for Track B

### 9.2 Empirical Validation Roadmap (beyond 4-week experimental window)

| Phase | Timeline | Data Source | What It Adds |
|---|---|---|---|
| **Phase 0** (current) | Weeks 1–4 | WMT MQM (Track A, first) → Synthetic calibrated from A (Track B) | Method validation on real + controlled data |
| **Phase 1** | April–May | Contact UCLouvain for MTPEAS FR-EN data | Real student PE data in target language pair; stronger archetype calibration |
| **Phase 2** | May–June | ToM-PE pilot (5–10 students, 3–5 sessions) | First live W₁ computations; preliminary deployment data for CIKM demo |
| **Phase 3** | Fall 2026 | Full semester deployment | Complete empirical validation with real learning trajectories |

Phase 0 results (Track A real-data + Track B synthetic) are sufficient for EC-TEL. Phase 1 data (if obtainable) strengthens CIKM by adding student-level (not just annotator-level) profiles. Phase 2 provides the CIKM demo video content. Phase 3 is the full journal paper.

---

## 10. Connection to Publication Strategy

### 10.1 Where This Fits

The experimental results from this spec can support multiple publication targets:

| Venue | Deadline | What to Include | Framing |
|---|---|---|---|
| **EC-TEL 2026** | April 10 | Theoretical framework + Track A real-data results (A1–A2, A4) + Track B selected (B1–B3, B5) | "Novel progress metric grounded in ToM — validated on WMT MQM data and synthetic trajectories" |
| **CIKM 2026** | ~mid-June | System demo + full Track A (A1–A4) + B7 normalization + live pilot data if available | "Real-data validation within a deployed PE training system" |
| **Standalone paper** (LAK/AIED/EDM 2027) | Varies | Full Track A + B (all analyses) + ground metric comparison + normalization study | "Optimal Transport for Multi-Skill Learning Analytics: Theory, Method, and Validation" |
| **Journal** (IEEE TLT / JMLR / UMUAI) | Open | Full treatment + Phase 3 deployed data | "Theory + method + empirical validation at scale" |

### 10.2 Minimum Viable Results for EC-TEL (April 10)

Given the 3-week window, the minimum we need is:
- Ground metric definitions (M1–M5) from §2
- **Track A completed**: WMT rater profiles extracted, A1 (inter-rater distances) and A2 (rater clustering) computed — provides real-data validation
- Track B archetypes defined (calibrated from A + literature), trajectories generated
- B1 (archetype discrimination): Fisher ratio across M1–M5 + Euclidean → Figure F3
- B2 (MasteryGap trajectories): 20-student trajectory plot → Figure F2
- B5 (ground metric sensitivity): at least the 6 planned comparisons
- The theoretical framework from Wasserstein Formalization v1.0

This is achievable in 3 weeks: Week 1 infrastructure + WMT loading, Week 2 Track A + Track B generation, Week 3 Track B analyses + write-up. The paper leads with Track A real-data findings and uses Track B for theoretical demonstrations — a stronger narrative than synthetic-only.

### 10.3 Contribution Framing by Venue

**For EC-TEL** (education/TEL audience): Lead with the pedagogical motivation and real-data validation. "Standard learning analytics treat all skills as independent. We propose a metric grounded in Theory of Mind that captures the *structural coherence* of skill development. We validate on 42,000+ WMT MQM annotations, showing that the metric distinguishes annotation profiles that pointwise metrics conflate, and demonstrate via calibrated simulations that it tracks learning progressions meaningfully." Technical details (OT, EMD, ground metrics) go in a methods section; the emphasis is on what the metric *means* for teachers and learners.

**For CIKM** (information systems audience): Lead with the system architecture. The Wasserstein metric is one component of a comprehensive PE training platform. Emphasize the real-data validation (Track A) and the system's analytics dashboard.

**For a standalone learning analytics paper** (LAK/AIED/EDM): Lead with the methodological contribution. "We introduce optimal transport with pedagogically grounded ground metrics as a general framework for measuring multi-skill learning progress." Full comparison of 5 ground metrics, balanced vs. unbalanced, BKT interaction. The ToM-PE application is the motivating example but the method generalizes to any hierarchical KC structure.

**For a journal**: All of the above plus full empirical validation from deployed system.
