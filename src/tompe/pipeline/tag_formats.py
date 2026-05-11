"""Tag format definitions for the C1–C4 tagging ablation (spec §5.5).

Four tag formats, progressively richer:

  - **C1 Bare:**        ``<error>span</error>``
  - **C2 Categorical:** ``<MISTRANSLATION>span</MISTRANSLATION>``
  - **C3 Attributed:**  ``<MISTRANSLATION type="false_cognate" severity="major">span</MISTRANSLATION>``
  - **C4 Full:**        ``<MISTRANSLATION type="..." severity="..." tom="..." desc="...">span</MISTRANSLATION>``

Production code paths default to C4. The ablation runner
(``experiments/ablation_tagging.py``) sweeps all four to measure the
effect of format complexity on injection compliance and
GEMBA-detectability of injected errors.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Pattern

from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel


class TagFormat(str, Enum):
    """The four tagging-strategy conditions from spec §5.5."""

    C1_BARE = "C1"
    C2_CATEGORICAL = "C2"
    C3_ATTRIBUTED = "C3"
    C4_FULL = "C4"


# Compiled regexes. All patterns expose a ``span_text`` group; richer
# formats additionally expose ``type``, ``severity``, ``tom``, ``desc``.
_TAG_PATTERNS: dict[TagFormat, Pattern[str]] = {
    TagFormat.C1_BARE: re.compile(
        r'<(?P<tag_name>error)>(?P<span_text>.*?)</error>',
        re.DOTALL,
    ),
    TagFormat.C2_CATEGORICAL: re.compile(
        r'<(?P<tag_name>[A-Z_]+)>(?P<span_text>.*?)</(?P=tag_name)>',
        re.DOTALL,
    ),
    TagFormat.C3_ATTRIBUTED: re.compile(
        r'<(?P<tag_name>[A-Z_]+)\s+type="(?P<type>[^"]+)"'
        r'\s+severity="(?P<severity>[^"]+)">'
        r'(?P<span_text>.*?)</(?P=tag_name)>',
        re.DOTALL,
    ),
    TagFormat.C4_FULL: re.compile(
        r'<(?P<tag_name>[A-Z_]+)\s+type="(?P<type>[^"]+)"'
        r'\s+severity="(?P<severity>[^"]+)"'
        r'\s+tom="(?P<tom>[^"]+)"'
        r'\s+desc="(?P<desc>[^"]*)">'
        r'(?P<span_text>.*?)</(?P=tag_name)>',
        re.DOTALL,
    ),
}


def get_tag_pattern(fmt: TagFormat) -> Pattern[str]:
    """Return the compiled regex for the given tag format."""
    return _TAG_PATTERNS[fmt]


def parse_tags(injected_text: str, fmt: TagFormat) -> list[dict]:
    """Parse all matching tags from ``injected_text``.

    Returns a list of dicts with at minimum ``tag_name`` and
    ``span_text``; richer formats also populate ``type``, ``severity``,
    ``tom``, and ``desc``. Missing fields default to ``""``.
    ``match_start`` / ``match_end`` are character offsets into the
    original text.
    """
    pattern = _TAG_PATTERNS[fmt]
    out: list[dict] = []
    for m in pattern.finditer(injected_text):
        d = m.groupdict()
        d["match_start"] = m.start()
        d["match_end"] = m.end()
        d.setdefault("type", "")
        d.setdefault("severity", "")
        d.setdefault("tom", "")
        d.setdefault("desc", "")
        out.append(d)
    return out


def strip_tags(injected_text: str, fmt: TagFormat) -> str:
    """Remove all tags of the given format, keeping the span content."""
    return _TAG_PATTERNS[fmt].sub(lambda m: m.group("span_text"), injected_text)


def render_tag(
    primary_tag: PrimaryTag,
    error_type: str,
    severity: Severity,
    tom_level: TOMLevel,
    desc: str,
    span_text: str,
    fmt: TagFormat,
) -> str:
    """Render a single XML error tag in the given format."""
    if fmt == TagFormat.C1_BARE:
        return f'<error>{span_text}</error>'
    if fmt == TagFormat.C2_CATEGORICAL:
        return f'<{primary_tag.value}>{span_text}</{primary_tag.value}>'
    if fmt == TagFormat.C3_ATTRIBUTED:
        return (
            f'<{primary_tag.value} type="{error_type}" '
            f'severity="{severity.value}">{span_text}'
            f'</{primary_tag.value}>'
        )
    # C4_FULL
    return (
        f'<{primary_tag.value} type="{error_type}" '
        f'severity="{severity.value}" tom="{tom_level.value}" '
        f'desc="{desc}">{span_text}'
        f'</{primary_tag.value}>'
    )


def reformat_codebook_xml(c4_xml_text: str, target: TagFormat) -> str:
    """Re-render a C4-formatted example string in the target format.

    Codebook examples are authored in C4; few-shot prompts for C1–C3
    runs need to show examples in the matching simpler format, so the
    LLM's task is "produce this format" without a format mismatch
    between examples and instructions.
    """
    if target == TagFormat.C4_FULL:
        return c4_xml_text

    c4_pattern = _TAG_PATTERNS[TagFormat.C4_FULL]

    def _replace(m: re.Match[str]) -> str:
        try:
            primary_tag = PrimaryTag(m.group("tag_name"))
            severity = Severity(m.group("severity"))
            tom_level = TOMLevel(m.group("tom"))
        except ValueError:
            # Malformed example — keep the original C4 string rather
            # than crash; the prompt will still be usable.
            return m.group(0)
        return render_tag(
            primary_tag=primary_tag,
            error_type=m.group("type"),
            severity=severity,
            tom_level=tom_level,
            desc=m.group("desc"),
            span_text=m.group("span_text"),
            fmt=target,
        )

    return c4_pattern.sub(_replace, c4_xml_text)


def tag_template_string(
    primary_tag: PrimaryTag,
    error_type: str,
    severity: Severity,
    tom_level: TOMLevel,
    fmt: TagFormat,
) -> str:
    """Render the "use this tag template" instruction line for the LLM.

    Differs from `render_tag` in that it uses placeholder span text
    suitable for an instruction (``error text``) and shows the structure
    rather than a real example.
    """
    placeholder = "error text"
    if fmt == TagFormat.C1_BARE:
        return f"<error>{placeholder}</error>"
    if fmt == TagFormat.C2_CATEGORICAL:
        return f"<{primary_tag.value}>{placeholder}</{primary_tag.value}>"
    if fmt == TagFormat.C3_ATTRIBUTED:
        return (
            f'<{primary_tag.value} type="{error_type}" '
            f'severity="{severity.value}">{placeholder}'
            f'</{primary_tag.value}>'
        )
    return (
        f'<{primary_tag.value} type="{error_type}" '
        f'severity="{severity.value}" tom="{tom_level.value}" '
        f'desc="5-15 word explanation">{placeholder}'
        f'</{primary_tag.value}>'
    )
