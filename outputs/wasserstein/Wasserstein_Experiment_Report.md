# Wasserstein Distance Metric Validation for PE Skill Profiling

## Experiment Report

**Date:** 2026-03-19
**Spec version:** ToM-PE_Wasserstein_Experimental_Spec_v2

---

## 1. Overview

This report documents a two-track validation of the Wasserstein-1 (W1) distance metric applied to student translation skill profiles. The experiments test whether optimal transport (OT) with pedagogically-informed ground metrics better captures learning progression than traditional pointwise metrics (Euclidean, cosine).

The core hypothesis is that W1, by respecting the structure of the skill space through a ground metric, can detect pedagogically meaningful patterns -- such as coherent vs. incoherent skill development -- that pointwise metrics miss because they treat all skill dimensions as independent.

### Research Questions

| RQ | Question |
|---|---|
| RQ1 | Does W1 with ToM ground metric distinguish structurally different student profiles? |
| RQ2 | Does W1 detect coherent vs. incoherent skill progression more reliably? |
| RQ3 | How sensitive is W1 to ground metric choice? |
| RQ4 | Does W1-based mastery distance correlate better with pedagogical outcomes? |
| RQ5 | Information loss in 1D linearisation vs. full graph formulation? |
| RQ6 | Does unbalanced OT add discriminative power over balanced OT? |
| RQ7 | Do empirically calibrated weighted metrics outperform unweighted? |

---

## 2. Skill Space Definition

All experiments operate over a 7-dimensional skill space S1--S7, ordered by the ToM framework's cognitive hierarchy:

| Skill | Domain | Baseline Detection | Learning Rate | ToM Level |
|---|---|---|---|---|
| S1 Surface | Spelling, punctuation | 93% | 0.030 | 1st_machine |
| S2 Grammar | Grammar, word form | 85% | 0.025 | 1st_machine |
| S3 Meaning | Mistranslation, false cognate | 80% | 0.020 | 1st_machine (meaning) |
| S4 Completeness | Omission, addition | 67% | 0.015 | 1st_author |
| S5 Terminology | Domain terms | 65% | 0.012 | 2nd_reader |
| S6 Pragmatic | Register, style, locale | 50% | 0.010 | 2nd_reader |
| S7 Discourse | Coherence, cohesion | 35% | 0.008 | Recursive |

**Target profile (expert):** [0.95, 0.90, 0.85, 0.80, 0.80, 0.75, 0.70]

A student profile is a 7-vector of detection rates. The skill adjacency structure encodes prerequisite relationships (e.g., S1->S2->S3, S3->S4, S3->S5/S6, S6->S7).

---

## 3. Ground Metrics

Five ground metrics define how "far apart" two skills are in the pedagogical space. The ground metric is the cost matrix that W1 uses to determine how expensive it is to move probability mass between skill bins.

### 3.1 M1: Trivial (Baseline)

**Definition:** D(i,j) = 1 - delta(i,j). All off-diagonal entries = 1.

**Purpose:** Null baseline. W1 with trivial metric reduces to Total Variation distance. Any structured metric should outperform M1.

### 3.2 M2: Unweighted Graph

**Definition:** D(i,j) = shortest_path(i,j) / max_path on the skill dependency graph. All edges have equal weight.

**Purpose:** Captures prerequisite topology without empirical calibration. Tests whether structure alone (RQ1) matters.

**Example distances:** S1-S2 = 0.25, S1-S7 = 1.0, S3-S6 = 0.50.

### 3.3 M3: Weighted Graph (Empirically Calibrated)

**Definition:** Edge weights = |baseline_detection(i) - baseline_detection(j)|. Shortest weighted path, normalised.

**Purpose:** Adds empirical calibration to the graph structure. Tests RQ7 (does calibration help?).

**Key weights:**
- S1->S2: |93%-85%| = 8 (small cognitive step)
- S3->S6: |80%-50%| = 30 (large cognitive jump)
- S6->S7: |50%-35%| = 15 (moderate)

### 3.4 M4: 2D Embedding

**Definition:** Skills embedded in 2D space (linguistic grain x ToM level). Distance = Euclidean in this space, normalised.

