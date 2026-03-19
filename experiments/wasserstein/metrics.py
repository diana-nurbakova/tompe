"""Balanced W₁, unbalanced UW₁, efficiency, barycenter — all configurable.

Core transport computations from spec §1.3, §3.3, §5.3, §5.4, §5.7.
"""

from __future__ import annotations

import numpy as np
import ot

from .config import N_SKILLS, REG_ENTROPIC, SKILL_LABELS, TARGET_PROFILE

_EPS = 1e-8


# =============================================================================
# Profile conversions
# =============================================================================

def profile_to_array(profile: dict[str, float]) -> np.ndarray:
    """Convert {S1: v1, ...} dict to length-7 numpy array."""
    return np.array([profile[k] for k in SKILL_LABELS], dtype=np.float64)


def normalize(a: np.ndarray) -> np.ndarray:
    """Normalize to a probability distribution (sum = 1)."""
    a = np.maximum(a, _EPS)
    return a / a.sum()


def safe_raw(a: np.ndarray) -> np.ndarray:
    """Ensure all values are positive (for unbalanced OT)."""
    return np.maximum(a, _EPS)


# =============================================================================
# Balanced W₁ (Earth Mover's Distance) — spec §1.3
# =============================================================================

def w1_balanced(
    profile_a: dict[str, float] | np.ndarray,
    profile_b: dict[str, float] | np.ndarray,
    cost_matrix: np.ndarray,
) -> float:
    """Compute balanced Wasserstein-1 distance between two skill profiles.

    Both profiles are normalized to probability distributions.
    Uses exact linear program solver (ot.emd2).
    """
    a = profile_a if isinstance(profile_a, np.ndarray) else profile_to_array(profile_a)
    b = profile_b if isinstance(profile_b, np.ndarray) else profile_to_array(profile_b)
    mu = normalize(a)
    nu = normalize(b)
    return float(ot.emd2(mu, nu, cost_matrix))


def w1_balanced_with_plan(
    profile_a: dict[str, float] | np.ndarray,
    profile_b: dict[str, float] | np.ndarray,
    cost_matrix: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Return (distance, transport_plan) for visualization (Figure F8)."""
    a = profile_a if isinstance(profile_a, np.ndarray) else profile_to_array(profile_a)
    b = profile_b if isinstance(profile_b, np.ndarray) else profile_to_array(profile_b)
    mu = normalize(a)
    nu = normalize(b)
    plan = ot.emd(mu, nu, cost_matrix)
    dist = float(np.sum(plan * cost_matrix))
    return dist, plan


# =============================================================================
# Unbalanced W₁ (Sinkhorn with KL marginal penalty) — spec §1.3, §5.7
# =============================================================================

def w1_unbalanced(
    profile_a: dict[str, float] | np.ndarray,
    profile_b: dict[str, float] | np.ndarray,
    cost_matrix: np.ndarray,
    reg: float = REG_ENTROPIC,
    reg_m: float = 1.0,
) -> float:
    """Compute unbalanced W₁ using Sinkhorn with KL marginal penalty.

    Raw mastery vectors used directly (no normalization).
    reg: entropic regularization.
    reg_m: marginal relaxation (KL penalty for mass creation/destruction).
    """
    a = profile_a if isinstance(profile_a, np.ndarray) else profile_to_array(profile_a)
    b = profile_b if isinstance(profile_b, np.ndarray) else profile_to_array(profile_b)
    a = safe_raw(a)
    b = safe_raw(b)
    result = ot.unbalanced.sinkhorn_unbalanced2(a, b, cost_matrix, reg, reg_m)
    return float(np.real(result))


# =============================================================================
# Euclidean & cosine baselines
# =============================================================================

def euclidean_distance(
    profile_a: dict[str, float] | np.ndarray,
    profile_b: dict[str, float] | np.ndarray,
) -> float:
    """Standard Euclidean distance between skill vectors."""
    a = profile_a if isinstance(profile_a, np.ndarray) else profile_to_array(profile_a)
    b = profile_b if isinstance(profile_b, np.ndarray) else profile_to_array(profile_b)
    return float(np.linalg.norm(a - b))


def cosine_distance(
    profile_a: dict[str, float] | np.ndarray,
    profile_b: dict[str, float] | np.ndarray,
) -> float:
    """Cosine distance (1 - cosine similarity) between skill vectors."""
    a = profile_a if isinstance(profile_a, np.ndarray) else profile_to_array(profile_a)
    b = profile_b if isinstance(profile_b, np.ndarray) else profile_to_array(profile_b)
    dot = np.dot(a, b)
    norms = np.linalg.norm(a) * np.linalg.norm(b)
    if norms < _EPS:
        return 1.0
    return float(1.0 - dot / norms)


# =============================================================================
# MasteryGap — spec §5.2
# =============================================================================

def mastery_gap(
    profile: dict[str, float] | np.ndarray,
    cost_matrix: np.ndarray,
    target: dict[str, float] | np.ndarray | None = None,
    balanced: bool = True,
    reg_m: float = 1.0,
) -> float:
    """W₁ distance from a student profile to the target mastery profile."""
    if target is None:
        target = TARGET_PROFILE
    if balanced:
        return w1_balanced(profile, target, cost_matrix)
    return w1_unbalanced(profile, target, cost_matrix, reg_m=reg_m)


# =============================================================================
# Trajectory efficiency — spec §5.3
# =============================================================================

def trajectory_efficiency(
    trajectory: list[dict[str, float] | np.ndarray],
    cost_matrix: np.ndarray,
    balanced: bool = True,
) -> float:
    """Compute trajectory efficiency: direct distance / cumulative path length.

    1.0 = perfectly direct path; < 1.0 = detours.
    """
    if len(trajectory) < 2:
        return 1.0

    dist_fn = w1_balanced if balanced else w1_unbalanced
    direct = dist_fn(trajectory[0], trajectory[-1], cost_matrix)
    cumulative = sum(
        dist_fn(trajectory[t], trajectory[t + 1], cost_matrix)
        for t in range(len(trajectory) - 1)
    )
    if cumulative < _EPS:
        return 1.0
    return float(direct / cumulative)


# =============================================================================
# Wasserstein barycenter — spec §5.4
# =============================================================================

def wasserstein_barycenter(
    profiles: list[dict[str, float] | np.ndarray],
    cost_matrix: np.ndarray,
    reg: float = 0.01,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """Compute the regularized Wasserstein barycenter of multiple profiles.

    Returns a length-7 probability distribution.
    """
    arrays = []
    for p in profiles:
        a = p if isinstance(p, np.ndarray) else profile_to_array(p)
        arrays.append(normalize(a))
    A = np.column_stack(arrays)  # (7, n_profiles)

    if weights is None:
        weights = np.ones(len(profiles)) / len(profiles)

    bary = ot.barycenter(A, cost_matrix, reg, weights=weights)
    return bary


# =============================================================================
# Pairwise distance matrix (for clustering, heatmaps)
# =============================================================================

def pairwise_distances(
    profiles: list[dict[str, float] | np.ndarray],
    cost_matrix: np.ndarray,
    balanced: bool = True,
    reg_m: float = 1.0,
) -> np.ndarray:
    """Compute full pairwise W₁ distance matrix for a list of profiles."""
    n = len(profiles)
    D = np.zeros((n, n))
    dist_fn = w1_balanced if balanced else w1_unbalanced
    for i in range(n):
        for j in range(i + 1, n):
            d = dist_fn(profiles[i], profiles[j], cost_matrix)
            D[i, j] = d
            D[j, i] = d
    return D
