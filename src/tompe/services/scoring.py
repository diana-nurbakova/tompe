"""Response evaluation and MQM scoring logic.

Implements IoU-based span matching for evaluation mode, HTER for post-editing mode,
and verification scoring for navigator mode.
"""

from tompe.schemas.enums import MQMCategory, PrimaryTag, SkillID, TOMLevel
from tompe.schemas.item import AssessmentItem
from tompe.schemas.response import StudentResponse
from tompe.schemas.scoring import CategoryScore, ScoringResult

# Map PrimaryTag → MQMCategory for scoring aggregation
_TAG_TO_MQM: dict[str, str] = {
    PrimaryTag.MISTRANSLATION: MQMCategory.ACCURACY,
    PrimaryTag.OMISSION: MQMCategory.ACCURACY,
    PrimaryTag.ADDITION: MQMCategory.ACCURACY,
    PrimaryTag.UNTRANSLATED: MQMCategory.ACCURACY,
    PrimaryTag.GRAMMAR: MQMCategory.FLUENCY,
    PrimaryTag.SPELLING: MQMCategory.FLUENCY,
    PrimaryTag.PUNCTUATION: MQMCategory.FLUENCY,
    PrimaryTag.TERMINOLOGY: MQMCategory.TERMINOLOGY,
    PrimaryTag.STYLE: MQMCategory.STYLE,
    PrimaryTag.LOCALE: MQMCategory.LOCALE,
}


def compute_span_iou(span_a: tuple[int, int], span_b: tuple[int, int]) -> float:
    """Compute character-level Intersection over Union between two spans."""
    start = max(span_a[0], span_b[0])
    end = min(span_a[1], span_b[1])
    intersection = max(0, end - start)
    union = (span_a[1] - span_a[0]) + (span_b[1] - span_b[0]) - intersection
    return intersection / union if union > 0 else 0.0


def _text_overlap(s_start, s_end, gt_err, item_text: str) -> bool:
    """Check if student span overlaps with ground truth error text (fuzzy)."""
    student_text = item_text[s_start:s_end].lower().strip()
    gt_text = ""
    if hasattr(gt_err, "injected_text") and gt_err.injected_text:
        gt_text = gt_err.injected_text.lower().strip()
    elif hasattr(gt_err, "original_text") and gt_err.original_text:
        gt_text = gt_err.original_text.lower().strip()
    if not student_text or not gt_text:
        return False
    # Check if one contains the other or significant overlap
    return student_text in gt_text or gt_text in student_text