**Purpose:** Tests whether a low-dimensional continuous embedding captures the same structure as the discrete graph (RQ5).

**Embedding coordinates:**
- Axis 1: Linguistic grain (word -> phrase -> sentence -> multi-sentence)
- Axis 2: ToM level (machine form -> author -> reader -> recursive)

### 3.5 M5: Uniform Linear (Control)

**Definition:** D(i,j) = |i-j|/6 for skills indexed 0-6.

**Purpose:** Control metric -- tests whether simple ordinal distance suffices, or whether graph/embedding structure adds value.

### 3.6 M_rand: Random Null (10 instances)

**Definition:** Random symmetric positive matrices. Used as permutation null distribution for B5.

---

## 4. Distance Metrics

### 4.1 Balanced W1 (Normalised)

Profiles are normalised to probability distributions (sum = 1) before computing the optimal transport cost. This captures the *shape* of the skill distribution, ignoring overall magnitude.

**Computation:** Exact linear program via `ot.emd2`.

### 4.2 Unbalanced W1 (Sinkhorn)

Raw mastery values are used without normalisation. Sinkhorn algorithm with KL marginal penalties allows mass creation/destruction. This captures both *shape* and *magnitude* of skill growth.

**Parameters:**
- Entropic regularisation: reg = 0.01
- Marginal relaxation: reg_m swept over {0.1, 0.5, 1.0, 5.0}

### 4.3 Baselines

- **Euclidean:** L2 norm of profile difference
- **Cosine:** 1 - cosine similarity

---

## 5. Track A: WMT MQM Rater Profiles

### 5.1 Data Source

**WMT 2020 Metrics Shared Task**, EN-DE language pair.

| Statistic | Value |
|---|---|
| Total annotations | 79,020 |
| Unique raters | 6 |
| Segments with multi-rater coverage | 14,180 |
| Total pairwise rater comparisons | 42,538 |

Annotations use the MQM taxonomy (Accuracy, Fluency, Terminology, Style, etc.) which maps to our S1-S7 skill space.

### 5.2 Rater Profiles (Raw Error Counts)

| Rater | S1 | S2 | S3 | S4 | S5 | S6 | S7 | Total |
|---|---|---|---|---|---|---|---|---|
| rater1 | 2,526 | 1,070 | 2,368 | 1,207 | 1,178 | 1,274 | 0 | 9,623 |
| rater2 | 2,576 | 1,686 | 3,139 | 677 | 468 | 3,103 | 0 | 11,649 |
| rater3 | 2,062 | 1,092 | 2,789 | 1,361 | 1,581 | 1,465 | 0 | 10,350 |
| rater4 | 2,376 | 1,090 | 4,646 | 874 | 1,046 | 1,895 | 0 | 11,927 |
| rater5 | 1,976 | 671 | 3,379 | 436 | 380 | 1,635 | 0 | 8,477 |
| rater6 | 2,343 | 1,035 | 4,893 | 1,034 | 917 | 989 | 0 | 11,211 |

**Observations:**
- S3 (Meaning/Mistranslation) dominates for most raters, especially rater4 and rater6
- S7 (Discourse) = 0 for all raters -- WMT MQM annotations rarely capture inter-sentential errors
- rater2 has an unusual S6 emphasis (3,103 style annotations vs. only 468 for S5)
- Profiles show meaningful individual variation in annotation focus

### 5.3 Analysis A1: Inter-Rater Distances

For each of the 14,180 segments with 2+ raters, all pairwise W1 distances were computed (42,538 pairs). Spearman correlation between W1 ranking and Euclidean ranking was computed per ground metric.

| Ground Metric | Spearman rho | p-value | W1 Mean | W1 Std | Euc Mean | Euc Std |
|---|---|---|---|---|---|---|
| M1_trivial | 0.678 | < 0.001 | 0.511 | 0.384 | 1.247 | 1.011 |
| M2_graph | 0.599 | < 0.001 | 0.214 | 0.181 | 1.247 | 1.011 |
| M3_weighted | 0.589 | < 0.001 | 0.215 | 0.192 | 1.247 | 1.011 |
| M4_2d | 0.588 | < 0.001 | 0.197 | 0.159 | 1.247 | 1.011 |
| M5_linear | 0.607 | < 0.001 | 0.195 | 0.170 | 1.247 | 1.011 |
| M_rand (mean) | 0.619 | < 0.001 | 0.340 | 0.267 | 1.247 | 1.011 |

