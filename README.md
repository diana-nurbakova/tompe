# ToM-PE

**Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training**

A controlled pedagogical environment for training translation students in machine
translation (MT) quality evaluation and MT post-editing. The platform generates
assessment items with known, categorized errors injected into MT output from EU/UN
parallel corpora, then scaffolds learning through a Theory of Mind (ToM) framework —
gradually shifting cognitive load from the system to the learner across scaffolding
levels (L0–L3). It pairs a FastAPI backend (scoring, feedback, analytics, Bayesian
Knowledge Tracing) with a Gradio student interface and a Streamlit teacher dashboard.

## Quick Start

```bash
# Install dependencies (uv + Python 3.11+)
uv sync

# Run the FastAPI backend (scoring, feedback, analytics, progression)
uv run tompe-api

# Run the student interface (Gradio)
uv run tompe-student

# Run the teacher dashboard (Streamlit)
uv run tompe-teacher

# Run the standalone evaluation study app (Gradio)
uv run tompe-study
```

Optional dependency groups:

```bash
uv sync --extra dev          # pytest, pytest-asyncio, ruff
uv sync --extra ml           # unbabel-comet, transformers, torch (xCOMET/QE)
uv sync --extra experiments  # POT, scikit-learn, scipy, matplotlib, seaborn
```

LLM-backed stages (MT generation, error injection, explanations) read API keys from
the environment (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`); backends are configured
in `config/mt_backends.yaml`.

## Project Structure

```
src/tompe/
├── schemas/         # Pydantic data models (MQM, ToM, items, responses, scoring, sessions, badges, competency)
├── pipeline/        # Item generation: segment selection → MT → error injection → QE → explanations
├── services/        # FastAPI backend: scoring, feedback, analytics, BKT, badges, auth, datastore, progression
└── interfaces/      # Student UI (Gradio), teacher dashboard (Streamlit), expert annotation tool (Gradio)

study/               # Standalone ECTEL 2026 evaluation study app (Gradio)
scripts/             # Corpus/IATE ingestion, batch item generation, codebook scaffolding & validation
config/              # YAML/JSON configuration (settings, MT backends, badges)
data/                # Corpora, codebook, caches, generated items (gitignored)
docs/                # Developer documentation (architecture, generation, demo readiness)
specs/               # Requirements & experimental specifications
experiments/         # Research experiment infrastructure (pipeline validation, stratification, analysis)
outputs/             # Generated reports and experiment results
tests/               # Test suite (pytest)
```

## Pipeline

The item generation pipeline (`src/tompe/pipeline/`, orchestrated by `item_builder.py`)
turns parallel-corpus segments into pedagogical assessment items:

1. **Segment selection** — filter/sample source–reference pairs from ingested corpora.
2. **MT generation** — translate sources via configured remote MT backends.
3. **Error injection** — inject categorized MQM errors into MT output using a two-step,
   LLM-driven process keyed to the MQM taxonomy (10 tags × ~37 error types).
4. **QE validation** — quality-estimation checks that injected items are well-formed and
   the errors are detectable; optional authentic-error detection (xCOMET/GEMBA).
5. **Explanation generation** — ToM-informed Layer 1 / 2a / 2b explanations (with LLM
   response caching) plus false-annotation generation for scaffolding.

## Services

The FastAPI backend (`src/tompe/services/`) exposes REST endpoints for the interfaces:

- **scoring** — span IoU matching and error-detection scoring
- **feedback** — post-submission feedback assembly (cognitive-forcing design)
- **progression** — scaffolding-level advancement (L0–L3)
- **bkt** — Bayesian Knowledge Tracing for per-skill mastery estimation
- **analytics** — learning analytics, including longitudinal and blind-spot analysis
- **badges** — achievement progression and unlocking
- **auth** / **datastore** — student accounts, class groups, and JSON-file persistence

## Interfaces

| App | Framework | Launch | Purpose |
| --- | --------- | ------ | ------- |
| Student | Gradio | `uv run tompe-student` | Login, 3-phase workflow, L0–L3 scaffolding; evaluation, post-editing, navigator, and comparison modes |
| Teacher | Streamlit | `uv run tompe-teacher` | Corpus browser, MT generation, item review, exercise builder, class management, analytics & blind-spot dashboards |
| Annotation | Gradio | `uv run python -m tompe.interfaces.annotation_app` | Expert MQM annotation tool for Track C validation (blind Phase A, ground-truth Phase B) |
| Study | Gradio | `uv run tompe-study` | Standalone linear evaluation study for ECTEL 2026 |

The student and study apps communicate with the FastAPI backend via `interfaces/api_client.py`,
so run `tompe-api` alongside them.

## Data: Parallel Corpora

The platform uses sentence-aligned EN-FR parallel corpora from [OPUS](https://opus.nlpl.eu/).
The ingestion script downloads pre-aligned Moses-format files and converts them to JSONL.

```bash
# Download all available corpora (10k segments each by default)
uv run python scripts/ingest_corpus.py

# Download a single corpus
uv run python scripts/ingest_corpus.py --corpus europarl

# Smaller sample for quick prototyping
uv run python scripts/ingest_corpus.py --max-segments 500

# Check what's downloaded
uv run python scripts/ingest_corpus.py --list
```

| Corpus | OPUS Source | Domain | Segments |
| ------ | ----------- | ------ | -------- |
| `europarl` | [Europarl v8](https://opus.nlpl.eu/Europarl.php) | Parliamentary proceedings | ~2M available |
| `dgt_tm` | [DGT v2019](https://opus.nlpl.eu/DGT.php) | EU legal translation memory | ~5M available |
| `eurlex` | [EUbookshop v2](https://opus.nlpl.eu/EUbookshop.php) | EU legislation & publications | ~10M available |
| `unpc` | [UNPC v1.0](https://opus.nlpl.eu/UNPC.php) | UN institutional documents | ~30M available |

Data files are stored in `data/corpora/{corpus}/segments_en_fr.jsonl` (gitignored —
regenerate with the script above). Terminology can be ingested separately with
`scripts/ingest_iate.py`.

## Generating Items

```bash
# Batch-generate assessment items from ingested segments
uv run python scripts/generate_items.py

# Validate the MQM codebook
uv run python scripts/validate_codebook.py
```

## Tests

```bash
uv run pytest
```

The suite (`tests/`) covers the codebook loader, MQM taxonomy, segment selection,
MT generation (mocked), error injection, and schema validation.

## License

Released under the [MIT License](LICENSE).

Copyright (c) 2026 Diana Nurbakova (INSA Lyon, CNRS, Université Claude Bernard Lyon 1,
LIRIS UMR5205, 69100 Villeurbanne, France) and Liana Ermakova (HCTI, University of Brest,
Brest, France).
