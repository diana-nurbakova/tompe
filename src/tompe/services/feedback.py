"""Feedback preparation logic.

Implements the cognitive forcing protocol: explanations are revealed only after
the student submits their justification. Builds the structured feedback payload
consumed by the student interface's Phase 3.
"""

from typing import Any

from tompe.schemas.item import AssessmentItem
from tompe.schemas.response import StudentResponse
from tompe.schemas.scoring import ScoringResult
from tompe.services.scoring import compute_span_iou


def prepare_feedback(
    response: StudentResponse,
    item: AssessmentItem,
    scoring: ScoringResult,
) -> dict[str, Any]:
    """Prepare the feedback payload for a scored response.

    Returns a dict with:
    - summary: overall stats (detected, missed, false_positives)
    - errors: per-error feedback cards
    """
    student_errors = response.identified_errors or []
    ground_truth = item.errors
    item_text = item.presented_text or ""

    # Match student errors to ground truth (same logic as scoring)
    gt_matched_by: dict[int, int] = {}  # gt_idx -> student_idx
    student_matched: dict[int, int] = {}  # student_idx -> gt_idx

    iou_threshold = 0.3

    for s_idx, s_err in enumerate(student_errors):
        best_iou = 0.0
        best_gt_idx = -1
        for gt_idx, gt_err in enumerate(ground_truth):
            if gt_idx in gt_matched_by:
                continue
            iou = compute_span_iou(
                (s_err.span_start, s_err.span_end),
                (gt_err.span_start, gt_err.span_end),
            )
            # Text-overlap fallback
            if iou < iou_threshold:
                student_text = item_text[s_err.span_start:s_err.span_end].lower().strip()
                gt_text = ""
                if hasattr(gt_err, "injected_text") and gt_err.injected_text:
                    gt_text = gt_err.injected_text.lower().strip()
                elif hasattr(gt_err, "original_text") and gt_err.original_text:
                    gt_text = gt_err.original_text.lower().strip()
                if student_text and gt_text and (student_text in gt_text or gt_text in student_text):
                    iou = max(iou, iou_threshold)
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = gt_idx
        if best_iou >= iou_threshold and best_gt_idx >= 0:
            gt_matched_by[best_gt_idx] = s_idx
            student_matched[s_idx] = best_gt_idx

    # Build per-error feedback cards
    error_cards = []

    # Cards for ground-truth errors (detected + missed)
    for gt_idx, gt_err in enumerate(ground_truth):
        detected = gt_idx in gt_matched_by
        card: dict[str, Any] = {
            "error_id": gt_err.error_id if hasattr(gt_err, "error_id") else f"gt_{gt_idx}",
            "detected": detected,
            "span_start": gt_err.span_start,
            "span_end": gt_err.span_end,
            "span_text": gt_err.injected_text if hasattr(gt_err, "injected_text") else "",
            "original_text": gt_err.original_text,
            "primary_tag": gt_err.primary_tag,
            "error_type": gt_err.error_type,
            "severity": gt_err.severity,
            "tom_level": gt_err.tom_level,
        }

        # Student justification (displayed first per cognitive forcing protocol)
        if detected:
            s_idx = gt_matched_by[gt_idx]
            # Find matching justification
            matching_justifications = [
                j for j in response.justifications
                if j.error_id == card["error_id"] or j.error_id is None
            ]
            if matching_justifications:
                j = matching_justifications[0]
                card["student_justification"] = {
                    "format": j.format,
                    "text": j.text,
                    "mt_misunderstanding": j.mt_misunderstanding,
                    "author_intent": j.author_intent,
                    "reader_impact": j.reader_impact,
                }
            # Student's classification
            s_err = student_errors[s_idx]
            card["student_classification"] = {
                "category": s_err.student_mqm_category,
                "severity": s_err.student_severity,
            }

        # Layer 1: Contrastive explanation
        if hasattr(gt_err, "explanation") and gt_err.explanation:
            expl = gt_err.explanation
            card["layer1"] = {
                "mt_interpretation": expl.mt_interpretation,
                "actual_meaning": expl.actual_meaning,
                "reader_impact": expl.reader_impact,
                "correction_rationale": expl.correction_rationale,
            }

        # Layer 2a: System behavior (How It Works)
        if hasattr(gt_err, "system_behavior") and gt_err.system_behavior:
            sb = gt_err.system_behavior
            card["layer2a"] = {
                "error_mechanism": sb.error_mechanism,
                "architectural_cause": sb.architectural_cause,
                "pattern_generalization": sb.pattern_generalization,
                "mt_system_specific": sb.mt_system_specific,
            }

        # Layer 2b: Technical (Under the Hood)
        if hasattr(gt_err, "technical_explanation") and gt_err.technical_explanation:
            te = gt_err.technical_explanation
            card["layer2b"] = {
                "technical_description": te.technical_description,
                "key_concepts": te.key_concepts,
                "references": te.references,
            }

        error_cards.append(card)

    # Cards for false positives (student-identified spans with no matching GT error)
    false_positive_cards = []
    for s_idx, s_err in enumerate(student_errors):
        if s_idx not in student_matched:
            false_positive_cards.append({
                "span_start": s_err.span_start,
                "span_end": s_err.span_end,
                "student_category": s_err.student_mqm_category,
                "student_severity": s_err.student_severity,
                "message": "This span does not contain an error.",
            })

    return {
        "summary": {
            "total_errors": len(ground_truth),
            "detected": scoring.true_positives,
            "missed": scoring.false_negatives,
            "false_positives": scoring.false_positives,
            "precision": scoring.precision,
            "recall": scoring.recall,
            "f1": scoring.f1,
            "score_pct": round(scoring.recall * 100),
        },
        "errors": error_cards,
        "false_positives": false_positive_cards,
        "hter": scoring.hter,
        "unnecessary_edits": scoring.unnecessary_edits,
    }
