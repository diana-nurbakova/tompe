"""Validate the codebook (remediation spec §8.1).

Sanity checks every entry in ``data/codebook/error_codebook_fr_en.json``:

  - Required fields present
  - ``(primary_tag, error_type)`` pair exists in ``ERROR_TYPE_SPECS``
  - ``tom_level``, ``primary_skill`` are valid enum values
  - ``severity_range`` is non-empty and each value is valid
  - ``definition`` and ``boundary_not`` are non-trivial (>= 20 chars,
    no leading "TODO:" or "_stub: true")
  - ``examples`` has >= 3 entries, each with non-empty ``source``,
    ``reference``, ``injected``, and an ``explanation`` block with
    all four contrastive fields
  - ``injected`` contains an inline XML tag whose attributes match
    the entry's primary_tag / error_type / severity_range

Exits non-zero when any entry fails; prints a per-entry punch list.

Usage:

    python scripts/validate_codebook.py
    python scripts/validate_codebook.py --strict   # also error on stub entries
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tompe.pipeline.mqm_taxonomy import ERROR_TYPE_SPECS  # noqa: E402
from tompe.schemas.enums import PrimaryTag, Severity, SkillID, TOMLevel  # noqa: E402

DEFAULT_CODEBOOK = PROJECT_ROOT / "data" / "codebook" / "error_codebook_fr_en.json"

_VALID_TAGS = {t.value for t in PrimaryTag}
_VALID_SEVERITIES = {s.value for s in Severity}
_VALID_TOMS = {t.value for t in TOMLevel}
_VALID_SKILLS = {s.value for s in SkillID}
_VALID_DIRECTIONS = {"en_to_fr", "fr_to_en"}

_TAXONOMY_KEYS = {
    (s.primary_tag.value, s.error_type) for s in ERROR_TYPE_SPECS
}

_REQUIRED_FIELDS = (
    "codebook_id", "primary_tag", "error_type", "mqm_path",
    "severity_range", "tom_level", "primary_skill",
    "directions", "definition", "boundary_not", "examples",
)


def _check_entry(entry: dict, strict: bool, min_examples: int = 3) -> list[str]:
    """Return a list of validation problems for one entry. Empty = OK."""
    problems: list[str] = []

    for field in _REQUIRED_FIELDS:
        if field not in entry:
            problems.append(f"missing field: {field}")

    if entry.get("_stub") and strict:
        problems.append("entry is a stub (_stub: true); fill it in or run without --strict")

    tag = entry.get("primary_tag")
    if tag not in _VALID_TAGS:
        problems.append(f"primary_tag {tag!r} not in PrimaryTag enum")

    etype = entry.get("error_type")
    if tag and etype and (tag, etype) not in _TAXONOMY_KEYS:
        problems.append(f"({tag}, {etype}) is not in ERROR_TYPE_SPECS")

    tom = entry.get("tom_level")
    if tom not in _VALID_TOMS:
        problems.append(f"tom_level {tom!r} not in TOMLevel enum")

    skill = entry.get("primary_skill")
    if skill not in _VALID_SKILLS:
        problems.append(f"primary_skill {skill!r} not in SkillID enum")

    sev_range = entry.get("severity_range", [])
    if not sev_range:
        problems.append("severity_range is empty")
    for s in sev_range:
        if s not in _VALID_SEVERITIES:
            problems.append(f"severity {s!r} not in Severity enum")

    directions = entry.get("directions", [])
    for d in directions:
        if d not in _VALID_DIRECTIONS:
            problems.append(f"direction {d!r} not in {{en_to_fr, fr_to_en}}")

    definition = (entry.get("definition") or "").strip()
    if len(definition) < 20 or definition.startswith("TODO"):
        problems.append("definition is too short or unset (TODO placeholder)")

    boundary_not = (entry.get("boundary_not") or "").strip()
    if len(boundary_not) < 20 or boundary_not.startswith("TODO"):
        problems.append("boundary_not is too short or unset (TODO placeholder)")

    examples = entry.get("examples", [])
    if len(examples) < min_examples:
        problems.append(f"only {len(examples)} examples (need >={min_examples})")

    for i, ex in enumerate(examples):
        for field in ("source", "reference", "injected", "explanation"):
            if not ex.get(field):
                problems.append(f"example #{i + 1} missing {field}")
                continue
        explanation = ex.get("explanation", {})
        for field in ("mt_interpretation", "actual_meaning",
                      "reader_impact", "correction_rationale"):
            if not (explanation or {}).get(field):
                problems.append(f"example #{i + 1} explanation missing {field}")

        # Inline XML tag attributes should match the entry header
        injected = ex.get("injected", "")
        if tag and tag not in injected and "<error>" not in injected:
            problems.append(
                f"example #{i + 1} injected text has no <{tag}> or <error> tag"
            )

        # severity check on the inline tag (best-effort regex)
        m = re.search(r'severity="([^"]+)"', injected)
        if m and m.group(1) not in sev_range:
            problems.append(
                f"example #{i + 1} severity {m.group(1)!r} not in entry's "
                f"severity_range {sev_range}"
            )

    return problems


def validate_codebook(
    codebook_path: Path,
    strict: bool = False,
    min_examples: int = 3,
) -> int:
    if not codebook_path.exists():
        print(f"Codebook not found: {codebook_path}", file=sys.stderr)
        return 2

    with open(codebook_path, "r", encoding="utf-8") as f:
        cb = json.load(f)
    entries = cb.get("entries", [])
    if not entries:
        print(f"Codebook at {codebook_path} has no entries.", file=sys.stderr)
        return 2

    n_ok = 0
    n_fail = 0
    for entry in entries:
        problems = _check_entry(entry, strict=strict, min_examples=min_examples)
        eid = entry.get("codebook_id", "<no id>")
        if problems:
            n_fail += 1
            print(f"FAIL {eid} ({entry.get('primary_tag')}/{entry.get('error_type')})")
            for p in problems:
                print(f"      - {p}")
        else:
            n_ok += 1

    seen_keys = {(e.get("primary_tag"), e.get("error_type")) for e in entries}
    missing_from_taxonomy = sorted(_TAXONOMY_KEYS - seen_keys)
    if missing_from_taxonomy:
        print(
            f"\nCoverage: {len(seen_keys)} / {len(_TAXONOMY_KEYS)} "
            f"ERROR_TYPE_SPECS entries; missing:"
        )
        for tag, etype in missing_from_taxonomy:
            print(f"  - {tag} / {etype}")

    print(f"\n{n_ok} OK, {n_fail} FAIL.")
    return 0 if n_fail == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the codebook (remediation §8.1).",
    )
    parser.add_argument(
        "--codebook", type=Path, default=DEFAULT_CODEBOOK,
        help=f"Codebook to validate (default: {DEFAULT_CODEBOOK.relative_to(PROJECT_ROOT)}).",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Also fail entries flagged with `_stub: true`.",
    )
    parser.add_argument(
        "--min-examples", type=int, default=3,
        help="Minimum required examples per entry (default: 3, matches spec target).",
    )
    args = parser.parse_args()

    code = validate_codebook(
        args.codebook, strict=args.strict, min_examples=args.min_examples,
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
