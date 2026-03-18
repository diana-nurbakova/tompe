"""FastAPI application — main service layer entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="ToM-PE API",
    description="Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ── Item endpoints ──────────────────────────────────────────────────────────

@app.get("/api/items")
async def list_items():
    """List available assessment items."""
    raise NotImplementedError


@app.get("/api/items/{item_id}")
async def get_item(item_id: str):
    """Retrieve a single assessment item."""
    raise NotImplementedError


# ── Session endpoints ───────────────────────────────────────────────────────

@app.post("/api/sessions")
async def create_session():
    """Create a new student session."""
    raise NotImplementedError


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve session state."""
    raise NotImplementedError


# ── Response endpoints ──────────────────────────────────────────────────────

@app.post("/api/responses")
async def submit_response():
    """Submit a student response for scoring."""
    raise NotImplementedError


# ── Feedback endpoints ──────────────────────────────────────────────────────

@app.get("/api/feedback/{response_id}")
async def get_feedback(response_id: str):
    """Retrieve feedback for a scored response."""
    raise NotImplementedError


# ── Analytics endpoints ─────────────────────────────────────────────────────

@app.get("/api/analytics/student/{student_id}")
async def get_student_analytics(student_id: str):
    """Retrieve aggregated performance data for a student."""
    raise NotImplementedError


@app.get("/api/analytics/class/{class_id}")
async def get_class_analytics(class_id: str):
    """Retrieve aggregated performance data for a class."""
    raise NotImplementedError


# ── Config endpoints ────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Retrieve teacher configuration."""
    raise NotImplementedError


def main():
    """Run the API server."""
    import uvicorn

    uvicorn.run("tompe.services.api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
