"""Ground metric matrices M1–M5 + random generator.

Implements all 5 structured ground metrics from spec §2 plus a random
metric generator for the permutation null baseline.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse.csgraph import shortest_path
from scipy.spatial.distance import cdist

from .config import ADJACENCY, EDGE_WEIGHTS, EMBEDDING_2D, N_RANDOM_METRICS, N_SKILLS


# =============================================================================
# M1: Trivial (baseline) — spec §2.2
# =============================================================================

def build_trivial() -> np.ndarray:
    """W₁ with trivial metric = Total Variation distance."""
    return 1.0 - np.eye(N_SKILLS)


# =============================================================================
# M2: Unweighted graph distance — spec §2.3
# =============================================================================

def build_unweighted_graph() -> np.ndarray:
    """Shortest-path distance on the ToM skill dependency graph, normalized."""
    D = shortest_path(ADJACENCY, unweighted=True)
    return D / D.max()


# =============================================================================
# M3: Weighted graph distance (empirically calibrated) — spec §2.4
# =============================================================================

def build_weighted_graph() -> np.ndarray:
    """Shortest-path distance with empirically calibrated edge weights."""
    adj = np.full((N_SKILLS, N_SKILLS), np.inf)
    np.fill_diagonal(adj, 0)
    for (i, j), w in EDGE_WEIGHTS.items():
        adj[i, j] = w
        adj[j, i] = w
    D = shortest_path(adj, method="D")
    return D / D.max()


# =============================================================================
# M4: 2D embedding (ToM Level × Linguistic Grain) — spec §2.5
# =============================================================================

def build_2d_embedding() -> np.ndarray:
    """Euclidean distance in the 2D ToM × linguistic grain space, normalized."""
    D = cdist(EMBEDDING_2D, EMBEDDING_2D, metric="euclidean")
    return D / D.max()


# =============================================================================
# M5: Uniform linear (control) — spec §2.6
# =============================================================================

def build_uniform_linear() -> np.ndarray:
    """Skills ordered 0-6 uniformly, |i - j| / 6."""
    idx = np.arange(N_SKILLS)
    return np.abs(idx[:, None] - idx[None, :]) / (N_SKILLS - 1)


# =============================================================================
# M_rand: Random symmetric metric matrices — spec §2.7
# =============================================================================

def build_random_metrics(
    n: int = N_RANDOM_METRICS, seed: int = 42
) -> list[np.ndarray]:
    """Generate n random valid metric matrices (symmetric, zero diagonal, normalized)."""
    rng = np.random.default_rng(seed)
    metrics = []
    for _ in range(n):
        raw = rng.uniform(0.1, 1.0, size=(N_SKILLS, N_SKILLS))
        sym = (raw + raw.T) / 2
        np.fill_diagonal(sym, 0)
        # Ensure triangle inequality via shortest-path closure
        D = shortest_path(sym, method="D")
        metrics.append(D / D.max())
    return metrics


# =============================================================================
# Convenience: build all named metrics
# =============================================================================

METRIC_BUILDERS = {
    "M1_trivial": build_trivial,
    "M2_graph": build_unweighted_graph,
    "M3_weighted": build_weighted_graph,
    "M4_2d": build_2d_embedding,
    "M5_linear": build_uniform_linear,
}


def build_all_metrics(
    include_random: bool = True, n_random: int = N_RANDOM_METRICS, seed: int = 42
) -> dict[str, np.ndarray]:
    """Build all ground metric matrices.

    Returns a dict mapping metric name to 7×7 cost matrix.
    Random metrics are keyed as 'M_rand_0', 'M_rand_1', etc.
    """
    metrics = {name: builder() for name, builder in METRIC_BUILDERS.items()}
    if include_random:
        for i, M in enumerate(build_random_metrics(n_random, seed)):
            metrics[f"M_rand_{i}"] = M
    return metrics