def score_evaluation_response(
    response: StudentResponse,
    item: AssessmentItem,
    iou_threshold: float = 0.3,
) -> ScoringResult:
    """Score an evaluation-mode response using IoU-based span matching.

    Uses a lower IoU threshold (0.3) with text-overlap fallback to be
    more forgiving of imprecise student selections.
    """
    ground_truth = item.errors
    student_errors = response.identified_errors or []
    item_text = item.presented_text or ""

    # Track which ground-truth errors are matched
    gt_matched = [False] * len(ground_truth)
    student_matched = [False] * len(student_errors)

    # Greedy matching: for each student error, find best IoU ground-truth match
    for s_idx, s_err in enumerate(student_errors):
        best_iou = 0.0
        best_gt_idx = -1
        for gt_idx, gt_err in enumerate(ground_truth):
            if gt_matched[gt_idx]:
                continue
            iou = compute_span_iou(
                (s_err.span_start, s_err.span_end),
                (gt_err.span_start, gt_err.span_end),
            )
            # Also try text-based matching as fallback
            if iou < iou_threshold:
                if _text_overlap(s_err.span_start, s_err.span_end, gt_err, item_text):
                    iou = max(iou, iou_threshold)  # Boost to threshold
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = gt_idx

        if best_iou >= iou_threshold and best_gt_idx >= 0:
            gt_matched[best_gt_idx] = True
            student_matched[s_idx] = True

    tp = sum(gt_matched)
    fp = sum(1 for m in student_matched if not m)
    fn = sum(1 for m in gt_matched if not m)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Per-MQM breakdown
    mqm_counts: dict[MQMCategory, dict[str, int]] = {}
    for gt_idx, gt_err in enumerate(ground_truth):
        mqm = MQMCategory(_TAG_TO_MQM.get(gt_err.primary_tag, MQMCategory.ACCURACY))
        if mqm not in mqm_counts:
            mqm_counts[mqm] = {"detected": 0, "total": 0}
        mqm_counts[mqm]["total"] += 1
        if gt_matched[gt_idx]:
            mqm_counts[mqm]["detected"] += 1

    detection_by_mqm = {
        mqm: CategoryScore(
            detected=c["detected"],
            total=c["total"],
            detection_rate=c["detected"] / c["total"] if c["total"] > 0 else 0.0,
        )
        for mqm, c in mqm_counts.items()
    }

    # Per-ToM breakdown
    tom_counts: dict[TOMLevel, dict[str, int]] = {}
    for gt_idx, gt_err in enumerate(ground_truth):
        tom = gt_err.tom_level
        if tom not in tom_counts:
            tom_counts[tom] = {"detected": 0, "total": 0}
        tom_counts[tom]["total"] += 1
        if gt_matched[gt_idx]:
            tom_counts[tom]["detected"] += 1

    detection_by_tom = {
        tom: CategoryScore(
            detected=c["detected"],
            total=c["total"],
            detection_rate=c["detected"] / c["total"] if c["total"] > 0 else 0.0,
        )
        for tom, c in tom_counts.items()
    }

    # Per-Skill breakdown (S1-S7)
    skill_counts: dict[SkillID, dict[str, int]] = {}
    for gt_idx, gt_err in enumerate(ground_truth):
        skill = gt_err.primary_skill
        if skill not in skill_counts:
            skill_counts[skill] = {"detected": 0, "total": 0}
        skill_counts[skill]["total"] += 1
        if gt_matched[gt_idx]:
            skill_counts[skill]["detected"] += 1

    detection_by_skill = {
        skill: CategoryScore(
            detected=c["detected"],
            total=c["total"],
            detection_rate=c["detected"] / c["total"] if c["total"] > 0 else 0.0,
        )
        for skill, c in skill_counts.items()
    }

    return ScoringResult(
        response_id=response.response_id,
        item_id=item.item_id,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        detection_by_mqm=detection_by_mqm,
        detection_by_tom=detection_by_tom,
        detection_by_skill=detection_by_skill,
    )


def score_postediting_response(
    response: StudentResponse,
    item: AssessmentItem,
) -> ScoringResult:
    """Score a post-editing response using HTER and edit analysis."""
    edited = response.edited_text or ""
    reference = item.reference_translation

    # Simple character-level edit distance (Levenshtein) for HTER
    # Using dynamic programming
    n, m = len(edited), len(reference)
    if n == 0 and m == 0:
        hter = 0.0
    elif m == 0:
        hter = 1.0
    else:
        # Optimize: use two-row DP
        prev = list(range(m + 1))
        curr = [0] * (m + 1)
        for i in range(1, n + 1):
            curr[0] = i
            for j in range(1, m + 1):
                cost = 0 if edited[i - 1] == reference[j - 1] else 1
                curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            prev, curr = curr, prev
        hter = prev[m] / m

    # Count unnecessary edits (changes to correct spans)
    unnecessary = 0
    ground_truth_spans = [(e.span_start, e.span_end) for e in item.errors]
    # Simple heuristic: if original and edited differ at a position not covered
    # by any ground-truth error span, it's an unnecessary edit
    original = item.presented_text
    min_len = min(len(original), len(edited))
    for i in range(min_len):
        if original[i] != edited[i]:
            in_error_span = any(s <= i < e for s, e in ground_truth_spans)
            if not in_error_span:
                unnecessary += 1

    return ScoringResult(
        response_id=response.response_id,
        item_id=item.item_id,
        true_positives=0,
        false_positives=0,
        false_negatives=0,
        precision=0.0,
        recall=0.0,
        f1=0.0,
        detection_by_mqm={},
        detection_by_tom={},
        hter=hter,
        unnecessary_edits=unnecessary,
        edit_quality=max(0.0, 1.0 - hter),
    )


