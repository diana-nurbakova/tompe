"""Track B: Synthetic student trajectory generation with BKT integration.

Implements 5 archetypes from spec §4.2 with empirically calibrated parameters
from §4.1. Each archetype has a specific learning dynamic (update function).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import (
    ARCHETYPE_INITIAL,
    ARCHETYPES,
    BKT_PARAMS,
    LEARNING_RATES,
    N_SESSIONS,
    N_SKILLS,
    NOISE_STD,
    OVER_EDITING_DECAY_PER_SESSION,
    OVER_EDITING_INITIAL,
    SKILL_LABELS,
)


@dataclass
class StudentTrajectory:
    """A single synthetic student's trajectory across sessions."""

    student_id: str
    archetype: str
    profiles: list[dict[str, float]] = field(default_factory=list)
    bkt_profiles: list[dict[str, float]] = field(default_factory=list)
    over_editing_rates: list[float] = field(default_factory=list)


# =============================================================================
# Archetype update functions — spec §4.2
# =============================================================================

def _update_coherent(
    current: np.ndarray,
    learning_rates: np.ndarray,
    session: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Coherent learner: frontline skills improve fastest.

    Skills whose prerequisites are mastered (>0.7) get accelerated learning.
    """
    mastery_threshold = 0.70
    rates = learning_rates.copy()

    # S2 accelerates when S1 mastered
    if current[0] >= mastery_threshold:
        rates[1] *= 1.5
    # S3 accelerates when S2 mastered
    if current[1] >= mastery_threshold:
        rates[2] *= 1.5
    # S4, S5, S6 accelerate when S3 mastered
    if current[2] >= mastery_threshold:
        rates[3] *= 1.3
        rates[4] *= 1.3
        rates[5] *= 1.3
    # S7 accelerates when S6 mastered
    if current[5] >= mastery_threshold:
        rates[6] *= 1.5

    return current + rates


def _update_scattered(
    current: np.ndarray,
    learning_rates: np.ndarray,
    session: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Scattered learner: random subset of skills improves each session.

    Same total improvement as coherent but distributed randomly.
    """
    total_budget = learning_rates.sum()
    # Pick 3-5 random skills to improve this session
    n_skills = rng.integers(3, 6)
    chosen = rng.choice(N_SKILLS, size=n_skills, replace=False)
    gains = np.zeros(N_SKILLS)
    # Distribute budget among chosen skills
    raw = rng.dirichlet(np.ones(n_skills))
    gains[chosen] = raw * total_budget
    return current + gains


def _update_fast_plateau(
    current: np.ndarray,
    learning_rates: np.ndarray,
    session: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Fast starter: rapid early improvement, then stagnation after session 4."""
    rates = learning_rates.copy()
    if session < 4:
        rates *= 2.0  # Double speed early
    else:
        rates *= 0.2  # Severe plateau
    return current + rates


def _update_slow_steady(
    current: np.ndarray,
    learning_rates: np.ndarray,
    session: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Slow steady: uniform improvement of +0.017/session across all skills."""
    return current + np.full(N_SKILLS, 0.017)


def _update_surface_only(
    current: np.ndarray,
    learning_rates: np.ndarray,
    session: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Surface-only: S1-S2 improve at 2x, S3+ at 0.3x normal rate."""
    rates = learning_rates.copy()
    rates[:2] *= 2.0
    rates[2:] *= 0.3
    return current + rates


UPDATE_FUNCTIONS = {
    "coherent": _update_coherent,
    "scattered": _update_scattered,
    "fast_plateau": _update_fast_plateau,
    "slow_steady": _update_slow_steady,
    "surface_only": _update_surface_only,
}


# =============================================================================
# BKT mastery estimation — spec §4.4
# =============================================================================

def bkt_update(
    p_learned: float, observed_correct: bool, params: dict[str, float]
) -> float:
    """Single BKT update step.

    p_learned: prior P(L) before this observation
    observed_correct: whether student detected the error
    params: {P_T, P_G, P_S}
    """
    p_t = params["P_T"]
    p_g = params["P_G"]
    p_s = params["P_S"]

    # P(correct | learned) = 1 - P_S; P(correct | ~learned) = P_G
    if observed_correct:
        p_correct = p_learned * (1 - p_s) + (1 - p_learned) * p_g
        p_learned_post = p_learned * (1 - p_s) / max(p_correct, 1e-10)
    else:
        p_incorrect = p_learned * p_s + (1 - p_learned) * (1 - p_g)
        p_learned_post = p_learned * p_s / max(p_incorrect, 1e-10)

    # Transition: learning can happen even if not yet learned
    p_learned_next = p_learned_post + (1 - p_learned_post) * p_t
    return float(np.clip(p_learned_next, 0.0, 1.0))


def compute_bkt_trajectory(
    raw_trajectory: list[dict[str, float]],
) -> list[dict[str, float]]:
    """Run BKT on raw detection rates to produce smoothed mastery estimates.

    For each skill, treats detection rate as P(correct) to simulate observations.
    """
    bkt_trajectory = []
    # Initialize from BKT priors
    p_learned = {sk: BKT_PARAMS[sk]["P_L0"] for sk in SKILL_LABELS}

    for profile in raw_trajectory:
        bkt_profile = {}
        for sk in SKILL_LABELS:
            # Simulate a binary observation from the detection rate
            # Use the detection rate directly as P(correct) for this session
            detected = profile[sk] > 0.5  # Threshold: detected if rate > 0.5
            p_learned[sk] = bkt_update(p_learned[sk], detected, BKT_PARAMS[sk])
            bkt_profile[sk] = p_learned[sk]
        bkt_trajectory.append(bkt_profile)

    return bkt_trajectory


# =============================================================================
# Trajectory generation — spec §4.3
# =============================================================================

def generate_trajectory(
    archetype: str,
    n_sessions: int = N_SESSIONS,
    noise_std: float = NOISE_STD,
    seed: int | None = None,
    initial: np.ndarray | None = None,
) -> StudentTrajectory:
    """Generate a single student trajectory for the given archetype.

    Returns a StudentTrajectory with both raw and BKT-smoothed profiles.
    """
    rng = np.random.default_rng(seed)
    update_fn = UPDATE_FUNCTIONS[archetype]

    base = ARCHETYPE_INITIAL.copy() if initial is None else initial.copy()
    learning_rates = np.array([LEARNING_RATES[sk] for sk in SKILL_LABELS])

    raw_profiles = []
    over_editing_rates = []
    current = base.copy()

    for t in range(n_sessions):
        # Add noise
        noisy = current + rng.normal(0, noise_std, size=N_SKILLS)
        noisy = np.clip(noisy, 0.0, 1.0)

        profile = {SKILL_LABELS[k]: float(noisy[k]) for k in range(N_SKILLS)}
        raw_profiles.append(profile)

        # Over-editing rate decays over sessions
        oe_rate = max(0.0, OVER_EDITING_INITIAL - OVER_EDITING_DECAY_PER_SESSION * t)
        over_editing_rates.append(oe_rate)

        # Update for next session
        current = update_fn(current, learning_rates, t, rng)
        current = np.clip(current, 0.0, 1.0)

    # Compute BKT trajectory
    bkt_profiles = compute_bkt_trajectory(raw_profiles)

    student_id = f"{archetype}_{seed or 0}"
    return StudentTrajectory(
        student_id=student_id,
        archetype=archetype,
        profiles=raw_profiles,
        bkt_profiles=bkt_profiles,
        over_editing_rates=over_editing_rates,
    )


def generate_all_students(
    n_sessions: int = N_SESSIONS,
    noise_std: float = NOISE_STD,
    base_seed: int = 42,
) -> list[StudentTrajectory]:
    """Generate all 20 synthetic students across all 5 archetypes."""
    students = []
    seed_counter = base_seed
    for archetype_key, archetype_cfg in ARCHETYPES.items():
        for i in range(archetype_cfg["n_instances"]):
            student = generate_trajectory(
                archetype=archetype_key,
                n_sessions=n_sessions,
                noise_std=noise_std,
                seed=seed_counter,
            )
            student.student_id = f"{archetype_key}_{i}"
            students.append(student)
            seed_counter += 1
    return students
