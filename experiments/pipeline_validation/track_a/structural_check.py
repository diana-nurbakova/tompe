"""A1 — Structural validation of pipeline output.

Checks whether each AssessmentItem produced by the injection pipeline is
well-formed: XML tags parse correctly, tag attributes belong to the codebook,
span offsets are within bounds, surrounding text is preserved, and clean/
injected item invariants hold.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from tompe.pipeline.error_injector import (
    _TAG_PATTERN,
    _get_span_positions,
    _parse_xml_tags,
    _strip_xml_tags,
)
from tompe.pipeline.mqm_taxonomy import validate_tag_type
from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel
from tompe.schemas.error import InjectedError
from tompe.schemas.item import AssessmentItem

from experiments.pipeline_validation.config import (
    RESULTS_DIR,
    STRUCTURAL_PASS_TARGET,
    ensure_dirs,
)

logger = logging.getLogger(__name__)

# All valid severity and ToM values (for attribute validation)
_VALID_SEVERITIES = {s.value for s in Severity}
_VALID_TOM_LEVELS = {t.value for t in TOMLevel}

# Minimum difflib similarity between surrounding text and reference
_SURROUNDING_SIMILARITY_THRESHOLD = 0.95


# ── Result dataclass ─────────────────────────────────────────────────────────


@dataclass
class StructuralCheckResult:
    """Result of structural validation for a single item."""

    item_id: str
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.checks_failed) == 0


# ── Per-item checks ──────────────────────────────────────────────────────────


def _check_xml_tags_parse(item: AssessmentItem) -> tuple[list[str], list[str]]:
    """Check that every error's xml_tag field parses correctly."""
    passed: list[str] = []
    failed: list[str] = []

    for err in item.errors:
        if not isinstance(err, InjectedError):
            continue
        if not err.xml_tag:
            failed.append(f"error {err.error_id}: xml_tag is empty")
            continue
        parsed = _parse_xml_tags(err.xml_tag)
        if parsed:
            passed.append(f"error {err.error_id}: xml_tag parses correctly")
        else:
            failed.append(f"error {err.error_id}: xml_tag failed to parse")

    if not any(isinstance(e, InjectedError) for e in item.errors):
        # No injected errors — nothing to check here
        passed.append("no injected errors to validate xml for")

    return passed, failed


def _check_tag_attributes(item: AssessmentItem) -> tuple[list[str], list[str]]:
    """Check that tag attributes belong to the codebook / enum inventory."""
    passed: list[str] = []
    failed: list[str] = []

    for err in item.errors:
        if not isinstance(err, InjectedError):
            continue

        # primary_tag must be a valid PrimaryTag
        try:
            PrimaryTag(err.primary_tag)
            passed.append(f"error {err.error_id}: primary_tag valid ({err.primary_tag})")
        except ValueError:
            failed.append(
                f"error {err.error_id}: invalid primary_tag '{err.primary_tag}'"
            )

        # severity must be a valid Severity
        if err.severity.value in _VALID_SEVERITIES:
            passed.append(f"error {err.error_id}: severity valid ({err.severity})")
        else:
            failed.append(
                f"error {err.error_id}: invalid severity '{err.severity}'"
            )

        # tom_level must be a valid TOMLevel
        if err.tom_level.value in _VALID_TOM_LEVELS:
            passed.append(f"error {err.error_id}: tom_level valid ({err.tom_level})")
        else:
            failed.append(
                f"error {err.error_id}: invalid tom_level '{err.tom_level}'"
            )

        # (tag, type) pair must exist in the taxonomy
        tag_val = err.primary_tag.value if isinstance(err.primary_tag, PrimaryTag) else str(err.primary_tag)
        if validate_tag_type(tag_val, err.error_type):
            passed.append(
                f"error {err.error_id}: tag/type pair valid "
                f"({tag_val}/{err.error_type})"
            )
        else:
            failed.append(
                f"error {err.error_id}: invalid tag/type pair "
                f"({tag_val}/{err.error_type})"
            )

    return passed, failed


def _check_span_offsets(item: AssessmentItem) -> tuple[list[str], list[str]]:
    """Check that span_start/span_end are within bounds of presented_text."""
    passed: list[str] = []
    failed: list[str] = []
    text_len = len(item.presented_text)

    for err in item.errors:
        if not isinstance(err, InjectedError):
            continue

        eid = err.error_id
        if err.span_start < 0:
            failed.append(f"error {eid}: span_start ({err.span_start}) < 0")
        elif err.span_end > text_len:
            failed.append(
                f"error {eid}: span_end ({err.span_end}) > "
                f"text length ({text_len})"
            )
        elif err.span_start >= err.span_end:
            failed.append(
                f"error {eid}: span_start ({err.span_start}) >= "
                f"span_end ({err.span_end})"
            )
        else:
            # Also verify the injected_text matches the slice
            actual_span = item.presented_text[err.span_start:err.span_end]
            if actual_span == err.injected_text:
                passed.append(
                    f"error {eid}: span [{err.span_start}:{err.span_end}] "
                    f"within bounds and matches injected_text"
                )
            else:
                failed.append(
                    f"error {eid}: span text mismatch — "
                    f"expected '{err.injected_text}', "
                    f"got '{actual_span}'"
                )

    return passed, failed