**Interpretation:**
- Lower Spearman rho = W1 produces a *different* ordering than Euclidean. This is desirable: it means the structured metric captures something Euclidean misses.
- **M4_2d** (rho = 0.588) produces the most divergent ranking from Euclidean, followed closely by M3_weighted (0.589) and M2_graph (0.599).
- **M1_trivial** (rho = 0.678) is closest to Euclidean, as expected -- it has no structure.
- Random metrics (rho ~ 0.619) fall between trivial and structured, providing a clear ordering: **structured < random < trivial** in terms of Euclidean similarity.

### 5.4 Analysis A2: Rater Clustering

K-medoids clustering (k=3) applied to the 6 raters using W1 distances. Compared to Euclidean K-means.

| Ground Metric | Silhouette Score | Cluster Labels |
|---|---|---|
| Euclidean | 0.338 | [0, 2, 0, 1, 0, 1] |
| M1_trivial | **0.414** | [1, 2, 1, 0, 0, 0] |
| M2_graph | -0.079 | [1, 2, 2, 2, 2, 0] |
| M3_weighted | 0.264 | [1, 2, 1, 2, 2, 0] |
| M4_2d | 0.306 | [1, 2, 1, 0, 0, 0] |
| M5_linear | 0.100 | [1, 1, 2, 2, 2, 0] |

**Interpretation:**
- With only 6 raters and k=3, clustering is inherently noisy. Silhouette scores are low across all metrics.
- M1_trivial produces the highest silhouette (0.414), suggesting that for this small sample, total variation captures the main rater differences (volume of annotations).
- M2_graph produces *negative* silhouette (-0.079), meaning its induced clusters are worse than random -- the graph structure creates distances that don't align with natural rater groupings.
- This is not a failure of W1 per se, but reflects that 6 raters are insufficient for clustering to be meaningful. Track B with 20 synthetic students provides the more informative test.

### 5.5 Analysis A3: System Quality vs. Rater Agreement

Pearson correlation between per-system MQM score and average inter-rater W1 distance.

| Statistic | Value |
|---|---|
| Pearson r | 0.085 |
| p-value | 0.816 |
| N systems | 10 |

**Interpretation:** No correlation between MT system quality and rater disagreement. This implies that rater variance is *systematic* (reflecting genuine differences in annotation focus) rather than data-driven (caused by ambiguous MT output). This supports the interpretation that rater profiles capture meaningful individual expertise differences.

### 5.6 Analysis A4: Ground Metric Comparison Summary

| Metric | A1 Spearman rho | A2 Silhouette |
|---|---|---|
| M1_trivial | 0.678 | 0.414 |
| M2_graph | 0.599 | -0.079 |
| M3_weighted | 0.589 | 0.264 |
| M4_2d | 0.588 | 0.306 |
| M5_linear | 0.607 | 0.100 |

**Conclusion for Track A:** Structured metrics (M2-M4) produce the most divergent orderings from Euclidean (lowest rho), confirming they capture different information. However, clustering performance is mixed with only 6 raters. The real test of discrimination power comes from Track B.

---

## 6. Track B: Synthetic Student Trajectories

### 6.1 Data Generation

20 synthetic students, 5 archetypes, 10 sessions each.

| Archetype | N | Learning Pattern | Pedagogical Meaning |
|---|---|---|---|
| Coherent | 5 | Sequential mastery along ToM hierarchy (S1->S2->...->S7). Prerequisite acceleration: if S_k >= 0.7, S_{k+1} improves 1.3-1.5x. | Ideal learner following the scaffolded progression |
| Scattered | 5 | Random 3-5 skills per session, Dirichlet-distributed. | Unfocused learner, no systematic strategy |
| Fast Plateau | 4 | 2.0x rate sessions 1-3, then 0.2x sessions 4-10. | Early overconfidence, burnout or ceiling effect |
| Slow Steady | 3 | Uniform +0.017/session across all skills. | Persistent but undifferentiated learner |
| Surface Only | 3 | S1-S2 at 2.0x, S3+ at 0.3x. | Student who masters surface errors but cannot progress to meaning-level |

