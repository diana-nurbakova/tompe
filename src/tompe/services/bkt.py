"""Bayesian Knowledge Tracing (BKT) for per-skill mastery estimation.

System spec §3.5 + Fluency Trap §2.2 / §6.2 — adaptive progression and the
Skill Radar both consume per-skill mastery probabilities. This module owns
the BKT math and per-student persistence.

Model (Corbett & Anderson 1995):
    p_mastery_{t}        — latent probability the skill is learned
    p_init               — prior at first observation (default 0.10)
    p_transit            — chance of learning during an observation (default 0.10)
    p_slip               — chance of getting it wrong despite mastery (default 0.10)
    p_guess              — chance of getting it right without mastery (default 0.20)

Update equation:
    if correct:
        p_posterior = p_m * (1 - p_slip) / (p_m * (1 - p_slip) + (1 - p_m) * p_guess)
    else:
        p_posterior = p_m * p_slip / (p_m * p_slip + (1 - p_m) * (1 - p_guess))
    p_mastery_{t+1} = p_posterior + (1 - p_posterior) * p_transit

Storage: one ``StudentBKT`` document per student under ``data/bkt/``; the
``per_skill`` mapping uses ``SkillID.value`` strings as keys (Pydantic
doesn't round-trip enum keys cleanly through model_validate).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from tompe.schemas.scoring import BKTSkillState, ScoringResult, StudentBKT
from tompe.services.datastore import bkt_store

# Default BKT parameters — tuned for short-window assessment items.
P_INIT = 0.10
P_TRANSIT = 0.10
P_SLIP = 0.10
P_GUESS = 0.20

# Cap the per-skill history list so long-running students don't bloat the JSON.
HISTORY_CAP = 200


@dataclass(frozen=True)
class BKTParams:
    p_init: float = P_INIT
    p_transit: float = P_TRANSIT
    p_slip: float = P_SLIP
    p_guess: float = P_GUESS


_DEFAULT = BKTParams()


def _posterior(p_m: float, correct: bool, params: BKTParams) -> float:
    """Bayes step: probability of mastery given the new observation."""
    if correct:
        num = p_m * (1 - params.p_slip)
        den = num + (1 - p_m) * params.p_guess
    else:
        num = p_m * params.p_slip
        den = num + (1 - p_m) * (1 - params.p_guess)
    if den <= 0:
        return p_m
    return num / den


def bkt_step(p_mastery: float, correct: bool, params: BKTParams = _DEFAULT) -> float:
    """Apply one BKT update: Bayes posterior + transition."""
    post = _posterior(p_mastery, correct, params)
    return post + (1 - post) * params.p_transit


def get_or_create_bkt(student_id: str) -> StudentBKT:
    """Load the student's BKT document, or create a fresh one."""
    record = bkt_store.get(student_id, StudentBKT)
    if record is None:
        record = StudentBKT(student_id=student_id)
        bkt_store.save(record)
    return record


def _ensure_skill(record: StudentBKT, skill_key: str, params: BKTParams) -> BKTSkillState:
    state = record.per_skill.get(skill_key)
    if state is None:
        state = BKTSkillState(p_mastery=params.p_init)
        record.per_skill[skill_key] = state
    return state


def update_skill(
    student_id: str,
    skill_key: str,
    correct: bool,
    params: BKTParams = _DEFAULT,
    *,
    persist: bool = True,
) -> float:
    """Apply a single BKT update for one (student, skill) pair.

    Returns the new ``p_mastery``. If ``persist`` is False the change is
    applied to the in-memory record but not written to disk — useful when
    replaying a batch of observations and saving once at the end.
    """
    record = get_or_create_bkt(student_id)
    state = _ensure_skill(record, skill_key, params)
    state.p_mastery = bkt_step(state.p_mastery, correct, params)
    state.n_observations += 1
    if correct:
        state.n_correct += 1
    state.history.append((
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        bool(correct),
        round(state.p_mastery, 4),
    ))
    if len(state.history) > HISTORY_CAP:
        state.history = state.history[-HISTORY_CAP:]
    if persist:
        bkt_store.save(record)
    return state.p_mastery


def update_from_scoring(
    student_id: str,
    scoring: ScoringResult,
    params: BKTParams = _DEFAULT,
) -> dict[str, float]:
    """Apply BKT updates derived from a ScoringResult's `detection_by_skill`.

    For each skill in ``detection_by_skill``, we feed ``detected`` "correct"
    observations and ``total - detected`` "incorrect" observations, in that
    order. Persists once at the end.

    Returns the post-update mastery probability per skill touched.
    """
    record = get_or_create_bkt(student_id)
    touched: dict[str, float] = {}
    for skill, cat in (scoring.detection_by_skill or {}).items():
        skill_key = skill.value if hasattr(skill, "value") else str(skill)
        state = _ensure_skill(record, skill_key, params)
        for _ in range(cat.detected):
            state.p_mastery = bkt_step(state.p_mastery, True, params)
            state.n_observations += 1
            state.n_correct += 1
            state.history.append((
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                True,
                round(state.p_mastery, 4),
            ))
        missed = max(0, cat.total - cat.detected)
        for _ in range(missed):
            state.p_mastery = bkt_step(state.p_mastery, False, params)
            state.n_observations += 1
            state.history.append((
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                False,
                round(state.p_mastery, 4),
            ))
        if len(state.history) > HISTORY_CAP:
            state.history = state.history[-HISTORY_CAP:]
        touched[skill_key] = state.p_mastery
    if touched:
        bkt_store.save(record)
    return touched


def get_mastery(student_id: str, skill_key: str) -> Optional[float]:
    """Return current p_mastery for a (student, skill); None if no observations."""
    record = bkt_store.get(student_id, StudentBKT)
    if not record:
        return None
    state = record.per_skill.get(skill_key)
    if state is None or state.n_observations == 0:
        return None
    return state.p_mastery


def bkt_skill_profile(student_id: str) -> dict[str, float]:
    """Return ``{S1: p_mastery, ..., S7: p_mastery}`` for the Skill Radar.

    Skills with no observations are reported as 0.0 so the radar still
    renders all 7 axes. Caller can decide to fall back to a different
    source (e.g. `aggregate_skill_profile`) when the record is empty.
    """
    skills = [f"S{i}" for i in range(1, 8)]
    record = bkt_store.get(student_id, StudentBKT)
    if not record:
        return {sk: 0.0 for sk in skills}
    out: dict[str, float] = {}
    for sk in skills:
        state = record.per_skill.get(sk)
        out[sk] = state.p_mastery if state and state.n_observations > 0 else 0.0
    return out
