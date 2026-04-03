"""Track A: WMT MQM annotator analysis.

Implements data loading, profile extraction, and analyses A1–A4 from spec §3.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations

import numpy as np
from scipy import stats

from .config import MQM_EXCLUDE, MQM_TO_SKILL, N_SKILLS, SKILL_LABELS
from .ground_metrics import build_all_metrics
from .metrics import (
    euclidean_distance,
    jsd_distance,
    manhattan_distance,
    pairwise_distances,
    profile_to_array,
    w1_balanced,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data loading — spec §3.1, §3.2
# =============================================================================

def load_wmt_data(
    year: int = 2020,
    lp: str = "en-de",
    cache_dir: str = "data/wmt-mqm",
) -> list[dict]:
    """Load WMT MQM raw annotation data with per-error categories.

    Uses the raw TSV from google/wmt-mqm-human-evaluation GitHub repo,
    which contains individual error annotations with rater, category, severity.
    Downloads and caches locally on first use.

    Args:
        year: WMT edition year.
        lp: Language pair (e.g., "en-de", "zh-en").
        cache_dir: Local directory for cached TSV files.

    Returns:
        List of annotation dicts with keys: system, doc, doc_id, seg_id,
        rater, source, target, category, severity.
    """
    import csv
    from pathlib import Path

    lp_code = lp.replace("-", "")
    tsv_name = f"mqm_newstest{year}_{lp_code}.tsv"
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    local_path = cache_path / tsv_name

    # Download if not cached
    if not local_path.exists():
        base_url = (
            "https://raw.githubusercontent.com/google/"
            "wmt-mqm-human-evaluation/main"
        )
        url = f"{base_url}/newstest{year}/{lp_code}/{tsv_name}"
        logger.info("Downloading WMT MQM data from %s ...", url)

        import urllib.request
        import urllib.error

        try:
            urllib.request.urlretrieve(url, local_path)
        except urllib.error.HTTPError:
            # Try alternate URL without subdirectory
            url_alt = f"{base_url}/newstest{year}/{tsv_name}"
            logger.info("Trying alternate URL: %s", url_alt)
            urllib.request.urlretrieve(url_alt, local_path)

        logger.info("Saved to %s", local_path)

    # Parse TSV
    records = []
    with open(local_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            records.append(dict(row))

    logger.info(
        "Loaded %d raw annotations from %s (columns: %s)",
        len(records),
        tsv_name,
        list(records[0].keys()) if records else "empty",
    )
    return records


# =============================================================================
# Profile extraction — spec §3.2 Step 2
# =============================================================================

def extract_rater_profile(
    annotations: list[dict], rater_id: str
) -> dict[str, int]:
    """Compute error category distribution for a single rater.

    Returns count dict mapping S1–S7 to number of annotations.
    """
    profile = {sk: 0 for sk in SKILL_LABELS}
    for annot in annotations:
        if annot.get("rater") != rater_id and annot.get("raterID") != rater_id:
            continue
        category = annot.get("category", "")
        # Skip non-error annotations
        if category in MQM_EXCLUDE or annot.get("severity") in ("no-error", "Neutral"):
            continue
        skill = MQM_TO_SKILL.get(category, "S3")  # Default to S3
        profile[skill] += 1
    return profile


def extract_all_rater_profiles(
    annotations: list[dict],
) -> dict[str, dict[str, int]]:
    """Extract profiles for all raters in the dataset."""
    # Find all unique rater IDs
    rater_ids = set()
    for annot in annotations:
        rid = annot.get("rater") or annot.get("raterID")
        if rid:
            rater_ids.add(rid)

    profiles = {}
    for rid in sorted(rater_ids):
        profiles[rid] = extract_rater_profile(annotations, rid)
    logger.info("Extracted profiles for %d raters", len(profiles))
    return profiles


def extract_segment_rater_profiles(
    annotations: list[dict],
) -> dict[tuple[str, str], dict[str, dict[str, int]]]:
    """Extract per-segment, per-rater profiles.

    Returns: {(system, seg_id): {rater_id: {S1: count, ...}}}
    """
    # Group annotations by (system, segment)
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for annot in annotations:
        system = annot.get("system", "")
        seg_id = str(annot.get("seg_id") or annot.get("docSegId", ""))
        grouped[(system, seg_id)].append(annot)

    segment_profiles: dict[tuple[str, str], dict[str, dict[str, int]]] = {}
    for key, annots in grouped.items():
        rater_ids = set()
        for a in annots:
            rid = a.get("rater") or a.get("raterID")
            if rid:
                rater_ids.add(rid)
        profiles = {}
        for rid in rater_ids:
            profiles[rid] = extract_rater_profile(annots, rid)
        if len(profiles) >= 2:
            segment_profiles[key] = profiles

    logger.info(
        "Extracted segment profiles for %d segments with 2+ raters",
        len(segment_profiles),
    )
    return segment_profiles


# =============================================================================
# Analysis A1: Inter-rater profile distances — spec §3.3
# =============================================================================

def analysis_a1_interrater_distances(
    segment_profiles: dict[tuple[str, str], dict[str, dict[str, int]]],
    ground_metrics: dict[str, np.ndarray],
) -> dict[str, object]:
    """Compare W₁ vs Euclidean rankings of rater pairs.

    For each segment with 2+ raters, compute pairwise distances under
    all ground metrics and Euclidean.

    Returns dict with Spearman correlations between W₁ and Euclidean rankings.
    """
    results = {}

    # Pre-compute all pairwise baseline distances (metric-independent)
    euc_distances = []
    man_distances = []
    jsd_dists = []
    pair_keys = []  # track segment pairs for alignment

    for _seg_key, rater_profiles in segment_profiles.items():
        rater_ids = list(rater_profiles.keys())
        for ri, rj in combinations(rater_ids, 2):
            pi = rater_profiles[ri]
            pj = rater_profiles[rj]
            euc_distances.append(euclidean_distance(pi, pj))
            man_distances.append(manhattan_distance(pi, pj))
            jsd_dists.append(jsd_distance(pi, pj))
            pair_keys.append((_seg_key, ri, rj))

    n_pairs = len(euc_distances)

    for metric_name, cost_matrix in ground_metrics.items():
        w1_distances = []
        for _seg_key, rater_profiles in segment_profiles.items():
            rater_ids = list(rater_profiles.keys())
            for ri, rj in combinations(rater_ids, 2):
                pi = rater_profiles[ri]
                pj = rater_profiles[rj]
                w1_distances.append(w1_balanced(pi, pj, cost_matrix))

        if len(w1_distances) > 2:
            rho, p_val = stats.spearmanr(w1_distances, euc_distances)
            results[metric_name] = {
                "spearman_rho": rho,
                "p_value": p_val,
                "n_pairs": len(w1_distances),
                "w1_mean": np.mean(w1_distances),
                "w1_std": np.std(w1_distances),
                "euc_mean": np.mean(euc_distances),
                "euc_std": np.std(euc_distances),
            }

    # Manhattan baseline: Spearman correlation with Euclidean ranking
    if n_pairs > 2:
        rho_man, p_man = stats.spearmanr(man_distances, euc_distances)
        results["manhattan"] = {
            "spearman_rho": float(rho_man),
            "p_value": float(p_man),
            "n_pairs": n_pairs,
            "dist_mean": float(np.mean(man_distances)),
            "dist_std": float(np.std(man_distances)),
        }

    # JSD baseline: Spearman correlation with Euclidean ranking
    if n_pairs > 2:
        rho_jsd, p_jsd = stats.spearmanr(jsd_dists, euc_distances)
        results["jsd"] = {
            "spearman_rho": float(rho_jsd),
            "p_value": float(p_jsd),
            "n_pairs": n_pairs,
            "dist_mean": float(np.mean(jsd_dists)),
            "dist_std": float(np.std(jsd_dists)),
        }

    return results


# =============================================================================
# Analysis A2: Rater-as-student competency profiles — spec §3.3
# =============================================================================

def analysis_a2_rater_clustering(
    rater_profiles: dict[str, dict[str, int]],
    ground_metrics: dict[str, np.ndarray],
    n_clusters: int = 3,
) -> dict[str, dict]:
    """Cluster raters using W₁ vs Euclidean, compare silhouette scores.

    Uses k-medoids with W₁ as distance metric.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    rater_ids = sorted(rater_profiles.keys())
    profiles = [rater_profiles[rid] for rid in rater_ids]
    profile_arrays = np.array([profile_to_array(p) for p in profiles])

    results = {}

    # Euclidean baseline (KMeans)
    if len(rater_ids) > n_clusters:
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        euc_labels = km.fit_predict(profile_arrays)
        euc_silhouette = silhouette_score(profile_arrays, euc_labels)
        results["euclidean"] = {
            "silhouette": euc_silhouette,
            "labels": euc_labels.tolist(),
        }

    # W₁-based clustering for each ground metric (using precomputed distances)
    for metric_name, cost_matrix in ground_metrics.items():
        D = pairwise_distances(profiles, cost_matrix)
        # K-medoids via precomputed distances
        labels = _kmedoids(D, n_clusters, random_state=42)
        if len(set(labels)) > 1:
            sil = silhouette_score(D, labels, metric="precomputed")
        else:
            sil = 0.0
        results[metric_name] = {
            "silhouette": sil,
            "labels": labels,
        }

    return results


