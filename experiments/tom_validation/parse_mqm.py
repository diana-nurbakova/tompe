"""§4.1 — Parse WMT 2020 MQM TSV and extract error spans.

Reads the raw TSV, extracts <v>...</v> tags from the target field,
and produces structured error records with character offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import MQM_TSV, UNMAPPED_CATEGORIES

_V_TAG = re.compile(r"<v>(.*?)</v>")


@dataclass
class ErrorSpan:
    """A single error span extracted from the target field."""
    segment_id: int
    system: str
    doc: str
    rater: str
    category: str
    severity: str
    span_start: int
    span_end: int
    span_text: str
    source_text: str = ""
    target_clean: str = ""


def load_raw(path: Path | None = None) -> pd.DataFrame:
    """Load the raw MQM TSV into a DataFrame."""
    path = path or MQM_TSV
    df = pd.read_csv(path, sep="\t", quoting=3)  # quoting=3 = QUOTE_NONE
    # Standardize column names
    df.columns = [c.strip() for c in df.columns]
    return df


def extract_spans(target: str) -> list[tuple[int, int, str]]:
    """Extract all <v>...</v> spans from a target string.

    Returns list of (start_char, end_char, span_text) tuples.
    Character offsets are relative to the *cleaned* target (tags removed).
    """
    if not isinstance(target, str):
        return []

    spans = []
    # Track position in cleaned text
    clean_pos = 0
    last_end = 0

    for m in _V_TAG.finditer(target):
        # Characters between last match end and this match start (excluding tags)
        prefix = re.sub(r"</?v>", "", target[last_end:m.start()])
        clean_pos += len(prefix)

        span_text = m.group(1)
        spans.append((clean_pos, clean_pos + len(span_text), span_text))
        clean_pos += len(span_text)
        last_end = m.end()

    return spans


def clean_target(target: str) -> str:
    """Remove <v>...</v> tags from target string."""
    if not isinstance(target, str):
        return ""
    return re.sub(r"</?v>", "", target)


def parse_all(path: Path | None = None) -> list[ErrorSpan]:
    """Parse the full MQM TSV into a list of ErrorSpan records.

    Skips no-error rows and unmapped categories.
    When a row has multiple <v> tags, one ErrorSpan is created per span.
    """
    df = load_raw(path)
    errors: list[ErrorSpan] = []

    for _, row in df.iterrows():
        cat = row["category"]
        if cat in UNMAPPED_CATEGORIES or cat == "No-error":
            continue

        target = row["target"]
        spans = extract_spans(target)

        if not spans:
            # Row has a category but no <v> tags — treat entire target as span
            t_clean = clean_target(target)
            spans = [(0, len(t_clean), t_clean)] if t_clean else []

        t_clean = clean_target(target)
        for start, end, text in spans:
            errors.append(ErrorSpan(
                segment_id=int(row["seg_id"]),
                system=row["system"],
                doc=row["doc"],
                rater=row["rater"],
                category=cat,
                severity=row["severity"],
                span_start=start,
                span_end=end,
                span_text=text,
                source_text=row["source"] if isinstance(row["source"], str) else "",
                target_clean=t_clean,
            ))

    return errors


def errors_to_dataframe(errors: list[ErrorSpan]) -> pd.DataFrame:
    """Convert ErrorSpan list to a DataFrame for downstream use."""
    records = []
    for e in errors:
        records.append({
            "segment_id": e.segment_id,
            "system": e.system,
            "doc": e.doc,
            "rater": e.rater,
            "category": e.category,
            "severity": e.severity,
            "span_start": e.span_start,
            "span_end": e.span_end,
            "span_text": e.span_text,
            "source_text": e.source_text,
            "target_clean": e.target_clean,
        })
    return pd.DataFrame(records)
