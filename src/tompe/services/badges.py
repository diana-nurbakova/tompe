"""Badge checking and XP computation service.

Implements the trigger logic from fluency-trap-badges-spec.md §2-5:
progression badges, specialisation badges, behaviour badges, and XP scoring.
"""

from datetime import datetime
from typing import Optional

from tompe.schemas.badges import (
    BadgeTier,
    CATEGORY_BADGE_NAMES,
    CATEGORY_DISPLAY_NAMES,
    CATEGORY_THRESHOLDS,
    LEVEL_TO_INT,
    PROGRESSION_BADGES,
    StudentBadges,
    compute_item_xp,
)
from tompe.schemas.scoring import ScoringResult
from tompe.services.datastore import badges_store


def get_or_create_student_badges(student_id: str) -> StudentBadges:
    """Load or create the badge record for a student."""
    record = badges_store.get(student_id, StudentBadges)
    if record is None:
        record = StudentBadges(student_id=student_id)
        badges_store.save(record)
    return record


# ── Progression badges ──────────────────────────────────────────────────────


def check_progression_badge(
    student_id: str,
    current_level: str,
    completed_exercises_at_level: int,
    exercise_id: Optional[str] = None,
) -> Optional[dict]:
    """Check if a progression badge should be awarded.

    Returns badge info dict if newly earned, None otherwise.
    """
    record = get_or_create_student_badges(student_id)
    level_int = LEVEL_TO_INT.get(current_level, 0)

    # Navigator: earned on first L0 exercise completion
    if level_int == 0:
        if not record.has_badge("navigator") and completed_exercises_at_level >= 1:
            record.add_badge("navigator", BadgeTier.NONE, exercise_id)
            badges_store.save(record)
            return {
                "badge_id": "navigator",
                "display_name": "Navigator",
                "tier": "none",
                "category": "progression",
                "description": "Complete your first exercise at Navigator level",
            }

    # Scout, Analyst, Expert: earned when the level is unlocked (implies mastery + teacher approval)
    if level_int > 0:
        badge_id, display_name = PROGRESSION_BADGES[level_int]
        if not record.has_badge(badge_id):
            record.add_badge(badge_id, BadgeTier.NONE, exercise_id)
            badges_store.save(record)
            return {
                "badge_id": badge_id,
                "display_name": display_name,
                "tier": "none",
                "category": "progression",
                "description": f"Reach {display_name} level",
            }

    return None


# ── Specialisation badges ───────────────────────────────────────────────────


def check_specialisation_badges(
    student_id: str,
    matched_categories: list[str],
    scaffolding_level: str,
    exercise_id: Optional[str] = None,
    threshold_overrides: Optional[dict[str, list[int]]] = None,
) -> list[dict]:
    """Check specialisation badges after correct detections.

    Args:
        matched_categories: List of PrimaryTag values for correctly detected errors.
        scaffolding_level: Current scaffolding level (L0 detections excluded).
        threshold_overrides: Optional per-class overrides keyed by category
            (e.g. {"GRAMMAR": [5, 15, 30]}); falls back to CATEGORY_THRESHOLDS.

    Returns list of newly earned badge info dicts.
    """
    # L0 detections don't count (pre-annotations visible)
    if scaffolding_level == "navigator":
        return []

    record = get_or_create_student_badges(student_id)
    overrides = threshold_overrides or {}
    earned = []

    for category in matched_categories:
        category_upper = category.upper() if hasattr(category, 'upper') else str(category)
        if category_upper not in CATEGORY_THRESHOLDS:
            continue

        # Increment detection counter
        record.detection_counts[category_upper] = (
            record.detection_counts.get(category_upper, 0) + 1
        )

        count = record.detection_counts[category_upper]
        thresholds = overrides.get(category_upper, CATEGORY_THRESHOLDS[category_upper])
        tiers = [BadgeTier.BRONZE, BadgeTier.SILVER, BadgeTier.GOLD]
        tier_names = ["bronze", "silver", "gold"]
        badge_id = CATEGORY_BADGE_NAMES[category_upper]
        display_name = CATEGORY_DISPLAY_NAMES[category_upper]

        # Check highest achievable tier
        for i in reversed(range(3)):
            if count >= thresholds[i]:
                tier = tiers[i]
                if not record.has_badge(badge_id, tier):
                    record.add_badge(badge_id, tier, exercise_id)
                    earned.append({
                        "badge_id": badge_id,
                        "display_name": display_name,
                        "tier": tier_names[i],
                        "category": "specialisation",
                        "description": f"{count} {category_upper.lower()} errors correctly detected",
                        "count": count,
                        "threshold": thresholds[i],
                    })
                break  # Only award highest achievable tier

    badges_store.save(record)
    return earned


