"""§4.2 — Cross-rater error span alignment.

For each (segment_id, system) pair, aligns error spans across the 3 raters
using character-level IoU, then computes detection counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .config import IOU_THRESHOLD


@dataclass
class AlignedError:
    """A unique error location after cross-rater alignment."""
    error_id: int
    segment_id: int
    system: str
    doc: str
    span_start: int
    span_end: int
    span_text: str
    detection_count: int        # 1, 2, or 3
    detection_rate: float       # detection_count / 3
    category: str               # majority vote
    severity: str               # max severity
    raters_detected: list[str]
    raters_missed: list[str]
    source_text: str = ""
    target_clean: str = ""


def span_iou(s1: tuple[int, int], s2: tuple[int, int]) -> float:
    """Compute character-level IoU between two spans."""
    inter_start = max(s1[0], s2[0])
    inter_end = min(s1[1], s2[1])
    intersection = max(0, inter_end - inter_start)
    if intersection == 0:
        return 0.0
    union = (s1[1] - s1[0]) + (s2[1] - s2[0]) - intersection
    return intersection / union if union > 0 else 0.0


def _match_spans(
    spans_a: list[dict],
    spans_b: list[dict],
    iou_threshold: float,
) -> list[tuple[int, int, float]]:
    """Greedy bipartite matching between two sets of spans.

    Returns list of (idx_a, idx_b, iou) for matched pairs.
    """
    # Compute all pairwise IoUs
    pairs = []
    for i, a in enumerate(spans_a):
        for j, b in enumerate(spans_b):
            iou = span_iou((a["span_start"], a["span_end"]),
                           (b["span_start"], b["span_end"]))
            if iou >= iou_threshold:
                pairs.append((i, j, iou))

    # Greedy: pick highest IoU first, then remove used indices
    pairs.sort(key=lambda x: -x[2])
    used_a, used_b = set(), set()
    matches = []
    for i, j, iou in pairs:
        if i not in used_a and j not in used_b:
            matches.append((i, j, iou))
            used_a.add(i)
            used_b.add(j)
    return matches


def _majority_category(categories: list[str]) -> str:
    """Return most frequent category (ties broken by first occurrence)."""
    counts: dict[str, int] = {}
    for c in categories:
        counts[c] = counts.get(c, 0) + 1
    return max(counts, key=lambda k: counts[k])


def _max_severity(severities: list[str]) -> str:
    """Return maximum severity."""
    order = {"Major": 3, "Minor": 2, "Neutral": 1}
    return max(severities, key=lambda s: order.get(s, 0))


def align_segment(
    error_df: pd.DataFrame,
    segment_id: int,
    system: str,
    all_raters: list[str],
    iou_threshold: float = IOU_THRESHOLD,
) -> list[AlignedError]:
    """Align errors across raters for a single (segment, system) pair.

    Args:
        error_df: DataFrame filtered to this (segment_id, system).
        segment_id: The segment ID.
        system: The MT system name.
        all_raters: List of all raters who evaluated this pair.
        iou_threshold: Minimum IoU for span matching.

    Returns:
        List of AlignedError instances.
    """
    # Group spans by rater
    by_rater: dict[str, list[dict]] = {}
    for rater in all_raters:
        rater_rows = error_df[error_df["rater"] == rater]
        by_rater[rater] = rater_rows.to_dict("records")

    # Collect all spans with rater labels
    all_spans: list[dict] = []
    for rater, spans in by_rater.items():
        for s in spans:
            all_spans.append({**s, "_rater": rater, "_matched": False})

    if not all_spans:
        return []

    # Build clusters via transitive IoU matching
    clusters: list[list[int]] = []  # each cluster = list of indices into all_spans

    for i, span in enumerate(all_spans):
        if span["_matched"]:
            continue

        cluster = [i]
        span["_matched"] = True

        # Find all other spans that overlap with any span in the cluster
        changed = True
        while changed:
            changed = False
            for j, other in enumerate(all_spans):
                if other["_matched"]:
                    continue
                # Don't match spans from the same rater
                if other["_rater"] == span["_rater"]:
                    # Check against all cluster members from different raters
                    pass
                for ci in cluster:
                    cs = all_spans[ci]
                    if cs["_rater"] == other["_rater"]:
                        continue
                    iou = span_iou(
                        (cs["span_start"], cs["span_end"]),
                        (other["span_start"], other["span_end"]),
                    )
                    if iou >= iou_threshold:
                        cluster.append(j)
                        other["_matched"] = True
                        changed = True
                        break

        clusters.append(cluster)

    # Build AlignedError from each cluster
    doc = error_df["doc"].iloc[0] if "doc" in error_df.columns else ""
    source_text = error_df["source_text"].iloc[0] if "source_text" in error_df.columns else ""
    target_clean = error_df["target_clean"].iloc[0] if "target_clean" in error_df.columns else ""

    aligned: list[AlignedError] = []
    for cluster_indices in clusters:
        members = [all_spans[i] for i in cluster_indices]
        raters_detected = list({m["_rater"] for m in members})
        raters_missed = [r for r in all_raters if r not in raters_detected]

        # Union span
        union_start = min(m["span_start"] for m in members)
        union_end = max(m["span_end"] for m in members)
        # Use text from first member
        span_text = members[0].get("span_text", "")

        aligned.append(AlignedError(
            error_id=0,  # assigned later
            segment_id=segment_id,
            system=system,
            doc=doc if isinstance(doc, str) else "",
            span_start=union_start,
            span_end=union_end,
            span_text=span_text,
            detection_count=len(raters_detected),
            detection_rate=len(raters_detected) / len(all_raters),
            category=_majority_category([m["category"] for m in members]),
            severity=_max_severity([m["severity"] for m in members]),
            raters_detected=raters_detected,
            raters_missed=raters_missed,
            source_text=source_text if isinstance(source_text, str) else "",
            target_clean=target_clean if isinstance(target_clean, str) else "",
        ))

    return aligned


def align_all(
    error_df: pd.DataFrame,
    iou_threshold: float = IOU_THRESHOLD,
) -> pd.DataFrame:
    """Align errors across all (segment, system) pairs.

    Args:
        error_df: Full error DataFrame from parse_mqm.
        iou_threshold: IoU threshold for span matching.

    Returns:
        DataFrame of aligned errors with detection counts.
    """
    # Identify raters per (segment, system) from the raw data
    # We need the full evaluation data (including no-error) to know which raters
    # evaluated each pair. For simplicity, use the raters present in error_df
    # plus infer from the data.

    all_aligned: list[AlignedError] = []
    error_id = 0

    groups = error_df.groupby(["segment_id", "system"])
    total = len(groups)

    for idx, ((seg_id, sys_name), group) in enumerate(groups):
        if idx % 2000 == 0 and idx > 0:
            print(f"  Aligning: {idx}/{total} segment-system pairs...")

        # Get raters for this pair (from error annotations)
        raters = group["rater"].unique().tolist()

        # We know 3 raters per pair from the WMT design
        # But we only see raters who found errors — others may have marked no-error
        # For detection rate, we use 3 as denominator (WMT design)
        n_raters = 3

        aligned = align_segment(group, seg_id, sys_name, raters, iou_threshold)

        for ae in aligned:
            ae.error_id = error_id
            # Fix detection rate to use 3 as denominator
            ae.detection_rate = ae.detection_count / n_raters
            error_id += 1

        all_aligned.extend(aligned)

    print(f"  Alignment complete: {len(all_aligned)} unique error locations from {total} pairs")

    # Convert to DataFrame
    records = []
    for ae in all_aligned:
        records.append({
            "error_id": ae.error_id,
            "segment_id": ae.segment_id,
            "system": ae.system,
            "doc": ae.doc,
            "span_start": ae.span_start,
            "span_end": ae.span_end,
            "span_text": ae.span_text,
            "detection_count": ae.detection_count,
            "detection_rate": ae.detection_rate,
            "category": ae.category,
            "severity": ae.severity,
            "raters_detected": ",".join(ae.raters_detected),
            "raters_missed": ",".join(ae.raters_missed),
            "source_text": ae.source_text,
            "target_clean": ae.target_clean,
        })

    return pd.DataFrame(records)
