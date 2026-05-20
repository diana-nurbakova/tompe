"""Difficulty and scaffolding stage management.

System spec §8.2 + Fluency Trap §2.2: progression from L0 → L1 → L2 → L3
is gated on Bayesian Knowledge Tracing mastery of the *active skills* for
each stage (``PROGRESSION_STAGES``). The default mastery threshold is 0.98
(spec §6.2); teachers can still approve a level manually via
``StudentAccount.allowed_levels``.

This module wraps the BKT module (``services.bkt``) so callers don't need to
know about per-skill state — they just ask "is this student ready for the
next level?" or "what should they work on?".
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from tompe.schemas.competency import PROGRESSION_STAGES
from tompe.schemas.enums import AnnotationLevel, SkillID
from tompe.schemas.scoring import StudentProfile
from tompe.services.bkt import bkt_skill_profile, get_mastery

logger = logging.getLogger(__name__)


# Spec §6.2 sets the BKT mastery threshold for unlocking a level.
DEFAULT_MASTERY_THRESHOLD = 0.98
# Minimum observations per skill before we trust BKT enough to recommend
# promotion. Below this, we assume not enough evidence even if the BKT
# probability is high (could be a fluke from prior + p_transit only).
DEFAULT_MIN_OBSERVATIONS = 6


_LEVEL_ORDER: tuple[AnnotationLevel, ...] = (
    AnnotationLevel.NAVIGATOR,
    AnnotationLevel.SCOUT,
    AnnotationLevel.ANALYST,
    AnnotationLevel.EXPERT,
)


def _stage_for_level(level: AnnotationLevel):
    """Return the PROGRESSION_STAGES entry matching this annotation level."""
    for stage in PROGRESSION_STAGES:
        if stage.annotation_level == level:
            return stage
    return None


def _next_level(current: AnnotationLevel) -> Optional[AnnotationLevel]:
    """Next level in the progression ladder, or None if already at the top."""
    try:
        idx = _LEVEL_ORDER.index(current)
    except ValueError:
        return None
    return _LEVEL_ORDER[idx + 1] if idx + 1 < len(_LEVEL_ORDER) else None


def _prerequisite_skills_for(level: AnnotationLevel) -> list[SkillID]:
    """Skills the student must have mastered to *enter* ``level``.

    Pedagogically: to unlock level N+1, the student should be fluent in the
    skills exercised at level N. So we look up the stage whose
    ``annotation_level`` sits one rung below ``level`` and return that
    stage's ``active_skills``.
    """
    try:
        idx = _LEVEL_ORDER.index(level)
    except ValueError:
        return []
    if idx == 0:
        return []  # NAVIGATOR has no prerequisites
    prev_level = _LEVEL_ORDER[idx - 1]
    prev_stage = _stage_for_level(prev_level)
    return list(prev_stage.active_skills) if prev_stage else []


def is_level_unlocked(
    student_id: str,
    level: AnnotationLevel,
    *,
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> bool:
    """Has BKT mastery passed the threshold on the prerequisite skills?

    L0 (NAVIGATOR) is always unlocked. For higher levels, every skill in the
    *previous* stage's ``active_skills`` must have:
      * ``n_observations >= min_observations`` AND
      * ``p_mastery >= mastery_threshold``

    Falls back to False when no prerequisites are defined (defensive).
    """
    if level == AnnotationLevel.NAVIGATOR:
        return True
    prereqs = _prerequisite_skills_for(level)
    if not prereqs:
        return False
    # We need n_observations + p_mastery per skill; bkt_store via get_mastery
    # only returns p_mastery, so import the full record lazily.
    from tompe.schemas.scoring import StudentBKT
    from tompe.services.datastore import bkt_store
    record = bkt_store.get(student_id, StudentBKT)
    if record is None:
        return False
    for skill in prereqs:
        skill_key = skill.value if hasattr(skill, "value") else str(skill)
        state = record.per_skill.get(skill_key)
        if state is None or state.n_observations < min_observations:
            return False
        if state.p_mastery < mastery_threshold:
            return False
    return True


def recommend_next_level(
    profile: StudentProfile,
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
    sustained_sessions: int = 3,
) -> Optional[AnnotationLevel]:
    """Recommend the next scaffolding level, or None if the student isn't ready.

    Uses BKT mastery (spec §6.2): a level is recommended once mastery on every
    active skill for that level passes ``mastery_threshold`` and there are at
    least ``sustained_sessions`` observations on the *current-level* skills.

    ``profile`` provides the current annotation level via
    ``current_difficulty_level`` (the integer rank from 1..5 in
    ``PROGRESSION_STAGES``). The actual recommendation walks up the
    PROGRESSION_STAGES ladder.
    """
    # Map difficulty_level integer → AnnotationLevel by stage rank.
    # Default to NAVIGATOR for unknown difficulty levels (defensive).
    stage_idx = max(1, min(profile.current_difficulty_level, len(PROGRESSION_STAGES))) - 1
    current_stage = PROGRESSION_STAGES[stage_idx]
    current_level = current_stage.annotation_level
    next_level = _next_level(current_level)
    if next_level is None:
        return None  # Already at the top
    next_stage = _stage_for_level(next_level)
    if next_stage is None:
        return None

    # Translate `sustained_sessions` into "at least N observations on the
    # CURRENT level's active skills" — we want evidence the student is
    # consistently performing before suggesting a level-up.
    for skill in current_stage.active_skills:
        skill_key = skill.value if hasattr(skill, "value") else str(skill)
        mastery = get_mastery(profile.student_id, skill_key)
        if mastery is None:
            return None  # No observations on this current-level skill yet
        from tompe.schemas.scoring import StudentBKT
        from tompe.services.datastore import bkt_store
        record = bkt_store.get(profile.student_id, StudentBKT)
        state = record.per_skill.get(skill_key) if record else None
        if state is None or state.n_observations < sustained_sessions:
            return None

    if is_level_unlocked(
        profile.student_id, next_level, mastery_threshold=mastery_threshold,
    ):
        return next_level
    return None


def recommend_exercises(
    profile: StudentProfile,
    available_items: list[dict],
    *,
    max_recommendations: int = 5,
) -> list[str]:
    """Suggest exercises that target the student's blind spots.

    Heuristic: rank ``available_items`` by how many of their errors fall in
    the student's BlindSpot (MQM × ToM) cells, then return the top
    ``max_recommendations`` item ids.

    Each item dict must expose:
      - ``item_id``: str
      - ``errors``: iterable of {primary_tag/mqm_category, tom_level} dicts
        (we accept the AssessmentItem model_dump shape).
    """
    if not profile.blind_spots:
        return []
    # Build a lookup of (mqm_value, tom_value) -> blind-spot rate
    spot_keys: set[tuple[str, str]] = set()
    for s in profile.blind_spots:
        spot_keys.add((
            s.mqm_category.value if hasattr(s.mqm_category, "value") else str(s.mqm_category),
            s.tom_level.value if hasattr(s.tom_level, "value") else str(s.tom_level),
        ))

    from tompe.services.scoring import _TAG_TO_MQM
    scored: list[tuple[int, str]] = []
    for item in available_items:
        iid = item.get("item_id")
        if not iid:
            continue
        hit_count = 0
        for err in item.get("errors", []) or []:
            tag = (err.get("primary_tag") if isinstance(err, dict) else getattr(err, "primary_tag", None))
            if tag is None:
                continue
            tag_str = tag.value if hasattr(tag, "value") else str(tag)
            mqm_val = _TAG_TO_MQM.get(tag_str) or _TAG_TO_MQM.get(tag)
            mqm_value = mqm_val.value if hasattr(mqm_val, "value") else (mqm_val or "")
            tom = (err.get("tom_level") if isinstance(err, dict) else getattr(err, "tom_level", None))
            tom_str = tom.value if hasattr(tom, "value") else (tom or "")
            if (mqm_value, tom_str) in spot_keys:
                hit_count += 1
        if hit_count > 0:
            scored.append((hit_count, iid))
    scored.sort(key=lambda pair: -pair[0])
    return [iid for _, iid in scored[:max_recommendations]]
