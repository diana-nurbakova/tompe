"""Scaffold missing codebook entries from the taxonomy.

Reads ``ERROR_TYPE_SPECS`` (42 entries) and the existing
``data/codebook/error_codebook_fr_en.json`` (currently 8 entries),
emits stub JSON entries for every ``(primary_tag, error_type)`` pair
present in the taxonomy but missing from the codebook.

Each stub carries:

  - codebook_id     (auto-generated, deterministic per pair)
  - primary_tag, error_type, mqm_path, severity_range, tom_level,
    primary_skill, secondary_skills, directions
                    (sourced from the taxonomy — researcher does not need to touch)
  - definition      "TODO: …" placeholder (~50 words target)
  - boundary_not    "TODO: …" placeholder (~30 words target)
  - examples        []  (researcher fills in ≥3)
  - _stub           true  (marker so the validator can flag unfilled entries)

The scaffold output is written to
``data/codebook/error_codebook_fr_en.stubs.json`` by default — a
sibling file that the researcher reviews, fills in, and then merges
into the main codebook. The main codebook is never touched by this
script.

Usage:

    python scripts/scaffold_codebook_entries.py
    python scripts/scaffold_codebook_entries.py --output path.json
    python scripts/scaffold_codebook_entries.py --list-missing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tompe.pipeline.mqm_taxonomy import ERROR_TYPE_SPECS  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_CODEBOOK = PROJECT_ROOT / "data" / "codebook" / "error_codebook_fr_en.json"
DEFAULT_STUBS = PROJECT_ROOT / "data" / "codebook" / "error_codebook_fr_en.stubs.json"


# ── ID generation ───────────────────────────────────────────────────────────

# Primary-tag → MQM dimension prefix (3 chars, matches existing IDs).
_TAG_TO_DIMENSION_PREFIX: dict[str, str] = {
    "MISTRANSLATION": "ACC",
    "OMISSION": "ACC",
    "ADDITION": "ACC",
    "UNTRANSLATED": "ACC",
    "GRAMMAR": "FLU",
    "SPELLING": "FLU",
    "PUNCTUATION": "FLU",
    "TERMINOLOGY": "TRM",
    "STYLE": "STY",
    "LOCALE": "LOC",
}

# Short tag code (4 chars, matches existing IDs where present).
_TAG_TO_SHORT: dict[str, str] = {
    "MISTRANSLATION": "MIST",
    "OMISSION": "OMIS",
    "ADDITION": "ADDI",
    "UNTRANSLATED": "UNTR",
    "GRAMMAR": "GRAM",
    "SPELLING": "SPEL",
    "PUNCTUATION": "PUNC",
    "TERMINOLOGY": "INC",
    "STYLE": "AWK",
    "LOCALE": "FMT",
}


def _error_type_initials(error_type: str) -> str:
    """Build a short 2–3-letter code from snake_case error_type."""
    parts = error_type.split("_")
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "".join(p[0] for p in parts).upper()


def _build_codebook_id(primary_tag: str, error_type: str) -> str:
    dim = _TAG_TO_DIMENSION_PREFIX.get(primary_tag, "GEN")
    tag = _TAG_TO_SHORT.get(primary_tag, primary_tag[:4])
    code = _error_type_initials(error_type)
    return f"{dim}-{tag}-{code}-001"


def _build_mqm_path(primary_tag: str, error_type: str) -> str:
    """Render a human-readable MQM path like 'Accuracy > Mistranslation > Word Sense'."""
    dim_label = {
        "MISTRANSLATION": "Accuracy",
        "OMISSION": "Accuracy",
        "ADDITION": "Accuracy",
        "UNTRANSLATED": "Accuracy",
        "GRAMMAR": "Linguistic conventions",
        "SPELLING": "Linguistic conventions",
        "PUNCTUATION": "Linguistic conventions",
        "TERMINOLOGY": "Terminology",
        "STYLE": "Style",
        "LOCALE": "Locale conventions",
    }.get(primary_tag, "Accuracy")
    tag_label = primary_tag.replace("_", " ").title()
    type_label = error_type.replace("_", " ").title()
    return f"{dim_label} > {tag_label} > {type_label}"


def _direction_to_codebook(taxonomy_direction: str) -> list[str]:
    """Map ``"both" | "en_fr" | "fr_en"`` to codebook ``directions[]``."""
    if taxonomy_direction == "both":
        return ["en_to_fr", "fr_to_en"]
    if taxonomy_direction == "en_fr":
        return ["en_to_fr"]
    if taxonomy_direction == "fr_en":
        return ["fr_to_en"]
    return ["en_to_fr", "fr_to_en"]


# ── Scaffold + I/O ──────────────────────────────────────────────────────────


def load_existing_keys(codebook_path: Path) -> set[tuple[str, str]]:
    if not codebook_path.exists():
        return set()
    with open(codebook_path, "r", encoding="utf-8") as f:
        cb = json.load(f)
    return {(e["primary_tag"], e["error_type"]) for e in cb.get("entries", [])}


def build_stub(primary_tag: str, error_type: str) -> dict:
    """Build a single stub entry from the taxonomy."""
    spec = next(
        s for s in ERROR_TYPE_SPECS
        if s.primary_tag.value == primary_tag and s.error_type == error_type
    )
    return {
        "codebook_id": _build_codebook_id(primary_tag, error_type),
        "primary_tag": primary_tag,
        "error_type": error_type,
        "mqm_path": _build_mqm_path(primary_tag, error_type),
        "severity_range": [s.value for s in spec.severity_range],
        "tom_level": spec.tom_level.value,
        "primary_skill": spec.primary_skill.value,
        "secondary_skills": [s.value for s in spec.secondary_skills],
        "directions": _direction_to_codebook(spec.direction),
        "definition": (
            "TODO: ~50-word definition. Explain what this error type is "
            "and the MT/LLM mechanism that typically produces it. Reference "
            "existing entries (e.g. ACC-MIST-FC-001) for tone + length."
        ),
        "boundary_not": (
            "TODO: ~30 words on what this error is NOT. Disambiguate against "
            "the most likely sibling types."
        ),
        "examples": [],
        "_stub": True,
    }


def scaffold_missing(
    codebook_path: Path,
    output_path: Path,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Generate stubs for every missing (tag, error_type) pair.

    Returns (stub_entries, missing_pairs).
    """
    existing = load_existing_keys(codebook_path)
    missing: list[tuple[str, str]] = []
    stubs: list[dict] = []
    for spec in ERROR_TYPE_SPECS:
        key = (spec.primary_tag.value, spec.error_type)
        if key in existing:
            continue
        missing.append(key)
        stubs.append(build_stub(*key))

    payload = {
        "version": "stub",
        "language_pair": "en_fr",
        "_doc": (
            "Stub codebook entries scaffolded from ERROR_TYPE_SPECS. "
            "Each entry needs `definition`, `boundary_not`, and ≥3 "
            "`examples` filled in before merging into the main codebook. "
            "Drop the `_stub: true` flag once content is reviewed."
        ),
        "entries": stubs,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return stubs, missing


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Scaffold missing codebook entries from ERROR_TYPE_SPECS.",
    )
    parser.add_argument(
        "--codebook", type=Path, default=DEFAULT_CODEBOOK,
        help=f"Existing codebook (default: {DEFAULT_CODEBOOK.relative_to(PROJECT_ROOT)}).",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_STUBS,
        help=f"Output stubs file (default: {DEFAULT_STUBS.relative_to(PROJECT_ROOT)}).",
    )
    parser.add_argument(
        "--list-missing", action="store_true",
        help="Just print the missing (tag, error_type) pairs and exit.",
    )
    args = parser.parse_args()

    existing = load_existing_keys(args.codebook)
    missing = [
        (s.primary_tag.value, s.error_type)
        for s in ERROR_TYPE_SPECS
        if (s.primary_tag.value, s.error_type) not in existing
    ]

    if args.list_missing:
        print(f"Codebook coverage: {len(existing)} / {len(ERROR_TYPE_SPECS)} taxonomy entries.")
        print(f"Missing: {len(missing)} pair(s):")
        for tag, etype in missing:
            print(f"  {tag} / {etype}")
        return

    stubs, _ = scaffold_missing(args.codebook, args.output)
    print(
        f"Wrote {len(stubs)} stub entries to {args.output}.\n"
        f"  Coverage: {len(existing)} done, {len(missing)} missing "
        f"({len(existing)}/{len(ERROR_TYPE_SPECS)}).\n"
        "Fill in `definition`, `boundary_not`, and >=3 `examples` per stub, "
        "drop the `_stub` flag, and merge into the main codebook."
    )


if __name__ == "__main__":
    main()
