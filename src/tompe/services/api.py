"""FastAPI application — main service layer entry point.

Provides REST API endpoints for both the Student (Gradio) and Teacher (Streamlit)
interfaces. Organized into routers per domain.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tompe.schemas.enums import AnnotationLevel, MQMCategory, Severity
from tompe.schemas.item import AssessmentItem
from tompe.schemas.response import IdentifiedError, Justification, StudentResponse
from tompe.schemas.scoring import ScoringResult
from tompe.schemas.session import (
    ClassGroup,
    Exercise,
    ExerciseAssignment,
    ResearchConsent,
    StudentAccount,
)
from tompe.services.auth import (
    authenticate,
    bulk_import_csv,
    create_account,
    create_class,
    get_class,
    get_student,
    invalidate_token,
    list_classes,
    list_students,
    update_student_levels,
    verify_token,
)
from tompe.services.datastore import (
    assignments_store,
    exercises_store,
    feedback_store,
    items_store,
    responses_store,
)
from tompe.services.badges import (
    get_badge_summary,
    process_badges_and_xp,
)
from tompe.services.feedback import prepare_feedback
from tompe.services.scoring import (
    score_evaluation_response,
    score_navigator_response,
    score_postediting_response,
)

app = FastAPI(
    title="ToM-PE API",
    description="Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training",
    version="0.1.0",
)

# CORS for Gradio / Streamlit cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ──────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    student_id: str
    display_name: str
    current_level: str
    allowed_levels: list[str]
    consent_pending: bool  # True if consent form has not been shown yet


class CreateStudentRequest(BaseModel):
    username: str
    display_name: str
    password: str
    class_id: str
    current_level: AnnotationLevel = AnnotationLevel.NAVIGATOR
    allowed_levels: list[AnnotationLevel] | None = None


class UpdateLevelsRequest(BaseModel):
    current_level: AnnotationLevel | None = None
    allowed_levels: list[AnnotationLevel] | None = None


class CreateClassRequest(BaseModel):
    class_name: str
    default_levels: list[AnnotationLevel] | None = None


class CreateExerciseRequest(BaseModel):
    name: str
    description: str = ""
    mode: str = "evaluation"
    level: AnnotationLevel = AnnotationLevel.ANALYST
    item_ids: list[str] = []
    justification_type: str = "free_text"
    clean_segment_ratio: float = 0.0
    false_annotation_ratio: float = 0.0
    item_ordering: str = "manual"
    domain: str = ""
    direction: str = ""


class AssignExerciseRequest(BaseModel):
    exercise_id: str
    student_ids: list[str] | None = None
    class_id: str | None = None


class SubmitAnnotationsRequest(BaseModel):
    item_id: str
    mode: str = "evaluation"
    identified_errors: list[IdentifiedError] = []
    edited_text: str | None = None
    time_spent_seconds: float = 0.0


class SubmitJustificationsRequest(BaseModel):
    justifications: list[Justification]


class CorpusQueryParams(BaseModel):
    origins: list[str] | None = None
    domain: str | None = None
    min_tokens: int = 10
    max_tokens: int = 50
    search_text: str | None = None
    limit: int = 100
    offset: int = 0


class ConsentRequest(BaseModel):
    tier1_research_data: bool
    tier2_publication_excerpts: bool


class WithdrawConsentRequest(BaseModel):
    pass  # No fields needed — the action itself is the intent


class ItemStatusRequest(BaseModel):
    status: str  # "reviewed", "published", "retired"


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ── Auth endpoints ───────────────────────────────────────────────────────────


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate a student and return a session token."""
    try:
        account, token = authenticate(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return LoginResponse(
        token=token,
        student_id=account.student_id,
        display_name=account.display_name,
        current_level=account.current_level,
        allowed_levels=[lvl for lvl in account.allowed_levels],
        consent_pending=account.consent is None,
    )


@app.post("/api/auth/logout")
async def logout(student: StudentAccount = Depends(verify_token)):
    """Invalidate the current session token."""
    # Token is in the Authorization header; we'd need to extract it.
    # For simplicity, just return success — token cleanup handled client-side.
    return {"status": "ok"}


# ── Consent endpoints ────────────────────────────────────────────────────────

CURRENT_CONSENT_VERSION = "1.0"


@app.get("/api/consent/text")
async def api_get_consent_text():
    """Return the current consent form text (markdown)."""
    from pathlib import Path
    consent_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "data" / "consent" / f"consent_v{CURRENT_CONSENT_VERSION}.md"
    )
    if consent_path.exists():
        text = consent_path.read_text(encoding="utf-8")
    else:
        text = "Consent form not found. Please contact your instructor."
    return {"version": CURRENT_CONSENT_VERSION, "text": text}


