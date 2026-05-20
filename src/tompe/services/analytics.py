"""Performance aggregation and blind-spot detection.

Implements the longitudinal analytics from System spec §3.9. Each student
accumulates per-MQM and per-ToM detection-rate time series; ``BlindSpot``s are
flagged when a (MQM, ToM) cell sits below ``threshold`` across at least
``min_sessions`` distinct sessions.

Functions split into:

  * stateless aggregators (``update_student_profile`` / ``detect_blind_spots``
    / ``compute_class_analytics``) that take models in and return models out;
  * convenience factories (``build_profile_from_store`` /
    ``compute_class_analytics_for_class``) that load from the datastore and
    persist the resulting ``StudentProfile`` under ``data/profiles/``.

The convenience layer is what the API + teacher dashboard call; the stateless
layer is what the unit tests exercise.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from tompe.schemas.enums import MQMCategory, TOMLevel
from tompe.schemas.item import AssessmentItem
from tompe.schemas.response import StudentResponse
from tompe.schemas.scoring import (
    BlindSpot,
    PerformanceTimeSeries,
    ScoringResult,
    StudentProfile,
)
from tompe.services.datastore import (
    feedback_store,
    items_store,
    profiles_store,
    responses_store,
)

logger = logging.getLogger(__name__)


# ── Trend detection ─────────────────────────────────────────────────────────

# Slope thresholds for the rolling trend label. Conservative: only call a
# trend when there are at least 3 sessions and the linear-fit slope clears
# the band.
_TREND_MIN_SESSIONS = 3
_TREND_SLOPE_THRESHOLD = 0.02  # per-session improvement (in [0, 1])


def _trend(values: list[float]) -> str:
    """Classify a per-session series as improving/stable/declining.

    Linear fit slope on the (session_index, detection_rate) points; returns
    "improving" if slope > +threshold, "declining" if slope < -threshold,
    "stable" otherwise. Short series default to "stable" so the trend label
    doesn't whiplash off the first 1–2 sessions.
    """
    n = len(values)
    if n < _TREND_MIN_SESSIONS:
        return "stable"
    # Simple OLS slope: cov(x, y) / var(x), with x = 0..n-1
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den == 0:
        return "stable"
    slope = num / den
    if slope > _TREND_SLOPE_THRESHOLD:
        return "improving"
    if slope < -_TREND_SLOPE_THRESHOLD:
        return "declining"
    return "stable"


# ── Stateless aggregators ───────────────────────────────────────────────────


def update_student_profile(
    profile: StudentProfile,
    session_results: list[dict],
) -> StudentProfile:
    """Fold new session results into the profile.

    Each entry in ``session_results`` must have keys:
      - ``session_id``: str
      - ``detection_by_mqm``: {MQMCategory(str): {detected, total, ...}}
      - ``detection_by_tom``: {TOMLevel(str): {detected, total, ...}}
      - (optional) ``false_positive_rate``: float in [0, 1]

    Existing entries in the profile's time series are preserved and extended.
    Duplicates (same session_id) are skipped so re-fetching the store is
    idempotent.
    """
    seen_mqm_sessions: dict[MQMCategory, set[str]] = {
        cat: set(series.session_ids)
        for cat, series in profile.mqm_performance.items()
    }
    seen_tom_sessions: dict[TOMLevel, set[str]] = {
        lvl: set(series.session_ids)
        for lvl, series in profile.tom_performance.items()
    }

    for sr in session_results:
        sid = sr.get("session_id")
        if not sid:
            continue
        for mqm_key, cell in (sr.get("detection_by_mqm") or {}).items():
            try:
                cat = MQMCategory(mqm_key) if not isinstance(mqm_key, MQMCategory) else mqm_key
            except ValueError:
                continue
            if sid in seen_mqm_sessions.get(cat, set()):
                continue
            rate = _safe_rate(cell)
            series = profile.mqm_performance.get(cat)
            if series is None:
                profile.mqm_performance[cat] = PerformanceTimeSeries(
                    session_ids=[sid], detection_rates=[rate], trend="stable",
                )
                seen_mqm_sessions[cat] = {sid}
            else:
                series.session_ids.append(sid)
                series.detection_rates.append(rate)
                series.trend = _trend(series.detection_rates)
                seen_mqm_sessions.setdefault(cat, set()).add(sid)

        for tom_key, cell in (sr.get("detection_by_tom") or {}).items():
            try:
                tom = TOMLevel(tom_key) if not isinstance(tom_key, TOMLevel) else tom_key
            except ValueError:
                continue
            if sid in seen_tom_sessions.get(tom, set()):
                continue
            rate = _safe_rate(cell)
            series = profile.tom_performance.get(tom)
            if series is None:
                profile.tom_performance[tom] = PerformanceTimeSeries(
                    session_ids=[sid], detection_rates=[rate], trend="stable",
                )
                seen_tom_sessions[tom] = {sid}
            else:
                series.session_ids.append(sid)
                series.detection_rates.append(rate)
                series.trend = _trend(series.detection_rates)
                seen_tom_sessions.setdefault(tom, set()).add(sid)

        fp = sr.get("false_positive_rate")
        if isinstance(fp, (int, float)):
            profile.false_positive_rate_history.append(float(fp))

    profile.sessions_completed = len({
        sid
        for series in profile.mqm_performance.values()
        for sid in series.session_ids
    })
    return profile


def _safe_rate(cell) -> float:
    """Pull a detection rate from a CategoryScore-shaped dict or model."""
    if hasattr(cell, "detection_rate"):
        return float(cell.detection_rate)
    if isinstance(cell, dict):
        if "detection_rate" in cell:
            return float(cell["detection_rate"])
        det = cell.get("detected", 0)
        tot = cell.get("total", 0)
        return det / tot if tot > 0 else 0.0
    return 0.0


def detect_blind_spots(
    profile: StudentProfile,
    threshold: float = 0.5,
    min_sessions: int = 3,
) -> list[BlindSpot]:
    """Identify (MQM × ToM) intersections sitting below ``threshold``.

    Cross-products MQM × ToM cells using the per-MQM and per-ToM time series.
    Reports a BlindSpot for each combination where the mean detection rate
    (computed over the *intersection* of session ids) is below ``threshold``
    across at least ``min_sessions`` shared sessions.
    """
    spots: list[BlindSpot] = []
    for mqm, mqm_ts in profile.mqm_performance.items():
        mqm_by_session: dict[str, float] = dict(zip(mqm_ts.session_ids, mqm_ts.detection_rates))
        for tom, tom_ts in profile.tom_performance.items():
            tom_by_session: dict[str, float] = dict(zip(tom_ts.session_ids, tom_ts.detection_rates))
            shared = set(mqm_by_session) & set(tom_by_session)
            if len(shared) < min_sessions:
                continue
            # Joint detection rate ≈ mean of the per-session min(mqm, tom).
            # Using the min is conservative — a cell is only "blind" when both
            # the MQM and the ToM dimension struggle in the same session.
            joint = [
                min(mqm_by_session[sid], tom_by_session[sid]) for sid in shared
            ]
            mean_rate = sum(joint) / len(joint)
            if mean_rate < threshold:
                spots.append(BlindSpot(
                    mqm_category=mqm,
                    tom_level=tom,
                    detection_rate=round(mean_rate, 4),
                    sessions_observed=len(shared),
                    example_item_ids=[],  # filled by the convenience layer
                ))
    profile.blind_spots = spots
    return spots


def compute_class_analytics(profiles: list[StudentProfile]) -> dict:
    """Aggregate a class's StudentProfiles into a summary dict.

    Returns:
        {
          "n_students": int,
          "avg_sessions": float,
          "mean_detection_rate_by_mqm": {MQMCategory.value: float},
          "mean_detection_rate_by_tom": {TOMLevel.value: float},
          "blind_spots_top": [
            {"mqm_category": str, "tom_level": str, "n_students": int, "mean_rate": float},
            ...  # top 5 most-common cells, sorted by n_students desc
          ],
          "over_editing_rate_mean": float,  # mean of per-student FP-rate history means
        }
    """
    n = len(profiles)
    if n == 0:
        return {
            "n_students": 0, "avg_sessions": 0.0,
            "mean_detection_rate_by_mqm": {},
            "mean_detection_rate_by_tom": {},
            "blind_spots_top": [],
            "over_editing_rate_mean": 0.0,
        }

    avg_sessions = sum(p.sessions_completed for p in profiles) / n

    # Mean of per-student means, by MQM and ToM
    def _per_dim_mean(get_series):
        bucket: dict[str, list[float]] = {}
        for p in profiles:
            for key, series in get_series(p).items():
                k = key.value if hasattr(key, "value") else str(key)
                if series.detection_rates:
                    bucket.setdefault(k, []).append(
                        sum(series.detection_rates) / len(series.detection_rates)
                    )
        return {k: sum(vs) / len(vs) for k, vs in bucket.items()}

    mean_mqm = _per_dim_mean(lambda p: p.mqm_performance)
    mean_tom = _per_dim_mean(lambda p: p.tom_performance)

    # Blind-spot crosstab: (mqm, tom) -> [rates across students who have it]
    spot_bucket: dict[tuple[str, str], list[float]] = {}
    for p in profiles:
        for s in p.blind_spots:
            key = (
                s.mqm_category.value if hasattr(s.mqm_category, "value") else str(s.mqm_category),
                s.tom_level.value if hasattr(s.tom_level, "value") else str(s.tom_level),
            )
            spot_bucket.setdefault(key, []).append(s.detection_rate)
    blind_spots_top = sorted(
        (
            {
                "mqm_category": mqm,
                "tom_level": tom,
                "n_students": len(rates),
                "mean_rate": round(sum(rates) / len(rates), 4),
            }
            for (mqm, tom), rates in spot_bucket.items()
        ),
        key=lambda d: (-d["n_students"], d["mean_rate"]),
    )[:5]

    over_means = [
        sum(p.false_positive_rate_history) / len(p.false_positive_rate_history)
        for p in profiles if p.false_positive_rate_history
    ]
    over_mean = sum(over_means) / len(over_means) if over_means else 0.0

    return {
        "n_students": n,
        "avg_sessions": round(avg_sessions, 2),
        "mean_detection_rate_by_mqm": {k: round(v, 4) for k, v in mean_mqm.items()},
        "mean_detection_rate_by_tom": {k: round(v, 4) for k, v in mean_tom.items()},
        "blind_spots_top": blind_spots_top,
        "over_editing_rate_mean": round(over_mean, 4),
    }


# ── Datastore-backed convenience layer ──────────────────────────────────────


def _session_payloads_for_student(
    student_id: str,
) -> tuple[list[dict], dict[tuple[str, str], list[str]]]:
    """Pull all ScoringResults for ``student_id`` and shape them for the
    stateless aggregator. Also returns a per-(mqm, tom) → [item_id] index so
    BlindSpot example_item_ids can be filled in.
    """
    responses = responses_store.list_all(
        StudentResponse, filter_fn=lambda r: r.student_id == student_id,
    )
    by_response = {r.response_id: r for r in responses}
    scores = feedback_store.list_all(
        ScoringResult, filter_fn=lambda s: s.response_id in by_response,
    )

    payloads: list[dict] = []
    examples: dict[tuple[str, str], list[str]] = {}
    for s in scores:
        resp = by_response.get(s.response_id)
        if resp is None:
            continue
        # Build the per-response detection_by_mqm / detection_by_tom dicts
        mqm_dict = {
            (k.value if hasattr(k, "value") else str(k)): v.model_dump()
            for k, v in (s.detection_by_mqm or {}).items()
        }
        tom_dict = {
            (k.value if hasattr(k, "value") else str(k)): v.model_dump()
            for k, v in (s.detection_by_tom or {}).items()
        }
        # FP rate from precision/false_positives (best-effort)
        total_picks = s.true_positives + s.false_positives
        fp_rate = (s.false_positives / total_picks) if total_picks > 0 else 0.0
        payloads.append({
            "session_id": resp.session_id,
            "detection_by_mqm": mqm_dict,
            "detection_by_tom": tom_dict,
            "false_positive_rate": fp_rate,
        })
        # Index item ids by (mqm, tom) for blind-spot example lookup
        for mqm_key in mqm_dict:
            for tom_key in tom_dict:
                examples.setdefault((mqm_key, tom_key), []).append(resp.item_id)
    return payloads, examples


def build_profile_from_store(student_id: str, display_name: str = "") -> StudentProfile:
    """Rebuild a ``StudentProfile`` from stored responses + scores and persist it.

    Recomputes the full profile from scratch (idempotent) rather than diffing,
    so cached profiles can be rebuilt on demand without orphaned state.
    """
    profile = StudentProfile(
        student_id=student_id, display_name=display_name or student_id,
    )
    payloads, examples = _session_payloads_for_student(student_id)
    update_student_profile(profile, payloads)
    spots = detect_blind_spots(profile)
    # Attach example_item_ids per blind spot, deduped + capped
    for s in spots:
        key = (
            s.mqm_category.value if hasattr(s.mqm_category, "value") else str(s.mqm_category),
            s.tom_level.value if hasattr(s.tom_level, "value") else str(s.tom_level),
        )
        ids = examples.get(key, [])
        # Dedupe while preserving order; cap at 5
        seen: set[str] = set()
        deduped: list[str] = []
        for iid in ids:
            if iid not in seen:
                seen.add(iid)
                deduped.append(iid)
            if len(deduped) >= 5:
                break
        s.example_item_ids = deduped
    profile.blind_spots = spots
    profiles_store.save(profile)
    return profile


def compute_class_analytics_for_class(
    student_ids: Iterable[str],
    display_name_by_id: Optional[dict[str, str]] = None,
) -> dict:
    """Build (or rebuild) profiles for every student id and aggregate."""
    profiles: list[StudentProfile] = []
    name_map = display_name_by_id or {}
    for sid in student_ids:
        profiles.append(build_profile_from_store(sid, display_name=name_map.get(sid, sid)))
    return compute_class_analytics(profiles)