**Initial profile (all archetypes):** [0.65, 0.50, 0.35, 0.25, 0.20, 0.15, 0.10]
**Noise:** Gaussian, sigma = 0.03 per session per skill.

### 6.2 Final Profiles (Session 10, Archetype Means)

| Skill | Coherent | Scattered | Fast Plateau | Slow Steady | Surface Only |
|---|---|---|---|---|---|
| S1 | 0.909 | 0.800 | 0.934 | 0.796 | 0.994 |
| S2 | 0.822 | 0.667 | 0.730 | 0.632 | 0.949 |
| S3 | 0.548 | 0.473 | 0.551 | 0.491 | 0.420 |
| S4 | 0.380 | 0.375 | 0.395 | 0.408 | 0.282 |
| S5 | 0.323 | 0.330 | 0.335 | 0.334 | 0.270 |
| S6 | 0.255 | 0.356 | 0.263 | 0.316 | 0.178 |
| S7 | 0.186 | 0.264 | 0.180 | 0.218 | 0.110 |

**Key patterns visible:**
- **Surface Only** has highest S1/S2 (near ceiling) but lowest S4-S7
- **Scattered** has relatively flat profiles (S6 and S7 sometimes higher than coherent due to random boosts)
- **Coherent** shows the steepest S1>>S7 gradient (hierarchical mastery)
- **Slow Steady** is the most uniform across skills

### 6.3 Analysis B1: Archetype Discrimination (Fisher Ratio)

Fisher discriminant ratio at session 10: var(between-archetype distances) / var(within-archetype distances). Higher = better separation.

| Ground Metric | Fisher Ratio |
|---|---|
| M5_linear | **7.069** |
| M2_graph | 3.510 |
| M4_2d | 3.317 |
| M3_weighted | 2.534 |
| M1_trivial | 1.442 |
| Cosine | 1.513 |
| Euclidean | 1.252 |
| M_rand (mean) | 1.475 |

**Interpretation:**
- All structured W1 metrics (M2-M5) substantially outperform Euclidean (1.252) and cosine (1.513) on archetype discrimination.
- **M5_linear** achieves the highest Fisher ratio (7.069), which is surprising -- it suggests that simple ordinal distance is highly effective for this particular archetype set.
- M2_graph (3.510) and M4_2d (3.317) are close, both roughly 2.5x better than Euclidean.
- Random metrics (~1.475) perform at the level of cosine distance, confirming that arbitrary structure does not help.
- **RQ1 confirmed:** W1 with structured ground metrics distinguishes archetypes significantly better than pointwise metrics.

### 6.4 Analysis B2: MasteryGap Trajectories

MasteryGap = W1(student_profile, target_profile) computed at each session. AUC-MG = integral over 10 sessions (lower = faster progress toward target).

| Archetype | Mean AUC-MG | Interpretation |
|---|---|---|
| Slow Steady | 1.070 | Closest to target (uniform improvement reduces gap fastest) |
| Scattered | 1.105 | Surprisingly close to target (random hits on weak skills) |
| Fast Plateau | 1.270 | Good early, stalls |
| Coherent | 1.306 | Focused but hierarchical (S7 stays far from target) |
| Surface Only | **1.685** | Furthest from target (S3-S7 barely improve) |

**Kruskal-Wallis test:** H = 16.886, **p = 0.002** (significant).

**Interpretation:**
- Archetypes are significantly distinguished by their mastery gap trajectories.
- **Surface Only** is clearly the worst performer (AUC-MG 1.685 vs. next-worst 1.306), confirming that high S1/S2 mastery alone does not bring students close to the expert target.
- Coherent learners (1.306) are *not* the closest to target -- they rank 4th. This is because the target profile expects substantial S5-S7 mastery (0.75-0.70), which coherent learners haven't reached after only 10 sessions despite being on the right trajectory.
- **Slow Steady** (1.070) closes the gap fastest because uniform improvement reduces the average distance across all skills, even though it doesn't follow the pedagogical hierarchy.
- **RQ4 partially confirmed:** W1-based mastery gap meaningfully separates archetypes (p=0.002), but the ordering reveals a tension between *pedagogically correct progression* (coherent) and *numerically optimal gap reduction* (slow steady).

