"""Prompts and schemas for L0 false-annotation generation.

False annotations are decoy MQM annotations attached to L0 (Navigator) items so
that students must Confirm or Dispute each pre-annotation. They drive the
Trap Detector behaviour badge (correct dispute count).

Design constraint: false annotations must look *plausible* (a tempting wrong
answer) but must not overlap any real injected error in the same item.
"""

from __future__ import annotations


SYSTEM_PROMPT = """You are an expert MQM annotator generating *plausible-but-incorrect* annotations for a pedagogical post-editing exercise. The student will see your annotations alongside real annotations and must decide which to confirm and which to dispute.

Your goal: produce annotations that a reasonable but inexperienced student might believe are real errors, but that an expert would reject.

Constraints:
- Each annotation must point to a span that *exists in the translation text* — copy the exact substring.
- Do NOT overlap any character range that a real error already occupies (the user supplies excluded ranges).
- Choose error categories where the surface form looks suspect (uncommon word choice, awkward phrasing, archaic punctuation) but the meaning is preserved.
- Severity should be plausible: most decoys should be "minor" or "major"; "critical" decoys are obvious and rarely useful.
- Avoid trivial picks (one-letter spans, whitespace).

Output JSON schema (one object per decoy):
{
  "span_text": "<exact substring from the translation>",
  "span_start": <int char offset where this substring starts in the translation>,
  "span_end": <int char offset where it ends, exclusive>,
  "primary_tag": "<one of MISTRANSLATION|OMISSION|ADDITION|UNTRANSLATED|GRAMMAR|TERMINOLOGY|STYLE|LOCALE|SPELLING|PUNCTUATION>",
  "severity": "<minor|major|critical>",
  "plausible_reasoning": "<one sentence describing why this might *look* like an error>"
}
"""


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decoys": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span_text": {"type": "string"},
                    "span_start": {"type": "integer"},
                    "span_end": {"type": "integer"},
                    "primary_tag": {
                        "type": "string",
                        "enum": [
                            "MISTRANSLATION", "OMISSION", "ADDITION",
                            "UNTRANSLATED", "GRAMMAR", "TERMINOLOGY",
                            "STYLE", "LOCALE", "SPELLING", "PUNCTUATION",
                        ],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["minor", "major", "critical"],
                    },
                    "plausible_reasoning": {"type": "string"},
                },
                "required": [
                    "span_text", "span_start", "span_end",
                    "primary_tag", "severity", "plausible_reasoning",
                ],
            },
        },
    },
    "required": ["decoys"],
}


def build_user_prompt(
    source_text: str,
    translation: str,
    excluded_ranges: list[tuple[int, int]],
    n_decoys: int,
) -> str:
    """Build the user message for decoy generation.

    excluded_ranges: list of (start, end) character ranges occupied by *real*
    errors; decoys must not overlap these.
    """
    excluded_str = ", ".join(f"[{a},{b})" for a, b in excluded_ranges) or "(none)"
    return (
        f"SOURCE:\n{source_text}\n\n"
        f"TRANSLATION:\n{translation}\n\n"
        f"EXCLUDED RANGES (do not overlap any of these):\n{excluded_str}\n\n"
        f"Produce exactly {n_decoys} plausible-but-incorrect MQM annotation(s) "
        f"on the translation. Return JSON conforming to the schema."
    )
