"""Corpus ingestion script.

Downloads EN-FR parallel segments from EU/UN corpora via OPUS (using
opustools) and stores them as JSONL files with document IDs and
positional ordering for the segment selector pipeline stage.

Document structure is preserved: each segment includes ``document_id``
(original OPUS filename) and ``position_in_doc`` (0-based sentence
position within that document).  This enables multi-sentence context
windows for L3 (recursive/discourse) error injection.

Usage:
    python scripts/ingest_corpus.py                          # all corpora, 10k segments each
    python scripts/ingest_corpus.py --corpus europarl        # single corpus
    python scripts/ingest_corpus.py --max-segments 500       # small sample
    python scripts/ingest_corpus.py --list                   # show available corpora info

Requirements:
    pip install opustools
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import uuid
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Corpus configuration ────────────────────────────────────────────────────

CORPORA = {
    "europarl": {
        "opus_name": "Europarl",
        "version": "v8",
        "domain": "parliamentary",
        "register": "semi-formal",
        "description": "European Parliament proceedings",
    },
    "dgt_tm": {
        "opus_name": "DGT",
        "version": "v2019",
        "domain": "legal",
        "register": "formal",
        "description": "EU Directorate-General for Translation memory",
    },
    "eurlex": {
        "opus_name": "EUbookshop",
        "version": "v2",
        "domain": "legal",
        "register": "formal",
        "description": "EU legislation and bookshop publications",
    },
    "unpc": {
        "opus_name": "UNPC",
        "version": "v1.0",
        "domain": "institutional",
        "register": "formal",
        "description": "United Nations Parallel Corpus",
    },
}

# ── Project paths ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPORA_DIR = PROJECT_ROOT / "data" / "corpora"
CACHE_DIR = CORPORA_DIR / "_cache"

# ── Document boundary tags in OPUS Moses output ────────────────────────────

_FROM_DOC_RE = re.compile(r"<fromDoc>(.*?)</fromDoc>")
_TO_DOC_RE = re.compile(r"<toDoc>(.*?)</toDoc>")


def _extract_with_opustools(
    corpus_key: str,
    max_segments: int,
    source_lang: str,
    target_lang: str,
) -> list[dict]:
    """Use opustools to extract aligned pairs with document IDs.

    OpusRead in moses write mode outputs:
    - ``<fromDoc>en/filename.xml.gz</fromDoc>`` before each document
    - Empty lines between documents
    - One sentence per line (aligned by position)
    """
    from opustools import OpusRead

    corpus_cfg = CORPORA[corpus_key]
    cache_dir = CACHE_DIR / corpus_key
    cache_dir.mkdir(parents=True, exist_ok=True)

    src_file = cache_dir / "src_moses.txt"
    trg_file = cache_dir / "trg_moses.txt"

    log.info(
        "Extracting %s (OPUS: %s %s) via opustools, max %d segments...",
        corpus_key, corpus_cfg["opus_name"], corpus_cfg["version"], max_segments,
    )

    reader = OpusRead(
        directory=corpus_cfg["opus_name"],
        source=source_lang,
        target=target_lang,
        release=corpus_cfg["version"],
        preprocess="xml",
        maximum=max_segments,
        print_file_names=True,
        download_dir=str(cache_dir),
        suppress_prompts=True,
        write=[str(src_file), str(trg_file)],
        write_mode="moses",
    )
    reader.printPairs()

    # Parse the Moses output files, tracking document boundaries
    segments: list[dict] = []

    src_lines = src_file.read_text(encoding="utf-8").splitlines()
    trg_lines = trg_file.read_text(encoding="utf-8").splitlines()

    current_doc_id: str | None = None
    position_in_doc = 0
    src_idx = 0
    trg_idx = 0

    while src_idx < len(src_lines) and trg_idx < len(trg_lines):
        src_line = src_lines[src_idx]
        trg_line = trg_lines[trg_idx]

        # Check for document boundary tag
        src_doc_match = _FROM_DOC_RE.search(src_line)
        trg_doc_match = _TO_DOC_RE.search(trg_line)

        if src_doc_match:
            current_doc_id = src_doc_match.group(1)
            # Strip path prefix (e.g., "en/ep-00-01-17.xml.gz" -> "ep-00-01-17")
            current_doc_id = (
                current_doc_id.rsplit("/", 1)[-1]
                .replace(".xml.gz", "")
                .replace(".xml", "")
            )
            position_in_doc = 0
            src_idx += 1
            trg_idx += 1
            continue

        if trg_doc_match and not src_doc_match:
            # Target has doc tag but source doesn't — skip target line
            trg_idx += 1
            continue

        # Skip empty lines (document boundaries in Moses format)
        if not src_line.strip() or not trg_line.strip():
            src_idx += 1
            trg_idx += 1
            continue

        src_text = src_line.strip()
        trg_text = trg_line.strip()

        if src_text and trg_text:
            segment = {
                "segment_id": f"{corpus_key}-{uuid.uuid4().hex[:12]}",
                "source_text": src_text,
                "reference_translation": trg_text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "corpus_origin": corpus_key,
                "domain": corpus_cfg["domain"],
                "register": corpus_cfg["register"],
                "document_id": current_doc_id,
                "position_in_doc": position_in_doc,
            }
            segments.append(segment)
            position_in_doc += 1

        src_idx += 1
        trg_idx += 1

    # Clean up temporary files
    src_file.unlink(missing_ok=True)
    trg_file.unlink(missing_ok=True)

    return segments


def download_and_extract(
    corpus_key: str,
    max_segments: int = 10_000,
    source_lang: str = "en",
    target_lang: str = "fr",
) -> Path:
    """Download from OPUS via opustools, extract pairs with document IDs, write JSONL.

    Returns the path to the output JSONL file.
    """
    output_dir = CORPORA_DIR / corpus_key
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"segments_{source_lang}_{target_lang}.jsonl"

    segments = _extract_with_opustools(
        corpus_key, max_segments, source_lang, target_lang,
    )
    log.info("Extracted %d aligned pairs from %s", len(segments), corpus_key)

    # Count documents
    doc_ids = {s["document_id"] for s in segments if s["document_id"]}
    log.info("  Documents: %d unique", len(doc_ids))

    # Write JSONL
    with open(output_file, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg, ensure_ascii=False) + "\n")

    log.info("Wrote %d segments to %s", len(segments), output_file)
    return output_file


def list_corpora():
    """Print info about available corpora."""
    print("\nAvailable corpora for ingestion:\n")
    print(f"  {'Key':<12} {'OPUS Name':<15} {'Domain':<15} {'Register':<12} Description")
    print(f"  {'-'*12} {'-'*15} {'-'*15} {'-'*12} {'-'*30}")
    for key, cfg in CORPORA.items():
        print(
            f"  {key:<12} {cfg['opus_name']:<15} {cfg['domain']:<15} "
            f"{cfg['register']:<12} {cfg['description']}"
        )

    # Check existing downloads
    print("\nExisting downloads:\n")
    for key in CORPORA:
        jsonl = CORPORA_DIR / key / "segments_en_fr.jsonl"
        if jsonl.exists():
            n_lines = sum(1 for _ in open(jsonl, encoding="utf-8"))
            # Check if document_id field exists
            with open(jsonl, encoding="utf-8") as f:
                first = json.loads(f.readline())
            has_doc = "document_id" in first and first["document_id"] is not None
            doc_info = " (with doc IDs)" if has_doc else " (no doc IDs)"
            size_mb = jsonl.stat().st_size / (1024 * 1024)
            print(f"  {key:<12} {n_lines:>8,} segments  ({size_mb:.1f} MB){doc_info}")
        else:
            print(f"  {key:<12} not downloaded")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Download EU/UN parallel corpora from OPUS for ToM-PE."
    )
    parser.add_argument(
        "--corpus",
        choices=list(CORPORA.keys()),
        help="Download a single corpus (default: all)",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=10_000,
        help="Max segments to extract per corpus (default: 10000)",
    )
    parser.add_argument(
        "--source-lang",
        default="en",
        help="Source language (default: en)",
    )
    parser.add_argument(
        "--target-lang",
        default="fr",
        help="Target language (default: fr)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available corpora and exit",
    )
    args = parser.parse_args()

    if args.list:
        list_corpora()
        return

    targets = [args.corpus] if args.corpus else list(CORPORA.keys())

    log.info(
        "Ingesting %d corpus/corpora with max %d segments each",
        len(targets),
        args.max_segments,
    )

    results = {}
    for corpus_key in targets:
        try:
            output_path = download_and_extract(
                corpus_key,
                max_segments=args.max_segments,
                source_lang=args.source_lang,
                target_lang=args.target_lang,
            )
            results[corpus_key] = str(output_path)
        except Exception:
            log.exception("Failed to ingest %s", corpus_key)
            results[corpus_key] = "FAILED"

    # Summary
    print("\n" + "=" * 60)
    print("Ingestion summary:")
    print("=" * 60)
    for key, result in results.items():
        if result == "FAILED":
            print(f"  FAIL {key}")
        else:
            n_lines = sum(1 for _ in open(result, encoding="utf-8"))
            print(f"  OK   {key}: {n_lines:,} segments -> {result}")
    print("=" * 60)


if __name__ == "__main__":
    main()
