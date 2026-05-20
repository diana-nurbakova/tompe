"""Ingest parallel corpora from teacher-uploaded files.

Supports two upload formats:

* **TMX** (Translation Memory Exchange XML) — segments live inside `<tu>` units
  with one `<tuv xml:lang="...">` child per language. We match the requested
  source/target language codes case-insensitively, so `EN`/`en-US`/`en` all line
  up with `en`.
* **TSV** — one segment per line, columns separated by a single tab:
  `source\\ttarget`. Lines with the wrong column count or empty cells are
  skipped (with a per-line warning surfaced by the caller).

Output: a list of dicts shaped to match the existing
`data/corpora/{origin}/segments_en_fr.jsonl` schema (see `segment_selector.load_corpus`).
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional


def _segment_id(origin: str, source_text: str, idx: int) -> str:
    """Stable per-segment id: `{origin}-{12-hex hash of (idx + source)}`."""
    digest = hashlib.sha256(f"{idx}:{source_text}".encode("utf-8")).hexdigest()[:12]
    return f"{origin}-{digest}"


def _lang_matches(tuv_lang: str, want: str) -> bool:
    """TMX language codes can be `en`, `EN`, `en-US`, etc. — match leading part."""
    if not tuv_lang:
        return False
    head = re.split(r"[-_]", tuv_lang.lower(), maxsplit=1)[0]
    return head == want.lower()


def parse_tmx(
    tmx_text: str,
    source_lang: str,
    target_lang: str,
    corpus_origin: str,
    domain: str = "general",
    register: Optional[str] = None,
) -> list[dict]:
    """Parse a TMX document into corpus segment dicts.

    Strips XML namespaces so attribute lookups don't need to know the TMX
    version. Skips translation units missing either language.
    """
    # Strip namespaces — TMX 1.4b uses xmlns but the schema is fixed
    cleaned = re.sub(r'\sxmlns(:[^=]+)?="[^"]*"', "", tmx_text, count=0)
    root = ET.fromstring(cleaned)

    segments: list[dict] = []
    for idx, tu in enumerate(root.iter("tu")):
        src_text: Optional[str] = None
        tgt_text: Optional[str] = None
        for tuv in tu.findall("tuv"):
            lang = (
                tuv.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                or tuv.attrib.get("xml:lang")
                or tuv.attrib.get("lang")
                or ""
            )
            seg = tuv.find("seg")
            if seg is None:
                continue
            # `itertext` keeps inline tags' text content
            text = "".join(seg.itertext()).strip()
            if not text:
                continue
            if _lang_matches(lang, source_lang) and src_text is None:
                src_text = text
            elif _lang_matches(lang, target_lang) and tgt_text is None:
                tgt_text = text
        if src_text and tgt_text:
            entry = {
                "segment_id": _segment_id(corpus_origin, src_text, idx),
                "source_text": src_text,
                "reference_translation": tgt_text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "corpus_origin": corpus_origin,
                "domain": domain,
                "position_in_doc": idx,
            }
            if register:
                entry["register"] = register
            segments.append(entry)
    return segments


def parse_tsv(
    tsv_text: str,
    source_lang: str,
    target_lang: str,
    corpus_origin: str,
    domain: str = "general",
    register: Optional[str] = None,
) -> tuple[list[dict], list[str]]:
    """Parse a tab-separated `source\\ttarget` file.

    Returns (segments, warnings). Lines with the wrong column count or empty
    cells appear as per-line warnings (1-indexed) so the caller can surface
    them in the UI without aborting the whole ingest.
    """
    segments: list[dict] = []
    warnings: list[str] = []
    for lineno, raw in enumerate(tsv_text.splitlines(), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            warnings.append(f"line {lineno}: expected 2 tab-separated columns, got {len(parts)} — skipped")
            continue
        if len(parts) > 2:
            # Allow extra columns but only use the first two
            warnings.append(f"line {lineno}: {len(parts)} columns — using only the first two")
        src = parts[0].strip()
        tgt = parts[1].strip()
        if not src or not tgt:
            warnings.append(f"line {lineno}: empty source or target — skipped")
            continue
        entry = {
            "segment_id": _segment_id(corpus_origin, src, lineno),
            "source_text": src,
            "reference_translation": tgt,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "corpus_origin": corpus_origin,
            "domain": domain,
            "position_in_doc": lineno - 1,
        }
        if register:
            entry["register"] = register
        segments.append(entry)
    return segments, warnings


def write_segments(
    corpus_dir: Path,
    corpus_origin: str,
    segments: Iterable[dict],
    *,
    append: bool = False,
) -> Path:
    """Write segments to `{corpus_dir}/{corpus_origin}/segments_en_fr.jsonl`.

    Creates the per-corpus directory if missing. Returns the JSONL path so
    callers can show it in the UI.
    """
    out_dir = corpus_dir / corpus_origin
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "segments_en_fr.jsonl"
    mode = "a" if append else "w"
    with open(out_path, mode, encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg, ensure_ascii=False) + "\n")
    return out_path
