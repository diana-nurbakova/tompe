"""JSON file-based data store for ToM-PE v1.

Each entity type is stored as individual JSON files in a dedicated directory
under `data/`. Provides generic CRUD operations parameterized by Pydantic models.
"""

import json
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Project root — two levels up from this file (services/ -> tompe/ -> src/ -> project)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = _PROJECT_ROOT / "data"


class JsonStore:
    """Generic JSON-file CRUD store for Pydantic models.

    Each object is stored as ``{base_dir}/{id}.json``.
    """

    def __init__(self, entity_dir: str, id_field: str = ""):
        """Initialize store for a given entity type.

        Args:
            entity_dir: Subdirectory name under DATA_DIR (e.g., "students").
            id_field: Name of the Pydantic field used as the primary key.
                      If empty, auto-detected from common patterns.
        """
        self.base_dir = DATA_DIR / entity_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._id_field = id_field

    def _get_id(self, obj: BaseModel) -> str:
        """Extract the ID from a Pydantic model instance."""
        if self._id_field:
            return str(getattr(obj, self._id_field))
        # Auto-detect common ID field patterns
        for candidate in ("item_id", "student_id", "class_id", "exercise_id",
                          "assignment_id", "response_id", "token", "id"):
            if hasattr(obj, candidate):
                return str(getattr(obj, candidate))
        raise ValueError(f"Cannot determine ID field for {type(obj).__name__}")

    def _path(self, obj_id: str) -> Path:
        return self.base_dir / f"{obj_id}.json"

    def save(self, obj: BaseModel) -> str:
        """Save an object. Overwrites if exists. Returns the ID."""
        obj_id = self._get_id(obj)
        path = self._path(obj_id)
        path.write_text(obj.model_dump_json(indent=2), encoding="utf-8")
        return obj_id

    def get(self, obj_id: str, model_class: type[T]) -> Optional[T]:
        """Load an object by ID. Returns None if not found."""
        path = self._path(obj_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_class.model_validate(data)

    def list_all(
        self,
        model_class: type[T],
        filter_fn: Optional[Callable[[T], bool]] = None,
    ) -> list[T]:
        """List all objects, optionally filtered."""
        results = []
        if not self.base_dir.exists():
            return results
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                obj = model_class.model_validate(data)
                if filter_fn is None or filter_fn(obj):
                    results.append(obj)
            except Exception:
                continue  # Skip malformed files
        return results

    def update(self, obj_id: str, model_class: type[T], patch: dict[str, Any]) -> Optional[T]:
        """Partial update: load, merge patch, save. Returns updated object or None."""
        obj = self.get(obj_id, model_class)
        if obj is None:
            return None
        data = obj.model_dump()
        data.update(patch)
        updated = model_class.model_validate(data)
        self.save(updated)
        return updated

    def delete(self, obj_id: str) -> bool:
        """Delete an object by ID. Returns True if deleted, False if not found."""
        path = self._path(obj_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, obj_id: str) -> bool:
        """Check if an object exists."""
        return self._path(obj_id).exists()

    def count(self) -> int:
        """Count total objects in the store."""
        if not self.base_dir.exists():
            return 0
        return len(list(self.base_dir.glob("*.json")))


# ── Pre-configured stores ────────────────────────────────────────────────────

students_store = JsonStore("students", id_field="student_id")
classes_store = JsonStore("classes", id_field="class_id")
exercises_store = JsonStore("exercises", id_field="exercise_id")
assignments_store = JsonStore("assignments", id_field="assignment_id")
items_store = JsonStore("items/manifests", id_field="item_id")
responses_store = JsonStore("sessions/responses", id_field="response_id")
tokens_store = JsonStore("sessions/tokens", id_field="token")
feedback_store = JsonStore("feedback", id_field="response_id")
badges_store = JsonStore("badges", id_field="student_id")