# ── Behaviour badges ────────────────────────────────────────────────────────


def check_behaviour_badges(
    student_id: str,
    scoring: ScoringResult,
    scaffolding_level: str,
    n_items: int,
    exercise_id: Optional[str] = None,
    item_results: Optional[list[dict]] = None,
) -> list[dict]:
    """Check behaviour badges after exercise/item completion.

    Args:
        scoring: The scoring result for the current item.
        scaffolding_level: Current scaffolding level.
        n_items: Number of items in the exercise.
        item_results: Per-item breakdown for Clean Sheet check.

    Returns list of newly earned badge info dicts.
    """
    record = get_or_create_student_badges(student_id)
    earned = []

    # False Positive Discipline: L3 exercise (>=5 items) with zero FP
    if (scaffolding_level == "expert"
            and n_items >= 5
            and scoring.false_positives == 0
            and not record.has_badge("false_positive_discipline")):
        record.add_badge("false_positive_discipline", BadgeTier.NONE, exercise_id)
        earned.append({
            "badge_id": "false_positive_discipline",
            "display_name": "False Positive Discipline",
            "tier": "none",
            "category": "behaviour",
            "description": "Complete an Expert exercise with zero false positives",
        })

    # Clean Sheet: 100% on a single item (all errors detected, correct categories, zero FP)
    if item_results:
        for item_r in item_results:
            if (item_r.get("detected", 0) == item_r.get("total_errors", 0)
                    and item_r.get("false_positives", 0) == 0
                    and item_r.get("category_matches", 0) == item_r.get("total_errors", 0)
                    and item_r.get("total_errors", 0) > 0):
                record.clean_sheet_count += 1
                if record.clean_sheet_count == 1:
                    record.add_badge("clean_sheet", BadgeTier.NONE, exercise_id)
                    earned.append({
                        "badge_id": "clean_sheet",
                        "display_name": "Clean Sheet",
                        "tier": "none",
                        "category": "behaviour",
                        "description": "Perfect score on a segment",
                        "count": record.clean_sheet_count,
                    })
                # Update count on existing badge
                for b in record.earned_badges:
                    if b.badge_id == "clean_sheet":
                        b.count = record.clean_sheet_count

    # Trap Detector: correctly dispute >=10 false annotations at L0
    if scaffolding_level == "navigator":
        # Count correct disputes from this response (FP that were identified as false)
        # In navigator mode, TP includes correctly identified false annotations
        new_disputes = item_results[0].get("correct_disputes", 0) if item_results else 0
        record.correct_disputes += new_disputes

        if (record.correct_disputes >= 10
                and not record.has_badge("trap_detector")):
            record.add_badge("trap_detector", BadgeTier.NONE, exercise_id)
            earned.append({
                "badge_id": "trap_detector",
                "display_name": "Trap Detector",
                "tier": "none",
                "category": "behaviour",
                "description": "Correctly dispute 10 false annotations at Navigator level",
            })

    badges_store.save(record)
    return earned


# ── XP Processing ───────────────────────────────────────────────────────────


def process_xp(
    student_id: str,
    scoring: ScoringResult,
    scaffolding_level: str,
    tom_level: str,
    exercise_id: str,
    category_matches: int = 0,
    severity_matches: int = 0,
) -> tuple[int, dict]:
    """Compute and record XP for an item response.

    Returns (xp_earned, breakdown).
    """
    record = get_or_create_student_badges(student_id)

    xp, breakdown = compute_item_xp(
        true_positives=scoring.true_positives,
        false_positives=scoring.false_positives,
        category_matches=category_matches,
        severity_matches=severity_matches,
        tom_level=tom_level,
        scaffolding_level=scaffolding_level,
    )

    record.add_xp(xp, exercise_id, breakdown)
    badges_store.save(record)
    return xp, breakdown


# ── Combined post-response check ────────────────────────────────────────────


