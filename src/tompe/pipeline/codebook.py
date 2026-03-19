"""Codebook loader and query functions for the error injection pipeline.

The codebook (`data/codebook/error_codebook_fr_en.json`) stores structured
entries with definitions, boundary conditions, and few-shot examples for
each error type. It drives the injection prompts and provides ICL material.

The tag schema (`data/codebook/tag_schema.json`) defines the valid tag
inventory for injection output validation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CodebookExplanation(BaseModel):
    """Explanation fields within a codebook example."""

    mt_interpretation: str
    actual_meaning: str
    reader_impact: str
    correction_rationale: str


class CodebookExample(BaseModel):
    """A single few-shot example within a codebook entry."""

    direction: str  # "fr_to_en" or "en_to_fr"
    source: str
    reference: str
    injected: str  # Contains inline XML tags
    explanation: CodebookExplanation


class CodebookEntry(BaseModel):
    """A single entry in the error codebook. From spec v1.1 §5.1."""

    codebook_id: str
    primary_tag: str  # e.g., "MISTRANSLATION"
    error_type: str  # e.g., "false_cognate"
    mqm_path: str  # e.g., "Accuracy > Mistranslation > False Friend"
    severity_range: list[str]  # e.g., ["major", "critical"]
    tom_level: str  # e.g., "1st_machine"
    primary_skill: str  # e.g., "S3"
    secondary_skills: list[str] = []
    definition: str
    boundary_not: str  # What this error is NOT (disambiguation)
    directions: list[str]  # e.g., ["fr_to_en", "en_to_fr"]
    examples: list[CodebookExample]


class TagSchema(BaseModel):
    """Tag inventory schema for validation."""

    version: str
    description: str
    primary_tags: dict[str, dict]  # tag_name -> {mqm_dimension, types}
    severity_levels: list[str]
    tom_levels: list[str]


class Codebook:
    """Loaded codebook with query methods."""

    def __init__(self, entries: list[CodebookEntry], tag_schema: Optional[TagSchema] = None):
        self.entries = entries
        self.tag_schema = tag_schema

        # Build indices
        self._by_tag: dict[str, list[CodebookEntry]] = {}
        self._by_tag_type: dict[tuple[str, str], CodebookEntry] = {}
        for entry in entries:
            self._by_tag.setdefault(entry.primary_tag, []).append(entry)
            self._by_tag_type[(entry.primary_tag, entry.error_type)] = entry

    def get_entry(self, primary_tag: str, error_type: str) -> Optional[CodebookEntry]:
        """Get a specific codebook entry by tag and type."""
        return self._by_tag_type.get((primary_tag, error_type))

    def get_entries_by_tag(self, primary_tag: str) -> list[CodebookEntry]:
        """Get all codebook entries for a primary tag."""
        return self._by_tag.get(primary_tag, [])

    def get_few_shot_examples(
        self,
        primary_tag: str,
        error_type: str,
        direction: Optional[str] = None,
        n: int = 3,
    ) -> list[CodebookExample]:
        """Get few-shot examples for a specific error type.

        Args:
            primary_tag: The primary tag (e.g., "MISTRANSLATION").
            error_type: The error type (e.g., "false_cognate").
            direction: Optional filter — "fr_to_en" or "en_to_fr".
            n: Maximum number of examples to return.

        Returns:
            List of CodebookExample objects.
        """
        entry = self.get_entry(primary_tag, error_type)
        if entry is None:
            # Fall back to any examples from the same tag
            entries = self.get_entries_by_tag(primary_tag)
            examples = []
            for e in entries:
                examples.extend(e.examples)
            if direction:
                examples = [ex for ex in examples if ex.direction == direction]
            return examples[:n]

        examples = entry.examples
        if direction:
            examples = [ex for ex in examples if ex.direction == direction]
        return examples[:n]

    def get_definition(self, primary_tag: str, error_type: str) -> str:
        """Get the definition for an error type."""
        entry = self.get_entry(primary_tag, error_type)
        return entry.definition if entry else ""

    def get_boundary_not(self, primary_tag: str, error_type: str) -> str:
        """Get the boundary/disambiguation text for an error type."""
        entry = self.get_entry(primary_tag, error_type)
        return entry.boundary_not if entry else ""

    def validate_tag_type(self, primary_tag: str, error_type: str) -> bool:
        """Validate a (tag, type) pair against the tag schema."""
        if self.tag_schema is None:
            return True  # No schema loaded, skip validation
        tag_info = self.tag_schema.primary_tags.get(primary_tag)
        if tag_info is None:
            return False
        return error_type in tag_info.get("types", [])

    @property
    def all_tags(self) -> list[str]:
        """Get all primary tags that have codebook entries."""
        return list(self._by_tag.keys())

    @property
    def entry_count(self) -> int:
        """Get total number of codebook entries."""
        return len(self.entries)

    @property
    def example_count(self) -> int:
        """Get total number of examples across all entries."""
        return sum(len(e.examples) for e in self.entries)


def load_codebook(
    codebook_path: str | Path,
    tag_schema_path: Optional[str | Path] = None,
) -> Codebook:
    """Load the codebook and optionally the tag schema from JSON files.

    Args:
        codebook_path: Path to error_codebook_fr_en.json.
        tag_schema_path: Optional path to tag_schema.json.

    Returns:
        A Codebook instance with all entries loaded and indexed.
    """
    codebook_path = Path(codebook_path)
    if not codebook_path.exists():
        logger.warning("Codebook not found at %s, returning empty codebook", codebook_path)
        return Codebook(entries=[])

    with open(codebook_path, encoding="utf-8") as f:
        data = json.load(f)

    entries = [CodebookEntry(**entry) for entry in data.get("entries", [])]
    logger.info("Loaded codebook with %d entries from %s", len(entries), codebook_path)

    tag_schema = None
    if tag_schema_path:
        tag_schema_path = Path(tag_schema_path)
        if tag_schema_path.exists():
            with open(tag_schema_path, encoding="utf-8") as f:
                schema_data = json.load(f)
            tag_schema = TagSchema(**schema_data)
            logger.info("Loaded tag schema from %s", tag_schema_path)

    return Codebook(entries=entries, tag_schema=tag_schema)


def load_default_codebook() -> Codebook:
    """Load the codebook from the default project paths.

    Looks for files relative to the project root (data/codebook/).
    """
    # Walk up from this file to find the project root
    current = Path(__file__).resolve()
    # src/tompe/pipeline/codebook.py → project root is 3 levels up
    project_root = current.parent.parent.parent.parent

    codebook_path = project_root / "data" / "codebook" / "error_codebook_fr_en.json"
    schema_path = project_root / "data" / "codebook" / "tag_schema.json"

    return load_codebook(
        codebook_path=codebook_path,
        tag_schema_path=schema_path if schema_path.exists() else None,
    )