def _kmedoids(
    D: np.ndarray, k: int, max_iter: int = 100, random_state: int = 42
) -> list[int]:
    """Simple k-medoids (PAM) on a precomputed distance matrix."""
    rng = np.random.default_rng(random_state)
    n = D.shape[0]
    if n <= k:
        return list(range(n))

    # Initialize medoids randomly
    medoids = list(rng.choice(n, size=k, replace=False))
    labels = _assign_clusters(D, medoids)

    for _ in range(max_iter):
        new_medoids = []
        for c in range(k):
            members = [i for i, lbl in enumerate(labels) if lbl == c]
            if not members:
                new_medoids.append(medoids[c])
                continue
            # Pick member with minimum total distance to other members
            costs = [sum(D[m, j] for j in members) for m in members]
            new_medoids.append(members[np.argmin(costs)])

        new_labels = _assign_clusters(D, new_medoids)
        if new_labels == labels:
            break
        medoids = new_medoids
        labels = new_labels

    return labels


def _assign_clusters(D: np.ndarray, medoids: list[int]) -> list[int]:
    """Assign each point to its closest medoid."""
    n = D.shape[0]
    labels = []
    for i in range(n):
        dists = [D[i, m] for m in medoids]
        labels.append(int(np.argmin(dists)))
    return labels