def score_navigator_response(
    response: StudentResponse,
    item: AssessmentItem,
) -> ScoringResult:
    """Score a navigator-mode response (Confirm/Dispute on pre-annotated spans).

    Convention used by the L0 flow:
      - Real errors live in `item.errors` (keyed by `error_id`).
      - False annotations are presented from `exercise.false_annotations` with
        IDs that are NOT in `item.errors`, so any verification.error_id we don't
        recognise is treated as a decoy.

    Counts:
      - correct_confirms  : agreed with a real error      (TP)
      - correct_disputes  : disputed a false annotation   (TP) — fuels Trap Detector
      - incorrect_confirms: agreed with a false annotation (FP) — fooled by decoy
      - incorrect_disputes: disputed a real error         (FN) — missed a real bug
    """
    verifications = response.verification_responses or []
    ground_truth = {e.error_id if hasattr(e, "error_id") else str(i): e
                    for i, e in enumerate(item.errors)}

    correct_confirms = 0
    correct_disputes = 0
    incorrect_confirms = 0
    incorrect_disputes = 0

    verified_ids = set()
    for v in verifications:
        verified_ids.add(v.error_id)
        if v.error_id in ground_truth:
            if v.agrees_is_error:
                correct_confirms += 1
            else:
                incorrect_disputes += 1
        else:
            if not v.agrees_is_error:
                correct_disputes += 1
            else:
                incorrect_confirms += 1

    # Real errors the student never verified count as missed
    unverified_real = sum(1 for eid in ground_truth if eid not in verified_ids)

    tp = correct_confirms + correct_disputes
    fp = incorrect_confirms
    fn = incorrect_disputes + unverified_real

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return ScoringResult(
        response_id=response.response_id,
        item_id=item.item_id,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        detection_by_mqm={},
        detection_by_tom={},
        correct_confirms=correct_confirms,
        correct_disputes=correct_disputes,
        incorrect_confirms=incorrect_confirms,
        incorrect_disputes=incorrect_disputes,
    )


# ── Cross-response aggregation ──────────────────────────────────────────────

# Skills we always report on the radar, even with zero observations.
_RADAR_SKILLS: tuple[str, ...] = tuple(s.value for s in SkillID)


def aggregate_skill_profile(scores: list[ScoringResult]) -> dict[str, float]:
    """Aggregate per-response `detection_by_skill` into one mastery probability per skill.

    Returns a dict `{"S1": p, ..., "S7": p}` with `p` in [0, 1]. The probability
    is the pooled detection rate: total detected / total observed across `scores`.
    Skills with zero observations report 0.0 so the radar still renders all axes.

    Detection-rate-based mastery is a deliberately simple stand-in for BKT
    (Fluency Trap spec §6.2). When BKT lands in `services/progression.py` the
    radar consumer can swap to those probabilities without touching the schema.
    """
    detected: dict[str, int] = {sk: 0 for sk in _RADAR_SKILLS}
    total: dict[str, int] = {sk: 0 for sk in _RADAR_SKILLS}

    for s in scores:
        for skill, cat in (s.detection_by_skill or {}).items():
            key = skill.value if hasattr(skill, "value") else str(skill)
            if key not in detected:
                continue
            detected[key] += cat.detected
            total[key] += cat.total

    return {
        sk: (detected[sk] / total[sk] if total[sk] > 0 else 0.0)
        for sk in _RADAR_SKILLS
    }
