"""Response evaluation and MQM scoring logic.

Implements IoU-based span matching for evaluation mode, HTER for post-editing mode,
verification scoring for navigator mode, and ranking + human-vs-MT scoring for
comparison mode.
"""

from typing import Optional

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


# ── Comparison-mode scoring (System §7.4) ───────────────────────────────────


def _kendall_tau(student: list[str], expert: list[str]) -> Optional[float]:
    """Stdlib-only Kendall's τ for two same-length rankings of the same set.

    Returns a value in [-1, 1] (1 = identical ranking, -1 = reversed).
    Returns None if the two lists don't cover the same set, or if the lists
    have fewer than 2 distinct items (τ is undefined).
    """
    if len(student) != len(expert) or set(student) != set(expert) or len(student) < 2:
        return None
    # Map each system id to its rank position in each list
    s_rank = {sys: i for i, sys in enumerate(student)}
    e_rank = {sys: i for i, sys in enumerate(expert)}
    items = list(s_rank)
    n = len(items)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            sd = s_rank[a] - s_rank[b]
            ed = e_rank[a] - e_rank[b]
            if sd * ed > 0:
                concordant += 1
            elif sd * ed < 0:
                discordant += 1
            # ties (==0) ignored — impossible here because ranks are unique
    denom = n * (n - 1) / 2
    return (concordant - discordant) / denom if denom > 0 else None


def score_comparison_response(response, item) -> ScoringResult:
    """Score an L3 comparison-mode response.

    Skill B (COMPARATIVE_RANKING):
      - Kendall's τ between student ranking and the expert ranking derived
        from MTOutput.quality_score (descending).
      - Returns τ=None if the student didn't rank every system.

    Human-vs-MT discrimination:
      - human_pick_correct = True iff student.human_pick == the mt_system id
        of the MTOutput with is_human_reference=True, OR student picked "none"
        and there is no human reference in comparison_outputs.

    Skill A (INDEPENDENT_EVAL) and PE-worthiness scoring are deferred:
      - Skill A needs per-system error manifests (Tier C follow-up).
      - PE-worthiness needs expert triage ground truth.
    """
    outputs = item.comparison_outputs or []
    if not outputs:
        # No comparison outputs — degenerate. Return a zero result.
        return ScoringResult(
            response_id=response.response_id,
            item_id=item.item_id,
            true_positives=0, false_positives=0, false_negatives=0,
            precision=0.0, recall=0.0, f1=0.0,
            detection_by_mqm={}, detection_by_tom={},
        )

    # ── Skill B: Kendall's τ ────────────────────────────────────────────────
    expert_ranking_ids: list[str] = []
    tau: Optional[float] = None
    if response.system_rankings:
        # Student ranking: sort by rank ascending (1 = best), then read mt_system
        student_sorted = sorted(
            response.system_rankings, key=lambda r: r.rank,
        )
        student_ranking_ids = [r.mt_system for r in student_sorted]

        # Expert ranking from quality_score descending; stable on input order
        scored = [(i, o) for i, o in enumerate(outputs) if o.quality_score is not None]
        unscored = [(i, o) for i, o in enumerate(outputs) if o.quality_score is None]
        scored.sort(key=lambda pair: pair[1].quality_score, reverse=True)
        expert_ranking_ids = [o.mt_system for _, o in scored] + [
            o.mt_system for _, o in unscored
        ]

        tau = _kendall_tau(student_ranking_ids, expert_ranking_ids)

    # ── Human-vs-MT discrimination ──────────────────────────────────────────
    human_pick_correct: Optional[bool] = None
    if response.human_pick is not None:
        human_outputs = [o for o in outputs if o.is_human_reference]
        if not human_outputs:
            human_pick_correct = response.human_pick.lower() == "none"
        else:
            # Could conceivably have >1 human reference; reject ambiguity.
            human_pick_correct = response.human_pick == human_outputs[0].mt_system

    # ── Synthesise an overall F1-style score so badges + analytics work ─────
    # tau is in [-1, 1]; map to [0, 1] for the precision/recall slots:
    overall = 0.5 * ((tau + 1) / 2 if tau is not None else 0.0)
    if human_pick_correct is True:
        overall += 0.5
    elif human_pick_correct is False:
        overall += 0.0
    elif human_pick_correct is None and response.human_pick is None:
        # No human-vs-MT sub-task attempted — Skill B alone scores the item
        overall = (tau + 1) / 2 if tau is not None else 0.0

    return ScoringResult(
        response_id=response.response_id,
        item_id=item.item_id,
        # Comparison mode has no per-error TP/FP/FN — leave at 0 and use the
        # comparison-specific fields below.
        true_positives=0, false_positives=0, false_negatives=0,
        precision=overall, recall=overall, f1=overall,
        detection_by_mqm={}, detection_by_tom={},
        ranking_kendall_tau=tau,
        expert_ranking=expert_ranking_ids,
        human_pick_correct=human_pick_correct,
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
