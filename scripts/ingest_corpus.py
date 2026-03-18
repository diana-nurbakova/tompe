"""Corpus ingestion script.

Downloads EN-FR parallel segments from EU/UN corpora via OPUS Moses files
and stores them as JSONL files for the segment selector pipeline stage.

The Moses txt.zip files from OPUS contain pre-aligned parallel text — one
sentence per line in separate .en and .fr files inside the zip. We download
the zip, stream the first N pairs, write JSONL, then delete the zip to
conserve disk space.

Usage:
    uv run python scripts/ingest_corpus.py                    # all corpora, 10k segments each
    uv run python scripts/ingest_corpus.py --corpus europarl  # single corpus
    uv run python scripts/ingest_corpus.py --max-segments 500 # small sample
    uv run python scripts/ingest_corpus.py --list             # show available corpora info
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
import uuid
import zipfile
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


def _moses_zip_url(opus_name: str, version: str, src: str, tgt: str) -> str:
    """Build the OPUS Moses txt.zip download URL."""
    return (
        f"https://object.pouta.csc.fi/OPUS-{opus_name}/{version}/moses/{src}-{tgt}.txt.zip"
    )


def _download_with_progress(url: str, dest: Path) -> None:
    """Download a file with progress reporting."""
    log.info("Downloading %s", url)

    def _report(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 // total_size)
            mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"\r  {mb:.0f}/{total_mb:.0f} MB ({pct}%)", end="", flush=True)

    urllib.request.urlretrieve(url, str(dest), reporthook=_report)
    print()  # newline after progress


def _extract_pairs_from_moses_zip(
    zip_path: Path,
    source_lang: str,
    target_lang: str,
    max_pairs: int,
) -> list[tuple[str, str]]:
    """Extract aligned sentence pairs from a Moses txt.zip.

    The zip typically contains:
      - {corpus}.{src}-{tgt}.{src}  (source sentences, one per line)
      - {corpus}.{src}-{tgt}.{tgt}  (target sentences, one per line)
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

        # Find the source and target text files
        src_file = None
        tgt_file = None
        for name in names:
            if name.endswith(f".{source_lang}"):
                src_file = name
            elif name.endswith(f".{target_lang}"):
                tgt_file = name

        if not src_file or not tgt_file:
            raise FileNotFoundError(
                f"Could not find .{source_lang} and .{target_lang} files in {zip_path}. "
                f"Found: {names}"
            )

        log.info("Reading %s and %s from zip", src_file, tgt_file)

        pairs: list[tuple[str, str]] = []
        with zf.open(src_file) as sf, zf.open(tgt_file) as tf:
            for i, (src_line, tgt_line) in enumerate(zip(sf, tf)):
                if i >= max_pairs:
                    break
                src = src_line.decode("utf-8").strip()
                tgt = tgt_line.decode("utf-8").strip()
                if src and tgt:
                    pairs.append((src, tgt))

    return pairs


def download_and_extract(
    corpus_key: str,
    max_segments: int = 10_000,
    source_lang: str = "en",
    target_lang: str = "fr",
    keep_cache: bool = False,
) -> Path:
    """Download a Moses txt.zip from OPUS, extract pairs, write JSONL.

    Returns the path to the output JSONL file.
    """
    corpus_cfg = CORPORA[corpus_key]

    output_dir = CORPORA_DIR / corpus_key
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"segments_{source_lang}_{target_lang}.jsonl"

    cache_dir = CACHE_DIR / corpus_key
    cache_dir.mkdir(parents=True, exist_ok=True)

    url = _moses_zip_url(
        corpus_cfg["opus_name"], corpus_cfg["version"], source_lang, target_lang
    )
    zip_path = cache_dir / f"{corpus_cfg['opus_name']}_{source_lang}-{target_lang}.txt.zip"

    # Download if not cached
    if zip_path.exists():
        log.info("Using cached %s", zip_path)
    else:
        _download_with_progress(url, zip_path)

    # Extract pairs
    log.info(
        "Extracting up to %d pairs from %s (%s)",
        max_segments,
        corpus_key,
        corpus_cfg["opus_name"],
    )
    pairs = _extract_pairs_from_moses_zip(zip_path, source_lang, target_lang, max_segments)
    log.info("Extracted %d aligned pairs from %s", len(pairs), corpus_key)

    # Write JSONL
    written = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for src, tgt in pairs:
            segment = {
                "segment_id": f"{corpus_key}-{uuid.uuid4().hex[:12]}",
                "source_text": src,
                "reference_translation": tgt,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "corpus_origin": corpus_key,
                "domain": corpus_cfg["domain"],
                "register": corpus_cfg["register"],
            }
            f.write(json.dumps(segment, ensure_ascii=False) + "\n")
            written += 1

    log.info("Wrote %d segments to %s", written, output_file)

    # Clean up zip to save disk space
    if not keep_cache:
        zip_path.unlink(missing_ok=True)
        log.info("Cleaned up cached zip to save disk space")

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
            size_mb = jsonl.stat().st_size / (1024 * 1024)
            print(f"  {key:<12} {n_lines:>8,} segments  ({size_mb:.1f} MB)")
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
        "--keep-cache",
        action="store_true",
        help="Keep downloaded zip files (default: delete after extraction)",
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
                keep_cache=args.keep_cache,
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