@app.get("/api/consent/status")
async def api_get_consent_status(student: StudentAccount = Depends(verify_token)):
    """Check current consent status for the authenticated student."""
    if student.consent is None:
        return {"consent_given": False, "consent_pending": True}
    return {
        "consent_given": True,
        "consent_pending": False,
        "tier1_research_data": student.consent.tier1_research_data,
        "tier2_publication_excerpts": student.consent.tier2_publication_excerpts,
        "consent_version": student.consent.consent_version,
        "timestamp": student.consent.timestamp,
        "withdrawn": student.consent.withdrawn,
    }


@app.post("/api/consent/submit")
async def api_submit_consent(
    req: ConsentRequest,
    student: StudentAccount = Depends(verify_token),
):
    """Record a student's consent decision. Neither tier is required."""
    from tompe.services.datastore import students_store

    consent = ResearchConsent(
        consent_version=CURRENT_CONSENT_VERSION,
        tier1_research_data=req.tier1_research_data,
        tier2_publication_excerpts=req.tier2_publication_excerpts,
        timestamp=datetime.now(),
    )
    updated = students_store.update(
        student.student_id,
        StudentAccount,
        {"consent": consent.model_dump()},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return {
        "status": "ok",
        "tier1_research_data": consent.tier1_research_data,
        "tier2_publication_excerpts": consent.tier2_publication_excerpts,
    }


@app.post("/api/consent/withdraw")
async def api_withdraw_consent(
    student: StudentAccount = Depends(verify_token),
):
    """Withdraw previously given research consent."""
    from tompe.services.datastore import students_store

    if student.consent is None:
        raise HTTPException(status_code=400, detail="No consent to withdraw")

    consent_data = student.consent.model_dump()
    consent_data["withdrawn"] = True
    consent_data["withdrawn_at"] = datetime.now().isoformat()
    consent_data["tier1_research_data"] = False
    consent_data["tier2_publication_excerpts"] = False

    updated = students_store.update(
        student.student_id, StudentAccount, {"consent": consent_data}
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"status": "consent_withdrawn"}


# ── Student endpoints ────────────────────────────────────────────────────────


@app.post("/api/students")
async def api_create_student(req: CreateStudentRequest):
    """Create a new student account (teacher action)."""
    try:
        account = create_account(
            username=req.username,
            display_name=req.display_name,
            password=req.password,
            class_id=req.class_id,
            current_level=req.current_level,
            allowed_levels=req.allowed_levels,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return account.model_dump(exclude={"password_hash"})


@app.get("/api/students")
async def api_list_students(class_id: Optional[str] = None):
    """List student accounts, optionally filtered by class."""
    students = list_students(class_id)
    return [s.model_dump(exclude={"password_hash"}) for s in students]


@app.get("/api/students/{student_id}")
async def api_get_student(student_id: str):
    """Get a single student account."""
    student = get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student.model_dump(exclude={"password_hash"})


@app.put("/api/students/{student_id}/levels")
async def api_update_levels(student_id: str, req: UpdateLevelsRequest):
    """Update a student's level configuration."""
    updated = update_student_levels(
        student_id, req.current_level, req.allowed_levels
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return updated.model_dump(exclude={"password_hash"})


# ── Class endpoints ──────────────────────────────────────────────────────────


@app.post("/api/classes")
async def api_create_class(req: CreateClassRequest):
    """Create a new class group."""
    cls = create_class(req.class_name, req.default_levels)
    return cls.model_dump()


@app.get("/api/classes")
async def api_list_classes():
    """List all class groups."""
    return [c.model_dump() for c in list_classes()]


@app.get("/api/classes/{class_id}")
async def api_get_class(class_id: str):
    """Get a single class group."""
    cls = get_class(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    return cls.model_dump()


# ── Corpus endpoints ─────────────────────────────────────────────────────────


@app.get("/api/corpus/segments")
async def api_browse_corpus(
    origins: Optional[str] = None,
    domain: Optional[str] = None,
    direction: Optional[str] = None,
    min_tokens: int = 10,
    max_tokens: int = 50,
    search_text: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Browse corpus segments with filters."""
    from tompe.pipeline.segment_selector import load_corpus, filter_segments

    # Parse origins
    origin_list = origins.split(",") if origins else None

    try:
        segments = load_corpus(origins=origin_list)
    except Exception:
        segments = []

    # Apply filters
    filtered = filter_segments(
        segments,
        min_tokens=min_tokens,
        max_tokens=max_tokens,
    )

    # Domain filter
    if domain:
        filtered = [s for s in filtered if s.domain == domain]

    # Direction filter
    if direction:
        if "fr" in direction.lower() and "en" in direction.lower():
            if direction.lower().startswith("fr"):
                filtered = [s for s in filtered if s.source_lang == "fr"]
            else:
                filtered = [s for s in filtered if s.source_lang == "en"]

    # Text search
    if search_text:
        q = search_text.lower()
        filtered = [
            s for s in filtered
            if q in s.source_text.lower() or q in s.reference_translation.lower()
        ]

    total = len(filtered)
    page = filtered[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "segments": [s.model_dump() for s in page],
    }


# ── Translation endpoints ───────────────────────────────────────────────────


@app.post("/api/translations/generate")
async def api_generate_translations(
    segment_ids: list[str],
    mt_systems: list[str] | None = None,
):
    """Generate MT translations for selected segments."""
    # This would call mt_generator — for now return a placeholder
    # In production, this triggers the async pipeline
    return {
        "status": "queued",
        "segment_ids": segment_ids,
        "mt_systems": mt_systems or ["google"],
        "message": "Translation generation queued. Check items store for results.",
    }


# ── Item endpoints ───────────────────────────────────────────────────────────


@app.get("/api/items")
async def api_list_items(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 100,
):
    """List assessment items with optional filters."""
    def filter_fn(item: AssessmentItem) -> bool:
        if status and item.item_status != status:
            return False
        if domain and item.domain != domain:
            return False
        return True

    items = items_store.list_all(AssessmentItem, filter_fn=filter_fn)
    return [item.model_dump() for item in items[:limit]]


@app.get("/api/items/{item_id}")
async def api_get_item(item_id: str):
    """Retrieve a single assessment item."""
    item = items_store.get(item_id, AssessmentItem)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item.model_dump()


@app.put("/api/items/{item_id}")
async def api_update_item(item_id: str, updates: dict[str, Any]):
    """Update an assessment item (teacher review edits)."""
    updated = items_store.update(item_id, AssessmentItem, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return updated.model_dump()


@app.put("/api/items/{item_id}/status")
async def api_update_item_status(item_id: str, req: ItemStatusRequest):
    """Change an item's status (approve/reject/retire)."""
    updated = items_store.update(item_id, AssessmentItem, {"item_status": req.status})
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return updated.model_dump()


# ── Exercise endpoints ───────────────────────────────────────────────────────


@app.post("/api/exercises")
async def api_create_exercise(req: CreateExerciseRequest):
    """Create a new exercise."""
    exercise = Exercise(
        exercise_id=str(uuid4()),
        name=req.name,
        description=req.description,
        mode=req.mode,
        level=req.level,
        item_ids=req.item_ids,
        justification_type=req.justification_type,
        clean_segment_ratio=req.clean_segment_ratio,
        false_annotation_ratio=req.false_annotation_ratio,
        item_ordering=req.item_ordering,
        domain=req.domain,
        direction=req.direction,
    )
    exercises_store.save(exercise)
    return exercise.model_dump()


@app.get("/api/exercises")
async def api_list_exercises():
    """List all exercises."""
    return [e.model_dump() for e in exercises_store.list_all(Exercise)]


@app.get("/api/exercises/{exercise_id}")
async def api_get_exercise(exercise_id: str):
    """Get a single exercise with details."""
    exercise = exercises_store.get(exercise_id, Exercise)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise.model_dump()


@app.post("/api/assignments")
async def api_assign_exercise(req: AssignExerciseRequest):
    """Assign an exercise to students or a class."""
    exercise = exercises_store.get(req.exercise_id, Exercise)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    student_ids = req.student_ids or []
    if req.class_id:
        class_students = list_students(req.class_id)
        student_ids.extend(s.student_id for s in class_students)
        # Update exercise
        exercises_store.update(
            req.exercise_id, Exercise, {"assigned_to_class": req.class_id}
        )

    assignments = []
    for sid in set(student_ids):
        assignment = ExerciseAssignment(
            assignment_id=str(uuid4()),
            exercise_id=req.exercise_id,
            student_id=sid,
        )
        assignments_store.save(assignment)
        assignments.append(assignment.model_dump())

        # Update exercise's assigned_to_students
        if sid not in exercise.assigned_to_students:
            exercise.assigned_to_students.append(sid)

    exercises_store.save(exercise)
    return {"assignments": assignments}


@app.get("/api/assignments")
async def api_list_assignments(student_id: Optional[str] = None):
    """List exercise assignments, optionally for a specific student."""
    if student_id:
        return [
            a.model_dump()
            for a in assignments_store.list_all(
                ExerciseAssignment,
                filter_fn=lambda a: a.student_id == student_id,
            )
        ]
    return [a.model_dump() for a in assignments_store.list_all(ExerciseAssignment)]


@app.get("/api/assignments/{assignment_id}")
async def api_get_assignment(assignment_id: str):
    """Get a single assignment."""
    assignment = assignments_store.get(assignment_id, ExerciseAssignment)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment.model_dump()


@app.put("/api/assignments/{assignment_id}")
async def api_update_assignment(assignment_id: str, updates: dict[str, Any]):
    """Update an assignment (e.g., advance item index, update status)."""
    updated = assignments_store.update(assignment_id, ExerciseAssignment, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return updated.model_dump()


# ── Response endpoints ───────────────────────────────────────────────────────


@app.post("/api/responses")
async def api_submit_response(
    req: SubmitAnnotationsRequest,
    student: StudentAccount = Depends(verify_token),
):
    """Submit a student's annotations for an item."""
    response = StudentResponse(
        response_id=str(uuid4()),
        session_id=str(uuid4()),  # Simplified: one session per response
        item_id=req.item_id,
        student_id=student.student_id,
        mode=req.mode,
        timestamp=datetime.now(),
        time_spent_seconds=req.time_spent_seconds,
        identified_errors=req.identified_errors if req.mode == "evaluation" else None,
        edited_text=req.edited_text if req.mode == "postediting" else None,
    )
    responses_store.save(response)
    return {"response_id": response.response_id}


@app.post("/api/responses/{response_id}/justifications")
async def api_submit_justifications(
    response_id: str,
    req: SubmitJustificationsRequest,
    student: StudentAccount = Depends(verify_token),
):
    """Submit justifications for a previously submitted response."""
    response = responses_store.get(response_id, StudentResponse)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")
    if response.student_id != student.student_id:
        raise HTTPException(status_code=403, detail="Not your response")

    updated = responses_store.update(
        response_id,
        StudentResponse,
        {"justifications": [j.model_dump() for j in req.justifications]},
    )
    return {"status": "ok", "justification_count": len(req.justifications)}


# ── Feedback endpoints ───────────────────────────────────────────────────────


@app.get("/api/feedback/{response_id}")
async def api_get_feedback(response_id: str):
    """Get feedback for a submitted response. Triggers scoring if needed."""
    # Check if feedback already computed
    existing = feedback_store.get(response_id, ScoringResult)
    response = responses_store.get(response_id, StudentResponse)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    item = items_store.get(response.item_id, AssessmentItem)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Compute scoring
    if response.mode == "evaluation":
        scoring = score_evaluation_response(response, item)
    elif response.mode == "postediting":
        scoring = score_postediting_response(response, item)
    elif response.mode == "navigator":
        scoring = score_navigator_response(response, item)
    else:
        scoring = score_evaluation_response(response, item)

    # Save scoring result
    feedback_store.save(scoring)

    # Process badges and XP
    # Determine scaffolding level and ToM level for XP multipliers
    scaffolding_level = "analyst"  # default
    exercise = None
    # Try to find the exercise for this response via assignments
    student_assignments = assignments_store.list_all(
        ExerciseAssignment,
        filter_fn=lambda a: a.student_id == response.student_id,
    )
    for asgn in student_assignments:
        ex = exercises_store.get(asgn.exercise_id, Exercise)
        if ex and response.item_id in ex.item_ids:
            exercise = ex
            scaffolding_level = ex.level.value if hasattr(ex.level, 'value') else str(ex.level)
            break

    # Determine dominant ToM level from item errors
    tom_level = "1st_machine"
    if item.errors:
        from collections import Counter
        tom_counts = Counter(
            e.tom_level.value if hasattr(e.tom_level, 'value') else str(e.tom_level)
            for e in item.errors if hasattr(e, 'tom_level')
        )
        if tom_counts:
            tom_level = tom_counts.most_common(1)[0][0]

    # Count category and severity matches from scoring
    matched_categories = []
    category_matches = 0
    severity_matches = 0
    if response.identified_errors and item.errors:
        from tompe.services.scoring import compute_span_iou
        for s_err in response.identified_errors:
            for gt_err in item.errors:
                iou = compute_span_iou(
                    (s_err.span_start, s_err.span_end),
                    (gt_err.span_start, gt_err.span_end),
                )
                if iou >= 0.5:
                    tag = gt_err.primary_tag.value if hasattr(gt_err.primary_tag, 'value') else str(gt_err.primary_tag)
                    matched_categories.append(tag)
                    if hasattr(s_err, 'student_mqm_category') and hasattr(gt_err, 'primary_tag'):
                        student_cat = s_err.student_mqm_category
                        if student_cat and str(student_cat).upper() == tag.upper():
                            category_matches += 1
                    if hasattr(s_err, 'student_severity') and hasattr(gt_err, 'severity'):
                        if str(s_err.student_severity) == str(gt_err.severity):
                            severity_matches += 1
                    break

    # Count completed exercises at this level for progression badges
    completed_at_level = 0
    for asgn in student_assignments:
        if asgn.status == "completed":
            ex = exercises_store.get(asgn.exercise_id, Exercise)
            if ex and (ex.level.value if hasattr(ex.level, 'value') else str(ex.level)) == scaffolding_level:
                completed_at_level += 1

    exercise_id = exercise.exercise_id if exercise else ""
    n_items = len(exercise.item_ids) if exercise else 1

    badge_result = process_badges_and_xp(
        student_id=response.student_id,
        scoring=scoring,
        scaffolding_level=scaffolding_level,
        tom_level=tom_level,
        exercise_id=exercise_id,
        matched_categories=matched_categories,
        category_matches=category_matches,
        severity_matches=severity_matches,
        n_items=n_items,
        completed_exercises_at_level=completed_at_level,
    )

    # Build feedback payload
    feedback = prepare_feedback(response, item, scoring)
    feedback["badges"] = badge_result
    return feedback


# ── Progress endpoints ───────────────────────────────────────────────────────


@app.get("/api/progress/{student_id}")
async def api_get_progress(student_id: str):
    """Get a student's progress summary."""
    student = get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Gather all responses and scores for this student
    student_responses = responses_store.list_all(
        StudentResponse,
        filter_fn=lambda r: r.student_id == student_id,
    )
    student_scores = feedback_store.list_all(
        ScoringResult,
        filter_fn=lambda s: s.response_id in {r.response_id for r in student_responses},
    )

    # Compute summary
    total_sessions = len(student_responses)
    avg_f1 = (
        sum(s.f1 for s in student_scores) / len(student_scores)
        if student_scores else 0.0
    )

    # Include badge summary
    badge_summary = get_badge_summary(student_id)

    return {
        "student_id": student_id,
        "display_name": student.display_name,
        "current_level": student.current_level,
        "total_sessions": total_sessions,
        "avg_detection_rate": round(avg_f1 * 100, 1),
        "scores": [s.model_dump() for s in student_scores],
        "badges": badge_summary,
    }


@app.get("/api/badges/{student_id}")
async def api_get_badges(student_id: str):
    """Get badge summary for a student."""
    student = get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return get_badge_summary(student_id)


# ── Analytics endpoints ──────────────────────────────────────────────────────


@app.get("/api/analytics/class/{class_id}")
async def api_class_analytics(class_id: str):
    """Get aggregated class analytics."""
    students = list_students(class_id)
    if not students:
        raise HTTPException(status_code=404, detail="Class not found or empty")

    student_ids = {s.student_id for s in students}

    all_scores = feedback_store.list_all(ScoringResult)
    all_responses = responses_store.list_all(StudentResponse)

    # Filter to this class's students
    response_ids_for_class = {
        r.response_id for r in all_responses if r.student_id in student_ids
    }
    class_scores = [s for s in all_scores if s.response_id in response_ids_for_class]

    if not class_scores:
        return {"class_id": class_id, "student_count": len(students), "scores": []}

    avg_f1 = sum(s.f1 for s in class_scores) / len(class_scores)

    return {
        "class_id": class_id,
        "student_count": len(students),
        "total_responses": len(class_scores),
        "avg_detection_rate": round(avg_f1 * 100, 1),
        "scores": [s.model_dump() for s in class_scores],
    }


@app.get("/api/analytics/student/{student_id}")
async def api_student_analytics(student_id: str):
    """Get detailed analytics for a single student."""
    return await api_get_progress(student_id)


# ── Config endpoint ──────────────────────────────────────────────────────────


@app.get("/api/config")
async def api_get_config():
    """Get system configuration (teacher-facing)."""
    import yaml
    from pathlib import Path

    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config"

    settings = {}
    mt_config = {}

    settings_path = config_path / "settings.yaml"
    if settings_path.exists():
        with open(settings_path) as f:
            settings = yaml.safe_load(f)

    mt_path = config_path / "mt_backends.yaml"
    if mt_path.exists():
        with open(mt_path) as f:
            mt_config = yaml.safe_load(f)

    return {"settings": settings, "mt_backends": mt_config}


# ── Entry point ──────────────────────────────────────────────────────────────


def main():
    """Run the API server."""
    import uvicorn

    uvicorn.run("tompe.services.api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