### 6.5 Analysis B3: Trajectory Efficiency

Efficiency = direct_distance(start, end) / cumulative_path_length. Values near 1.0 = straight path; low values = detours.

| Archetype | Mean Efficiency | Std |
|---|---|---|
| Scattered | **0.360** | 0.055 |
| Slow Steady | 0.288 | 0.120 |
| Surface Only | 0.254 | 0.069 |
| Coherent | 0.185 | 0.068 |
| Fast Plateau | **0.125** | 0.044 |

**ANOVA:** F = 5.354, **p = 0.007** (significant).

**Interpretation:**
- Archetypes differ significantly in trajectory efficiency.
- **Scattered** has the highest efficiency (0.360) -- counterintuitively, random exploration produces a more "direct" path in W1 space because it doesn't over-concentrate on specific skills before moving to others.
- **Fast Plateau** has the lowest efficiency (0.125) -- the learning cliff at session 4 creates a trajectory that goes forward fast, then stalls, making the cumulative path much longer than the net displacement.
- **Coherent** has low efficiency (0.185) because hierarchical mastery creates deliberate "detours" -- spending time perfecting S1 before moving to S2 is pedagogically sound but geometrically inefficient.
- **RQ2 partially addressed:** W1 reliably distinguishes progression types, but efficiency alone doesn't separate "good" from "bad" learners -- it separates *focused* from *diffuse* strategies.

### 6.6 Analysis B4: Barycenter Comparison

Compares the Wasserstein barycenter (Frechet mean under W1) to the arithmetic mean of all session-10 profiles.

| Measure | Arithmetic Mean | Wasserstein Barycenter |
|---|---|---|
| S1 | 0.883 | 0.262 |
| S2 | 0.755 | 0.226 |
| S3 | 0.502 | 0.162 |
| S4 | 0.371 | 0.112 |
| S5 | 0.321 | 0.096 |
| S6 | 0.280 | 0.084 |
| S7 | 0.198 | 0.058 |

**Readiness correlation (distance to center vs. "ready" binary):**
- Barycenter: r = 0.005, p = 0.982
- Arithmetic mean: r = 0.065, p = 0.785

**Interpretation:** Neither center predicts readiness in this setup. The Wasserstein barycenter is normalised (much smaller absolute values) and represents a "shape" centre, while the arithmetic mean represents a "level" centre. The readiness correlation is null for both, likely because "readiness" (mastery gap < median) is too coarse a binary for 20 students. This analysis would benefit from a larger student population.

### 6.7 Analysis B5: Ground Metric Sensitivity

Effect matrix: each ground metric's performance across three analyses.

| Metric | B1 Fisher | B2 Kruskal-H | B3 ANOVA-F | Row Sum |
|---|---|---|---|---|
| M5_linear | 7.069 | 17.104 | 6.954 | 31.13 |
| M4_2d | 3.317 | 17.104 | 5.755 | 26.18 |
| M2_graph | 3.510 | 16.886 | 5.354 | 25.75 |
| M3_weighted | 2.534 | 17.104 | 5.155 | 24.79 |
| M1_trivial | 1.442 | 16.502 | 5.131 | 23.08 |

**Planned comparisons:**

| Comparison | Metric A (mean) | Metric B (mean) | Winner |
|---|---|---|---|
| Structure vs. none | M2 (8.58) | M1 (7.69) | M2 (3/3 wins) |
| Specific vs. random | M2 (8.58) | M_rand (7.40) | M2 |
| Calibrated vs. uniform | M3 (8.26) | M2 (8.58) | M2 (M3 wins 1/3) |
| 2D vs. 1D | M4 (8.73) | M2 (8.58) | M4 (2/3 wins) |
| Structure vs. ordering | M2 (8.58) | M5 (10.38) | **M5** |
| Best ToM vs. baseline | M4 (8.73) | M5 (10.38) | **M5** |