# =============================================================================
# Analysis A3: System quality × rater agreement — spec §3.3
# =============================================================================

def analysis_a3_system_quality(
    annotations: list[dict],
    segment_profiles: dict[tuple[str, str], dict[str, dict[str, int]]],
    cost_matrix: np.ndarray,
) -> dict[str, dict]:
    """Correlation between MT system quality and inter-rater W₁.

    Higher quality systems → more rater disagreement (hypothesis).
    """
    # Compute MQM score per system from severity weights
    # MQM scoring: Minor=-1, Major=-5, Critical=-10 (standard MQM weighting)
    severity_weights = {"Minor": -1, "Major": -5, "Critical": -10}
    system_scores: dict[str, list[float]] = defaultdict(list)
    for annot in annotations:
        system = annot.get("system", "")
        severity = annot.get("severity", "")
        if severity in severity_weights:
            system_scores[system].append(severity_weights[severity])
        elif severity not in ("no-error", "Neutral", ""):
            system_scores[system].append(-1)  # Default to minor

    system_avg_mqm = {
        sys: np.mean(scores) for sys, scores in system_scores.items() if scores
    }

    # Compute average inter-rater W₁ per system
    system_w1: dict[str, list[float]] = defaultdict(list)
    for (system, _seg_id), rater_profiles in segment_profiles.items():
        rater_ids = list(rater_profiles.keys())
        for ri, rj in combinations(rater_ids, 2):
            d = w1_balanced(rater_profiles[ri], rater_profiles[rj], cost_matrix)
            system_w1[system].append(d)

    system_avg_w1 = {
        sys: np.mean(dists) for sys, dists in system_w1.items() if dists
    }

    # Correlate
    common_systems = sorted(set(system_avg_mqm) & set(system_avg_w1))
    if len(common_systems) < 3:
        return {"error": "Not enough systems with both MQM scores and W₁ data"}

    mqm_vals = [system_avg_mqm[s] for s in common_systems]
    w1_vals = [system_avg_w1[s] for s in common_systems]

    r, p_val = stats.pearsonr(mqm_vals, w1_vals)
    return {
        "pearson_r": r,
        "p_value": p_val,
        "n_systems": len(common_systems),
        "systems": common_systems,
        "mqm_scores": mqm_vals,
        "w1_distances": w1_vals,
    }


