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

## Architecture

- **Data Layer**: EU/UN parallel corpora (Europarl, DGT-TM, EUR-Lex, UNPC) + IATE terminology
- **Pipeline Layer**: Segment selection → MT generation → Error injection → QE validation → Explanation generation
- **Service Layer**: FastAPI with scoring, feedback, analytics, and progression management
- **Student Interface**: Gradio — evaluation, post-editing, navigator, and comparison modes
- **Teacher Interface**: Streamlit — item review, exercise builder, analytics dashboard, ToM blind spot analysis

## License

TBD