**Interpretation:**
- **RQ3 (sensitivity):** Ground metric choice matters significantly. M2 consistently outperforms M1 and random metrics.
- **RQ7 (calibration):** Surprisingly, M3_weighted does *not* outperform M2_graph (M2 wins 2/3 comparisons). Empirical calibration via detection rate gradients does not clearly improve discrimination for this dataset.
- **RQ5 (2D vs. 1D):** M4_2d slightly outperforms M2_graph (8.73 vs. 8.58), suggesting the 2D embedding captures similar structure with less information loss.
- **Unexpected finding:** M5_linear outperforms all structured metrics (10.38 vs. best structured 8.73). This suggests that for the current archetype set, the simple ordinal structure of the skill hierarchy is the dominant factor, and the graph topology adds complexity without proportional benefit. This deserves further investigation with more diverse student archetypes.

### 6.8 Analysis B6: BKT Robustness

Bayesian Knowledge Tracing smoothing applied to raw detection rate trajectories.

| Measure | Raw | BKT-Smoothed |
|---|---|---|
| Fisher ratio (M2) | 3.510 | 1.248 |
| Fisher preserved? | -- | **No** |

**Efficiency means (BKT):**

| Archetype | Raw | BKT |
|---|---|---|
| Coherent | 0.185 | 0.527 |
| Scattered | 0.360 | 0.531 |
| Fast Plateau | 0.125 | 0.580 |
| Slow Steady | 0.288 | 0.462 |
| Surface Only | 0.254 | 1.000 |

**Interpretation:**
- BKT smoothing *reduces* the Fisher ratio from 3.51 to 1.25 -- archetype discrimination is substantially degraded.
- BKT compresses inter-archetype differences by smoothing toward a common learning curve.
- Surface Only achieves efficiency = 1.0 under BKT because BKT models mastery as a monotone latent variable, which collapses the surface-only pattern into a "fully mastered" state for S1/S2.
- **Conclusion:** BKT smoothing is too aggressive for this application. Raw detection rates or lighter smoothing methods should be preferred when computing W1 distances.

### 6.9 Analysis B7: Balanced vs. Unbalanced OT

Compares balanced W1 (normalised profiles) with unbalanced W1 (Sinkhorn, raw profiles) across 4 marginal relaxation values.

| reg_m | Correlation (r) | p-value | Balanced Fisher | Unbalanced Fisher |
|---|---|---|---|---|
| 0.1 | 0.382 | 0.096 | 16.29 | ~0.0 |
| 0.5 | -- | -- | -- | -- |
| 1.0 | -- | -- | -- | -- |
| 5.0 | -- | -- | -- | -- |

**Slow Steady divergence (reg_m = 0.1):**
- Balanced delta (session 1 vs 10): 0.026
- Unbalanced delta: ~0.0 (effectively zero)

**Interpretation:**
- At reg_m = 0.1 (tight marginal constraint), unbalanced OT produces near-zero mastery gaps for all students -- the regularisation is too strong, collapsing all distances.
- The balanced formulation (Fisher = 16.29) dramatically outperforms unbalanced (Fisher ~ 0.0) at this setting.
- **RQ6 partially answered:** Unbalanced OT with reg_m = 0.1 is too constrained to be useful. Higher reg_m values (looser marginals) would allow more informative mass transport but were not fully evaluated in this run.
- **Practical recommendation:** Balanced W1 with normalised profiles is the more robust choice for the current application. Unbalanced OT requires careful tuning of reg_m and may be more appropriate when absolute mastery level (not just shape) matters pedagogically.

---

## 7. Summary of Findings by Research Question

| RQ | Finding | Verdict |
|---|---|---|
| RQ1 | W1 with structured metrics (M2-M5) achieves Fisher ratios 2-5x higher than Euclidean for archetype discrimination | **Confirmed** |
| RQ2 | W1 reliably distinguishes progression styles (ANOVA p=0.007), but efficiency metric captures strategy type rather than quality | **Partially confirmed** |
| RQ3 | Ground metric choice matters: structured > random > trivial for divergence from Euclidean (A1) and Fisher ratio (B1) | **Confirmed** |
| RQ4 | W1 mastery gap significantly separates archetypes (Kruskal-Wallis p=0.002), but pedagogically "correct" progression != numerically optimal | **Partially confirmed** |
| RQ5 | M4 (2D embedding) slightly outperforms M2 (graph) on average, suggesting minimal information loss | **Confirmed** |
| RQ6 | Unbalanced OT at reg_m=0.1 collapses distances; balanced OT is more robust | **Not confirmed** (needs tuning) |
| RQ7 | M3 (calibrated) does *not* outperform M2 (unweighted); M5 (linear) unexpectedly outperforms all | **Not confirmed** |

