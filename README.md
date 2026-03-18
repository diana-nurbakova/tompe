# ToM-PE

**Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training**

A controlled pedagogical environment for training translation students in MT quality evaluation and MT post-editing. The platform generates assessment items with known, categorized errors injected into MT output from EU/UN parallel corpora, scaffolded by a Theory of Mind framework.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the API server
uv run tompe-api

# Run the student interface (Gradio)
uv run tompe-student

# Run the teacher dashboard (Streamlit)
uv run streamlit run src/tompe/interfaces/teacher_app.py
```

## Project Structure

```
src/tompe/
├── schemas/         # Pydantic data models (MQM, ToM, items, responses, scoring)
├── pipeline/        # Item generation pipeline (segment selection → MT → error injection → QE → explanations)
├── services/        # FastAPI backend (scoring, feedback, analytics, progression)
├── interfaces/      # Student UI (Gradio) + Teacher dashboard (Streamlit)
config/              # YAML configuration (settings, MT backends)
scripts/             # Corpus ingestion and batch item generation
tests/               # Test suite
```

## Data: Parallel Corpora

The platform uses sentence-aligned EN-FR parallel corpora from [OPUS](https://opus.nlpl.eu/). The ingestion script downloads pre-aligned Moses-format files and converts them to JSONL.

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

Data files are stored in `data/corpora/{corpus}/segments_en_fr.jsonl` (gitignored — regenerate with the script above).

## Architecture

- **Data Layer**: EU/UN parallel corpora (Europarl, DGT-TM, EUR-Lex, UNPC) + IATE terminology
- **Pipeline Layer**: Segment selection → MT generation → Error injection → QE validation → Explanation generation
- **Service Layer**: FastAPI with scoring, feedback, analytics, and progression management
- **Student Interface**: Gradio — evaluation, post-editing, navigator, and comparison modes
- **Teacher Interface**: Streamlit — item review, exercise builder, analytics dashboard, ToM blind spot analysis

## License

TBD