def _check_surrounding_text(item: AssessmentItem) -> tuple[list[str], list[str]]:
    """Check that text outside error spans is preserved from the reference.

    Reconstructs what the reference should look like by replacing each
    injected span with its original_text, then compares with difflib.
    """
    passed: list[str] = []
    failed: list[str] = []

    injected_errors = [e for e in item.errors if isinstance(e, InjectedError)]
    if not injected_errors:
        passed.append("no injected errors — surrounding text check skipped")
        return passed, failed

    # Reconstruct reference from presented_text by reverting all injections
    reconstructed = item.presented_text
    # Sort errors by span_start descending so replacements don't shift offsets
    sorted_errors = sorted(injected_errors, key=lambda e: e.span_start, reverse=True)
    for err in sorted_errors:
        reconstructed = (
            reconstructed[:err.span_start]
            + err.original_text
            + reconstructed[err.span_end:]
        )

    similarity = SequenceMatcher(
        None, reconstructed, item.reference_translation
    ).ratio()

    if similarity >= _SURROUNDING_SIMILARITY_THRESHOLD:
        passed.append(
            f"surrounding text preserved (similarity={similarity:.4f})"
        )
    else:
        failed.append(
            f"surrounding text differs from reference "
            f"(similarity={similarity:.4f}, "
            f"threshold={_SURROUNDING_SIMILARITY_THRESHOLD})"
        )

    return passed, failed


def _check_error_presence(item: AssessmentItem) -> tuple[list[str], list[str]]:
    """Check clean/injected invariants.

    Non-clean items must have at least one error.
    Clean items must have no modifications (presented_text == reference).
    """
    passed: list[str] = []
    failed: list[str] = []

    injected_errors = [e for e in item.errors if isinstance(e, InjectedError)]
    is_clean = len(injected_errors) == 0

    if is_clean:
        # Clean item: presented_text should equal reference_translation
        if item.presented_text == item.reference_translation:
            passed.append("clean item: presented_text matches reference")
        else:
            sim = SequenceMatcher(
                None, item.presented_text, item.reference_translation
            ).ratio()
            failed.append(
                f"clean item: presented_text differs from reference "
                f"(similarity={sim:.4f})"
            )
    else:
        # Non-clean item: must have at least one error
        passed.append(
            f"non-clean item: {len(injected_errors)} error(s) present"
        )
        # presented_text should differ from reference
        if item.presented_text == item.reference_translation:
            failed.append(
                "non-clean item: presented_text identical to reference "
                "despite having injected errors"
            )

    return passed, failed


# ── Public API ────────────────────────────────────────────────────────────────


def check_item(item: AssessmentItem) -> StructuralCheckResult:
    """Run all structural checks on a single AssessmentItem."""
    result = StructuralCheckResult(item_id=item.item_id)

    check_functions = [
        _check_xml_tags_parse,
        _check_tag_attributes,
        _check_span_offsets,
        _check_surrounding_text,
        _check_error_presence,
    ]

    for fn in check_functions:
        p, f = fn(item)
        result.checks_passed.extend(p)
        result.checks_failed.extend(f)

    return result


def check_batch(items: list[AssessmentItem]) -> dict:
    """Run structural checks on a batch and return aggregate summary.

    Returns dict with:
        pass_rate: float (fraction of items that passed all checks)
        total_items: int
        passed_items: int
        failed_items: int
        per_check_rates: dict mapping check-name -> pass-rate
        failures: list of dicts with item_id and failed checks
    """
    results = [check_item(item) for item in items]

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    pass_rate = passed_count / max(total, 1)

    # Aggregate per-check pass rates
    check_names = [
        "xml_tags_parse",
        "tag_attributes",
        "span_offsets",
        "surrounding_text",
        "error_presence",
    ]
    check_functions = [
        _check_xml_tags_parse,
        _check_tag_attributes,
        _check_span_offsets,
        _check_surrounding_text,
        _check_error_presence,
    ]
    per_check_rates: dict[str, float] = {}
    for name, fn in zip(check_names, check_functions):
        check_pass_count = 0
        for item in items:
            _, failures = fn(item)
            if not failures:
                check_pass_count += 1
        per_check_rates[name] = check_pass_count / max(total, 1)

    # Collect failures
    failures = [
        {"item_id": r.item_id, "checks_failed": r.checks_failed}
        for r in results
        if not r.passed
    ]

    summary = {
        "pass_rate": pass_rate,
        "total_items": total,
        "passed_items": passed_count,
        "failed_items": total - passed_count,
        "meets_target": pass_rate >= STRUCTURAL_PASS_TARGET,
        "target": STRUCTURAL_PASS_TARGET,
        "per_check_rates": per_check_rates,
        "failures": failures,
    }

    logger.info(
        "Structural check: %d/%d passed (%.1f%%), target %.0f%%",
        passed_count,
        total,
        pass_rate * 100,
        STRUCTURAL_PASS_TARGET * 100,
    )

    return summary


def save_results(summary: dict, output_dir: Path | None = None) -> Path:
    """Save structural check results to JSON."""
    ensure_dirs()
    out_dir = output_dir or (RESULTS_DIR / "track_a")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "a1_structural_check.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Structural check results saved to %s", out_path)
    return out_path


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="A1: Structural validation of pipeline items."
    )
    parser.add_argument(
        "--items-file",
        type=str,
        required=True,
        help="Path to JSON file with list of AssessmentItem dicts.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save results (default: results/track_a/).",
    )
    args = parser.parse_args()

    items_path = Path(args.items_file)
    if not items_path.exists():
        logger.error("Items file not found: %s", items_path)
        sys.exit(1)

    with open(items_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    items = [AssessmentItem(**item) for item in raw_items]
    logger.info("Loaded %d items from %s", len(items), items_path)

    summary = check_batch(items)
    out_dir = Path(args.output_dir) if args.output_dir else None
    save_results(summary, output_dir=out_dir)

    if not summary["meets_target"]:
        logger.warning(
            "BELOW TARGET: pass rate %.1f%% < %.0f%%",
            summary["pass_rate"] * 100,
            STRUCTURAL_PASS_TARGET * 100,
        )
        sys.exit(1)

    logger.info("All structural checks meet target.")