def process_badges_and_xp(
    student_id: str,
    scoring: ScoringResult,
    scaffolding_level: str,
    tom_level: str,
    exercise_id: str,
    matched_categories: list[str],
    category_matches: int = 0,
    severity_matches: int = 0,
    n_items: int = 1,
    completed_exercises_at_level: int = 0,
    item_results: Optional[list[dict]] = None,
    threshold_overrides: Optional[dict[str, list[int]]] = None,
) -> dict:
    """Run all badge checks and XP computation after a response.

    Returns a dict with newly_earned_badges, xp_earned, total_xp.
    Threshold overrides (per-class) are applied to specialisation badges.
    """
    newly_earned = []

    # Progression badges
    prog = check_progression_badge(
        student_id, scaffolding_level, completed_exercises_at_level, exercise_id
    )
    if prog:
        newly_earned.append(prog)

    # Specialisation badges
    spec = check_specialisation_badges(
        student_id, matched_categories, scaffolding_level, exercise_id,
        threshold_overrides=threshold_overrides,
    )
    newly_earned.extend(spec)

    # Behaviour badges
    behav = check_behaviour_badges(
        student_id, scoring, scaffolding_level, n_items, exercise_id, item_results
    )
    newly_earned.extend(behav)

    # XP
    xp, breakdown = process_xp(
        student_id, scoring, scaffolding_level, tom_level,
        exercise_id, category_matches, severity_matches,
    )

    record = get_or_create_student_badges(student_id)

    return {
        "newly_earned_badges": newly_earned,
        "xp_earned": xp,
        "xp_breakdown": breakdown,
        "total_xp": record.total_xp,
    }


def get_badge_summary(
    student_id: str,
    threshold_overrides: Optional[dict[str, list[int]]] = None,
) -> dict:
    """Get a complete badge summary for display in the UI.

    Args:
        threshold_overrides: Optional per-class threshold overrides; falls back
            to CATEGORY_THRESHOLDS for any category not overridden.

    Returns a dict with all badge info, detection counts, XP.
    """
    record = get_or_create_student_badges(student_id)
    overrides = threshold_overrides or {}

    # Progression badges
    progression = []
    for level_int in range(4):
        badge_id, display_name = PROGRESSION_BADGES[level_int]
        earned = record.has_badge(badge_id)
        progression.append({
            "badge_id": badge_id,
            "display_name": display_name,
            "earned": earned,
            "level": level_int,
        })

    # Specialisation badges
    specialisation = []
    for category, badge_id in CATEGORY_BADGE_NAMES.items():
        display_name = CATEGORY_DISPLAY_NAMES[category]
        thresholds = overrides.get(category, CATEGORY_THRESHOLDS[category])
        count = record.detection_counts.get(category, 0)
        highest_tier = record.get_highest_tier(badge_id)

        # Determine next tier info
        next_tier = None
        next_threshold = None
        if highest_tier is None:
            next_tier = "bronze"
            next_threshold = thresholds[0]
        elif highest_tier == BadgeTier.BRONZE:
            next_tier = "silver"
            next_threshold = thresholds[1]
        elif highest_tier == BadgeTier.SILVER:
            next_tier = "gold"
            next_threshold = thresholds[2]

        specialisation.append({
            "badge_id": badge_id,
            "display_name": display_name,
            "mqm_tag": category,
            "current_count": count,
            "highest_tier": highest_tier.value if highest_tier else None,
            "next_tier": next_tier,
            "next_threshold": next_threshold,
            "thresholds": {"bronze": thresholds[0], "silver": thresholds[1], "gold": thresholds[2]},
        })

    # Behaviour badges
    behaviour = []
    behaviour_defs = [
        ("false_positive_discipline", "False Positive Discipline",
         "Complete an Expert exercise with zero false positives"),
        ("clean_sheet", "Clean Sheet",
         "Perfect score on a segment"),
        ("trap_detector", "Trap Detector",
         "Correctly dispute 10 false annotations at Navigator level"),
    ]
    for badge_id, display_name, desc in behaviour_defs:
        earned = record.has_badge(badge_id)
        extra = {}
        if badge_id == "clean_sheet" and earned:
            extra["count"] = record.clean_sheet_count
        if badge_id == "trap_detector":
            extra["progress"] = record.correct_disputes
            extra["threshold"] = 10
        behaviour.append({
            "badge_id": badge_id,
            "display_name": display_name,
            "description": desc,
            "earned": earned,
            **extra,
        })

    return {
        "progression": progression,
        "specialisation": specialisation,
        "behaviour": behaviour,
        "total_xp": record.total_xp,
        "xp_history": record.xp_history[-20:],  # Last 20 entries
        "detection_counts": record.detection_counts,
    }