# =============================================================================
# Analysis A4: Ground metric comparison on real data — spec §3.3
# =============================================================================

def analysis_a4_ground_metric_comparison(
    a1_results: dict,
    a2_results: dict,
) -> dict[str, dict]:
    """Compare discriminative power of M1–M5 on analyses A1–A3.

    Aggregates effect sizes across analyses for each ground metric.
    """
    metric_names = [k for k in a1_results if k.startswith("M")]
    comparison_results = {}

    for metric_name in metric_names:
        a1 = a1_results.get(metric_name, {})
        a2 = a2_results.get(metric_name, {})

        comparison_results[metric_name] = {
            "a1_spearman_rho": a1.get("spearman_rho"),
            "a2_silhouette": a2.get("silhouette"),
            # Lower rho = more different from Euclidean (desired)
            # Higher silhouette = better clustering
        }

    return comparison_results


# =============================================================================
# Full Track A pipeline
# =============================================================================

def run_track_a(
    year: int = 2020,
    lp: str = "en-de",
    n_clusters: int = 3,
) -> dict:
    """Execute all Track A analyses.

    Returns a dict with all results for reporting.
    """
    logger.info("=== Track A: WMT MQM Analysis (year=%d, lp=%s) ===", year, lp)

    # Load data
    logger.info("Loading WMT data...")
    annotations = load_wmt_data(year=year, lp=lp)
    logger.info("Loaded %d annotations", len(annotations))

    # Extract profiles
    logger.info("Extracting rater profiles...")
    rater_profiles = extract_all_rater_profiles(annotations)
    segment_profiles = extract_segment_rater_profiles(annotations)

    # Build ground metrics
    ground_metrics = build_all_metrics(include_random=True)

    # A1: Inter-rater distances
    logger.info("Running A1: Inter-rater profile distances...")
    a1_results = analysis_a1_interrater_distances(segment_profiles, ground_metrics)

    # A2: Rater clustering
    logger.info("Running A2: Rater clustering...")
    a2_results = analysis_a2_rater_clustering(
        rater_profiles, ground_metrics, n_clusters=n_clusters
    )

    # A3: System quality × agreement (use M2 as primary)
    logger.info("Running A3: System quality × rater agreement...")
    a3_results = analysis_a3_system_quality(
        annotations, segment_profiles, ground_metrics["M2_graph"]
    )

    # A4: Ground metric comparison
    logger.info("Running A4: Ground metric comparison...")
    a4_results = analysis_a4_ground_metric_comparison(a1_results, a2_results)

    return {
        "metadata": {
            "year": year,
            "lp": lp,
            "n_annotations": len(annotations),
            "n_raters": len(rater_profiles),
            "n_segments_with_multi_rater": len(segment_profiles),
        },
        "rater_profiles": rater_profiles,
        "A1_interrater_distances": a1_results,
        "A2_rater_clustering": a2_results,
        "A3_system_quality": a3_results,
        "A4_ground_metric_comparison": a4_results,
    }