---

## 8. Key Figures

All figures are saved to `outputs/wasserstein/`.

| Figure | Description | Key Finding |
|---|---|---|
| F1 | Radar charts: archetype profiles at sessions 1 and 10 | Surface Only ceiling on S1-S2 clearly visible |
| F2 | MasteryGap trajectories over 10 sessions | Surface Only diverges upward; others converge |
| F3 | Fisher ratios by ground metric | M5 > M2 > M4 > M3 > M1 > Cosine > Euclidean |
| F4 | Pairwise W1 heatmap at session 10 | Block-diagonal structure visible for within-archetype pairs |
| F5 | Ground metric sensitivity heatmap | M5 dominates across B1-B3 |
| F8 | Transport plan: coherent vs. target | Most mass moved from S1 excess to S5-S7 deficit |
| F9 | All 5 ground metric matrices side-by-side | Visual comparison of structure differences |
| F10 | Balanced vs. unbalanced for Slow Steady | Balanced captures shape change; unbalanced collapses |
| F11 | 2D embedding space with skill nodes | Pedagogical topology visualised |
| F12 | Permutation null distribution | Structured metrics clearly exceed random |

---

## 9. Limitations

1. **Track A sample size:** Only 6 WMT raters limits the power of clustering analyses. Rater clustering (A2) results should be interpreted cautiously.

2. **S7 = 0 in WMT data:** No discourse-level errors were annotated in WMT MQM 2020, making S7 uninformative in Track A. This is a limitation of the data source, not the framework.

3. **M5 outperformance:** The unexpected dominance of M5_linear over structured metrics (M2-M4) may be an artefact of the archetype design -- all archetypes operate primarily along the S1-to-S7 ordinal axis. With archetypes that exploit lateral skill relationships (e.g., a "terminology specialist" who excels at S5 but not S4), graph metrics may show larger advantages.

4. **Unbalanced OT tuning:** Only reg_m = 0.1 was fully evaluated. The unbalanced formulation needs a broader parameter sweep to be fairly compared.

5. **BKT compression:** BKT smoothing degrades archetype discrimination. Alternative smoothing methods (exponential moving average, Kalman filter) should be evaluated.

---

## 10. Reproducibility

### Running the experiments

```bash
python -m experiments.wasserstein.run_all
```

### Output structure

```
outputs/wasserstein/
  all_results.json           # Combined Track A + Track B
  track_a_results.json       # Track A standalone
  track_b_results.json       # Track B standalone
  F1_radar_charts.png        # Archetype profiles
  F2_mastery_gap_trajectories.png
  F3_fisher_ratios.png
  F4_pairwise_heatmap.png
  F5_sensitivity_heatmap.png
  F8_transport_plan_*.png
  F9_ground_metrics.png
  F10_balanced_vs_unbalanced.png
  F11_embedding_space.png
  F12_permutation_null.png
  T1_ground_metrics.tex      # LaTeX metric matrices
  T2_archetypes.tex          # Archetype parameters
```

### Dependencies

- Python 3.10+
- POT >= 0.9 (optimal transport)
- scipy >= 1.12
- scikit-learn >= 1.4
- numpy >= 1.24
- matplotlib >= 3.8
- seaborn >= 0.13
- datasets >= 2.18 (WMT data loading)

### Source code

```
experiments/wasserstein/
  config.py                  # Central parameters (skills, archetypes, BKT, adjacency)
  run_all.py                 # Orchestrator
  ground_metrics.py          # M1-M5 + M_rand construction
  metrics.py                 # W1 balanced/unbalanced, Euclidean, cosine, mastery gap
  synthetic_trajectories.py  # 5 archetype generators, BKT integration
  analysis.py                # B1-B7 analyses
  wmt_analysis.py            # Track A: WMT data loading, A1-A4 analyses
  visualizations.py          # F1-F12 figure generation
```
