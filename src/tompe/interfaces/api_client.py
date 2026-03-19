"""HTTP client wrapper for student app → FastAPI backend communication.

The student Gradio app uses this to call the backend API. The teacher Streamlit
app calls services directly (same machine, simpler for v1).
"""

from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


class ToMPEClient:
    """Synchronous HTTP client for the ToM-PE API."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = None

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _handle_response(self, resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)
        return resp.json()

    # ── Auth ──────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict:
        """Login and store the session token."""
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self._url("/api/auth/login"),
                json={"username": username, "password": password},
            )
        data = self._handle_response(resp)
        self._token = data["token"]
        return data

    def logout(self):
        """Logout and clear the session token."""
        self._token = None

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    # ── Consent ───────────────────────────────────────────────────────────

    def get_consent_text(self) -> dict:
        """Get the current consent form text."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(self._url("/api/consent/text"))
        return self._handle_response(resp)

    def get_consent_status(self) -> dict:
        """Check consent status for the current student."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self._url("/api/consent/status"), headers=self._headers
            )
        return self._handle_response(resp)

    def submit_consent(self, tier1: bool, tier2: bool) -> dict:
        """Submit consent decision."""
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self._url("/api/consent/submit"),
                json={"tier1_research_data": tier1, "tier2_publication_excerpts": tier2},
                headers=self._headers,
            )
        return self._handle_response(resp)

    def withdraw_consent(self) -> dict:
        """Withdraw previously given consent."""
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self._url("/api/consent/withdraw"), headers=self._headers
            )
        return self._handle_response(resp)

    # ── Assignments & Exercises ───────────────────────────────────────────

    def get_assignments(self, student_id: str) -> list[dict]:
        """Get all assignments for a student."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self._url("/api/assignments"),
                params={"student_id": student_id},
                headers=self._headers,
            )
        return self._handle_response(resp)

    def get_exercise(self, exercise_id: str) -> dict:
        """Get exercise details."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self._url(f"/api/exercises/{exercise_id}"),
                headers=self._headers,
            )
        return self._handle_response(resp)

    def get_item(self, item_id: str) -> dict:
        """Get an assessment item."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self._url(f"/api/items/{item_id}"),
                headers=self._headers,
            )
        return self._handle_response(resp)

    def update_assignment(self, assignment_id: str, updates: dict) -> dict:
        """Update an assignment (advance item, change status)."""
        with httpx.Client(timeout=10) as client:
            resp = client.put(
                self._url(f"/api/assignments/{assignment_id}"),
                json=updates,
                headers=self._headers,
            )
        return self._handle_response(resp)

    # ── Responses & Feedback ─────────────────────────────────────────────

    def submit_response(self, item_id: str, mode: str, **kwargs) -> dict:
        """Submit annotations/edits for an item."""
        payload = {"item_id": item_id, "mode": mode, **kwargs}
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self._url("/api/responses"),
                json=payload,
                headers=self._headers,
            )
        return self._handle_response(resp)

    def submit_justifications(self, response_id: str, justifications: list[dict]) -> dict:
        """Submit justifications for a response."""
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self._url(f"/api/responses/{response_id}/justifications"),
                json={"justifications": justifications},
                headers=self._headers,
            )
        return self._handle_response(resp)

    def get_feedback(self, response_id: str) -> dict:
        """Get feedback for a submitted response."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                self._url(f"/api/feedback/{response_id}"),
                headers=self._headers,
            )
        return self._handle_response(resp)

    # ── Progress ─────────────────────────────────────────────────────────

    def get_progress(self, student_id: str) -> dict:
        """Get student progress data."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self._url(f"/api/progress/{student_id}"),
                headers=self._headers,
            )
        return self._handle_response(resp)


class APIError(Exception):
    """Raised when the API returns an error."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API Error {status_code}: {detail}")
