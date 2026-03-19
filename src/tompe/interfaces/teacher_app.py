"""Streamlit teacher interface for ToM-PE.

Provides: corpus browser, MT generation trigger, review queue, exercise builder,
class management, analytics dashboard, and settings. Calls services directly
(same machine, no HTTP overhead for v1).
"""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit as st
import yaml

from tompe.interfaces.components.colors import TAG_COLORS, TAG_LABELS
from tompe.schemas.enums import AnnotationLevel, PrimaryTag, Severity
from tompe.schemas.item import AssessmentItem
from tompe.schemas.session import ClassGroup, Exercise, ExerciseAssignment, StudentAccount
from tompe.services.auth import (
    create_account,
    create_class,
    get_class,
    list_classes,
    list_students,
    update_student_levels,
)
from tompe.services.datastore import (
    assignments_store,
    exercises_store,
    items_store,
    DATA_DIR,
)

# ── Config ───────────────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"


def _load_config() -> dict:
    """Load settings.yaml."""
    path = CONFIG_DIR / "settings.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_mt_config() -> dict:
    """Load mt_backends.yaml."""
    path = CONFIG_DIR / "mt_backends.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    """Launch the teacher interface."""
    st.set_page_config(
        page_title="ToM-PE — Teacher Dashboard",
        page_icon="📋",
        layout="wide",
    )

    st.title("ToM-PE — Teacher Dashboard")
    st.caption("Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training")

    # ── Sidebar navigation (spec §4.1) ───────────────────────────────────
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        [
            "📂 Browse Corpus",
            "📤 Upload Corpus",
            "🔄 Generate Translations",
            "📋 Review Queue",
            "📋 Published Items",
            "📚 Exercise Builder",
            "👥 Class Management",
            "📊 Analytics Dashboard",
            "⚙️ Settings",
        ],
        label_visibility="collapsed",
    )

    # Ensure a default class exists
    _ensure_default_class()

    # ── Page routing ─────────────────────────────────────────────────────
    if page == "📂 Browse Corpus":
        _page_browse_corpus()
    elif page == "📤 Upload Corpus":
        _page_upload_corpus()
    elif page == "🔄 Generate Translations":
        _page_generate_translations()
    elif page == "📋 Review Queue":
        _page_review_queue()
    elif page == "📋 Published Items":
        _page_published_items()
    elif page == "📚 Exercise Builder":
        _page_exercise_builder()
    elif page == "👥 Class Management":
        _page_class_management()
    elif page == "📊 Analytics Dashboard":
        _page_analytics()
    elif page == "⚙️ Settings":
        _page_settings()


def _ensure_default_class():
    """Create a default class if none exists."""
    classes = list_classes()
    if not classes:
        create_class(
            "Default Class",
            default_levels=[AnnotationLevel.NAVIGATOR, AnnotationLevel.GUIDED, AnnotationLevel.INDEPENDENT],
        )


# ── Corpus Browser ───────────────────────────────────────────────────────────


def _page_browse_corpus():
    st.header("📂 Browse Corpus")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sources = st.multiselect(
            "Corpus Source",
            ["europarl", "dgt_tm", "eurlex", "unpc"],
            default=["europarl"],
        )
    with col2:
        domain = st.selectbox("Domain", ["All", "parliamentary", "legal", "institutional"], index=0)
    with col3:
        direction = st.selectbox("Direction", ["Both", "FR→EN", "EN→FR"], index=0)
    with col4:
        register = st.selectbox("Register", ["All", "formal", "semi-formal"], index=0)

    col5, col6 = st.columns(2)
    with col5:
        min_tok, max_tok = st.slider("Token length range", 5, 100, (10, 50))
    with col6:
        search = st.text_input("Search text", placeholder="Search in source or reference...")

    # Load segments
    if st.button("Search", type="primary"):
        with st.spinner("Loading corpus segments..."):
            try:
                from tompe.pipeline.segment_selector import load_corpus, filter_segments

                segments = load_corpus(origins=sources if sources else None)
                segments = filter_segments(segments, min_tokens=min_tok, max_tokens=max_tok)

                if domain != "All":
                    segments = [s for s in segments if s.domain == domain]
                if direction == "FR→EN":
                    segments = [s for s in segments if s.source_lang == "fr"]
                elif direction == "EN→FR":
                    segments = [s for s in segments if s.source_lang == "en"]
                if register != "All":
                    segments = [s for s in segments if s.text_register == register]
                if search:
                    q = search.lower()
                    segments = [
                        s for s in segments
                        if q in s.source_text.lower() or q in s.reference_translation.lower()
                    ]

                st.session_state["corpus_segments"] = segments
                st.success(f"Found {len(segments)} segments")
            except Exception as e:
                st.error(f"Error loading corpus: {e}")
                st.session_state["corpus_segments"] = []

    # Display segments
    segments = st.session_state.get("corpus_segments", [])
    if segments:
        # Build display data
        data = []
        for s in segments[:200]:  # Limit display
            data.append({
                "Select": False,
                "Source": s.source_text[:80],
                "Reference": s.reference_translation[:80],
                "Domain": s.domain,
                "Tokens": int(s.complexity_score * 50),
                "Corpus": s.corpus_origin,
                "ID": s.segment_id,
            })

        edited = st.data_editor(
            data,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "Source": st.column_config.TextColumn("Source (FR)", width="large"),
                "Reference": st.column_config.TextColumn("Reference (EN)", width="large"),
            },
            hide_index=True,
            use_container_width=True,
        )

        selected_ids = [row["ID"] for row in edited if row.get("Select")]
        if selected_ids:
            st.info(f"Selected: {len(selected_ids)} segments")
            st.session_state["selected_segment_ids"] = selected_ids


# ── Upload Corpus ────────────────────────────────────────────────────────────


def _page_upload_corpus():
    st.header("📤 Upload Corpus")

    st.markdown("""
    **Supported formats:**
    - TMX (Translation Memory Exchange)
    - TSV (tab-separated: source \\t target)
    - Aligned text (two files, one line per segment)
    """)

    uploaded = st.file_uploader("Choose file(s)", type=["tmx", "tsv", "txt"], accept_multiple_files=True)

    col1, col2 = st.columns(2)
    with col1:
        corpus_name = st.text_input("Corpus name")
        src_lang = st.selectbox("Source language", ["fr", "en"])
    with col2:
        domain_custom = st.text_input("Domain")
        tgt_lang = st.selectbox("Target language", ["en", "fr"])

    if st.button("Upload & Index", type="primary"):
        if uploaded and corpus_name:
            st.info(f"Upload processing for '{corpus_name}' — feature coming in v2.")
        else:
            st.warning("Please provide file(s) and corpus name.")


# ── Generate Translations ────────────────────────────────────────────────────


def _page_generate_translations():
    st.header("🔄 Generate Translations")

    selected_ids = st.session_state.get("selected_segment_ids", [])
    if not selected_ids:
        st.info("No segments selected. Go to Browse Corpus and select segments first.")
        return

    st.write(f"**Selected segments:** {len(selected_ids)}")

    # MT system selection
    mt_config = _load_mt_config()
    mt_systems = mt_config.get("mt_systems", {})

    st.subheader("MT Systems")
    selected_systems = []
    cols = st.columns(3)
    for i, (name, config) in enumerate(mt_systems.items()):
        with cols[i % 3]:
            enabled = config.get("enabled", False)
            label = f"{name} {'✓' if enabled else '⚠️ Not configured'}"
            if st.checkbox(label, value=enabled, key=f"mt_{name}"):
                selected_systems.append(name)

    st.subheader("LLM Translation Prompt")
    prompt_presets = {
        "EU Formal": "You are a professional EU translator. Translate the following French text into English, maintaining formal register and EU terminology conventions.",
        "General": "Translate the following text from French to English accurately and naturally.",
        "Legal": "You are a legal translator specializing in EU law. Translate with precise legal terminology.",
    }
    preset = st.selectbox("Load preset", list(prompt_presets.keys()))
    prompt = st.text_area("Translation prompt", value=prompt_presets.get(preset, ""), height=100)

    if st.button("Generate Translations", type="primary"):
        st.info(
            f"Translation generation for {len(selected_ids)} segments using "
            f"{', '.join(selected_systems) or 'default'} — "
            "This triggers the async pipeline. Check Review Queue for results."
        )


# ── Review Queue ─────────────────────────────────────────────────────────────


def _page_review_queue():
    st.header("📋 Review Queue")

    items = items_store.list_all(
        AssessmentItem,
        filter_fn=lambda i: i.item_status in ("draft", "reviewed"),
    )

    if not items:
        st.info("No items pending review. Generate items from the corpus first.")
        return

    # Two-column layout
    col_list, col_detail = st.columns([1, 2])

    with col_list:
        st.subheader("Pending Items")
        # Filter controls
        status_filter = st.selectbox("Status", ["All", "draft", "reviewed"], index=0)

        filtered = items
        if status_filter != "All":
            filtered = [i for i in items if i.item_status == status_filter]

        selected_item_id = None
        for item in filtered[:50]:
            status_emoji = {"draft": "📝", "reviewed": "👁"}.get(item.item_status, "📄")
            n_errors = len(item.errors)
            label = f"{status_emoji} {item.item_id[:8]}... | {item.domain} | {n_errors} errors"
            if st.button(label, key=f"item_{item.item_id}", use_container_width=True):
                st.session_state["selected_review_item"] = item.item_id

    with col_detail:
        item_id = st.session_state.get("selected_review_item")
        if item_id:
            item = items_store.get(item_id, AssessmentItem)
            if item:
                _render_review_detail(item)
        else:
            st.info("Select an item from the list to review.")


def _render_review_detail(item: AssessmentItem):
    """Render the detail panel for reviewing an item."""
    st.subheader(f"Item: {item.item_id[:12]}...")

    # Status + metadata strip
    status_colors = {"draft": "orange", "reviewed": "blue", "published": "green", "retired": "red"}
    st.markdown(
        f"**Status:** :{status_colors.get(item.item_status, 'gray')}[{item.item_status}] | "
        f"**Domain:** {item.domain} | **Direction:** {item.source_lang}→{item.target_lang} | "
        f"**Difficulty:** {item.difficulty_level}/5 | **Errors:** {len(item.errors)}"
    )

    # Source + Translation side by side
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Source Text**")
        st.text_area("Source", value=item.source_text, height=100, disabled=True, key="review_src")
    with col2:
        st.markdown("**Translation (with errors)**")
        st.text_area("Translation", value=item.presented_text, height=100, disabled=True, key="review_tgt")

    # Reference
    st.markdown("**Reference Translation**")
    st.text(item.reference_translation)

    # Error manifest
    st.subheader("Error Manifest")
    for i, err in enumerate(item.errors):
        with st.expander(
            f"Error {i+1}: {TAG_LABELS.get(err.primary_tag, err.primary_tag)} "
            f"({err.severity}) — \"{err.injected_text if hasattr(err, 'injected_text') else ''}\"",
            expanded=i == 0,
        ):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.selectbox(
                    "Category", [t.value for t in PrimaryTag],
                    index=[t.value for t in PrimaryTag].index(err.primary_tag)
                    if err.primary_tag in [t.value for t in PrimaryTag] else 0,
                    key=f"err_cat_{i}",
                )
            with col2:
                st.text_input("Error type", value=err.error_type, key=f"err_type_{i}")
            with col3:
                st.selectbox(
                    "Severity", [s.value for s in Severity],
                    index=[s.value for s in Severity].index(err.severity)
                    if err.severity in [s.value for s in Severity] else 0,
                    key=f"err_sev_{i}",
                )

            if hasattr(err, "injected_text"):
                st.text_input("Error text", value=err.injected_text, key=f"err_text_{i}")
            st.text_input("Correct text", value=err.original_text, key=f"err_orig_{i}")

            # Explanation layers
            if hasattr(err, "explanation") and err.explanation:
                st.markdown("**Layer 1 — Contrastive**")
                st.text_area(
                    "MT interpretation", value=err.explanation.mt_interpretation,
                    key=f"l1_mt_{i}", height=60,
                )
                st.text_area(
                    "Actual meaning", value=err.explanation.actual_meaning,
                    key=f"l1_actual_{i}", height=60,
                )

            if hasattr(err, "system_behavior") and err.system_behavior:
                st.markdown("**Layer 2a — Conceptual**")
                st.text_area(
                    "Error mechanism", value=err.system_behavior.error_mechanism,
                    key=f"l2a_{i}", height=60,
                )

    # Teacher notes
    st.subheader("Teacher Notes")
    notes = st.text_area("Internal notes", value=item.teacher_notes or "", key="teacher_notes")

    # Action buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🟢 Approve & Publish", type="primary", use_container_width=True):
            items_store.update(item.item_id, AssessmentItem, {
                "item_status": "published",
                "teacher_notes": notes,
            })
            st.success("Item published!")
            st.rerun()
    with col2:
        if st.button("🟠 Save as Reviewed", use_container_width=True):
            items_store.update(item.item_id, AssessmentItem, {
                "item_status": "reviewed",
                "teacher_notes": notes,
            })
            st.success("Item saved as reviewed.")
            st.rerun()
    with col3:
        if st.button("🔴 Reject", use_container_width=True):
            items_store.update(item.item_id, AssessmentItem, {
                "item_status": "retired",
                "teacher_notes": notes,
            })
            st.warning("Item rejected.")
            st.rerun()


# ── Published Items ──────────────────────────────────────────────────────────


def _page_published_items():
    st.header("📋 Published Items")

    items = items_store.list_all(
        AssessmentItem, filter_fn=lambda i: i.item_status == "published"
    )

    if not items:
        st.info("No published items yet. Approve items from the Review Queue.")
        return

    data = []
    for item in items:
        data.append({
            "Item ID": item.item_id[:12],
            "Domain": item.domain,
            "Direction": f"{item.source_lang}→{item.target_lang}",
            "Errors": len(item.errors),
            "Difficulty": item.difficulty_level,
            "Source": item.source_text[:60],
        })
    st.dataframe(data, use_container_width=True)


# ── Exercise Builder ─────────────────────────────────────────────────────────


def _page_exercise_builder():
    st.header("📚 Exercise Builder")

    tab_create, tab_manage = st.tabs(["Create Exercise", "Manage Exercises"])

    with tab_create:
        _exercise_create_form()

    with tab_manage:
        _exercise_manage()


def _exercise_create_form():
    """Exercise creation form."""
    # Published items for selection
    items = items_store.list_all(
        AssessmentItem, filter_fn=lambda i: i.item_status == "published"
    )

    if not items:
        st.info("No published items available. Publish items from the Review Queue first.")
        return

    # Item selection
    st.subheader("Select Items")
    col_filter, col_items = st.columns([1, 2])

    with col_filter:
        domain_filter = st.selectbox("Domain", ["All"] + list(set(i.domain for i in items)))

    filtered_items = items
    if domain_filter != "All":
        filtered_items = [i for i in items if i.domain == domain_filter]

    with col_items:
        item_options = {
            f"{i.item_id[:8]} | {i.domain} | {len(i.errors)} errors | Diff {i.difficulty_level}": i.item_id
            for i in filtered_items
        }
        selected = st.multiselect("Items", list(item_options.keys()))
        selected_ids = [item_options[s] for s in selected]

    st.divider()

    # Configuration
    st.subheader("Exercise Configuration")

    col1, col2 = st.columns(2)
    with col1:
        ex_name = st.text_input("Exercise name", placeholder="e.g., Introduction to Error Detection")
        ex_mode = st.selectbox("Mode", ["evaluation", "postediting", "both"])
        ex_level = st.selectbox(
            "Scaffolding Level",
            ["navigator", "guided", "independent", "expert"],
            index=2,
        )
    with col2:
        ex_just = st.selectbox("Justification type", ["free_text", "structured", "both"])
        ex_order = st.selectbox("Item ordering", ["manual", "difficulty", "random"])
        ex_domain = st.text_input("Domain label", placeholder="e.g., Parliamentary")
        ex_direction = st.text_input("Direction", placeholder="e.g., FR→EN")

    # Level-specific options
    if ex_level == "navigator":
        false_ratio = st.slider("False annotation ratio (L0)", 0.0, 0.5, 0.25, 0.05)
    else:
        false_ratio = 0.0

    if ex_level == "expert":
        clean_ratio = st.slider("Clean segment ratio (L3)", 0.0, 0.4, 0.2, 0.05)
    else:
        clean_ratio = 0.0

    # Assignment
    st.subheader("Assign To")
    classes = list_classes()
    class_options = {c.class_name: c.class_id for c in classes}
    assign_class = st.selectbox("Class", ["None"] + list(class_options.keys()))

    if st.button("Create Exercise", type="primary"):
        if not ex_name:
            st.warning("Please provide an exercise name.")
            return
        if not selected_ids:
            st.warning("Please select at least one item.")
            return

        exercise = Exercise(
            exercise_id=str(uuid4()),
            name=ex_name,
            mode=ex_mode,
            level=AnnotationLevel(ex_level),
            item_ids=selected_ids,
            justification_type=ex_just,
            item_ordering=ex_order,
            domain=ex_domain,
            direction=ex_direction,
            false_annotation_ratio=false_ratio,
            clean_segment_ratio=clean_ratio,
        )
        exercises_store.save(exercise)

        # Assign to class
        if assign_class != "None":
            class_id = class_options[assign_class]
            exercise.assigned_to_class = class_id
            students = list_students(class_id)
            for student in students:
                assignment = ExerciseAssignment(
                    assignment_id=str(uuid4()),
                    exercise_id=exercise.exercise_id,
                    student_id=student.student_id,
                )
                assignments_store.save(assignment)
                exercise.assigned_to_students.append(student.student_id)
            exercises_store.save(exercise)

        st.success(f"Exercise '{ex_name}' created!")


def _exercise_manage():
    """List and manage existing exercises."""
    exercises = exercises_store.list_all(Exercise)

    if not exercises:
        st.info("No exercises created yet.")
        return

    for ex in exercises:
        with st.expander(f"{ex.name} | {ex.level} | {ex.mode} | {len(ex.item_ids)} items"):
            st.write(f"**ID:** {ex.exercise_id}")
            st.write(f"**Level:** {ex.level} | **Mode:** {ex.mode}")
            st.write(f"**Items:** {len(ex.item_ids)} | **Justification:** {ex.justification_type}")
            st.write(f"**Assigned to:** {len(ex.assigned_to_students)} students")

            if st.button("Delete", key=f"del_{ex.exercise_id}"):
                exercises_store.delete(ex.exercise_id)
                st.rerun()


# ── Class Management ─────────────────────────────────────────────────────────


def _page_class_management():
    st.header("👥 Class Management")

    tab_students, tab_create = st.tabs(["Student Accounts", "Create Class"])

    with tab_students:
        _class_students_view()

    with tab_create:
        _class_create_form()


def _class_students_view():
    """Student accounts management."""
    classes = list_classes()
    if not classes:
        st.info("No classes created yet.")
        return

    class_options = {c.class_name: c.class_id for c in classes}
    selected_class_name = st.selectbox("Class", list(class_options.keys()))
    class_id = class_options[selected_class_name]

    # Action buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("+ Add Student"):
            st.session_state["show_add_student"] = True
    with col2:
        uploaded_csv = st.file_uploader("Import CSV", type=["csv"], key="csv_import")
        if uploaded_csv:
            import csv
            import io
            content = uploaded_csv.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            created = 0
            for row in reader:
                try:
                    create_account(
                        username=row["username"].strip(),
                        display_name=row["display_name"].strip(),
                        password=row["password"].strip(),
                        class_id=class_id,
                    )
                    created += 1
                except (ValueError, KeyError):
                    continue
            st.success(f"Imported {created} students.")

    # Add student form
    if st.session_state.get("show_add_student"):
        with st.form("add_student_form"):
            st.subheader("Add Student")
            new_username = st.text_input("Username")
            new_display = st.text_input("Display name")
            new_password = st.text_input("Password", type="password")
            if st.form_submit_button("Create Account"):
                if new_username and new_display and new_password:
                    try:
                        create_account(new_username, new_display, new_password, class_id)
                        st.success(f"Created account for {new_display}.")
                        st.session_state["show_add_student"] = False
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    # Student table
    students = list_students(class_id)
    if not students:
        st.info("No students in this class yet. Add students above.")
        return

    # Consent summary
    consent_given = sum(1 for s in students if s.consent is not None and not s.consent.withdrawn)
    consent_pending = sum(1 for s in students if s.consent is None)
    consent_declined = sum(
        1 for s in students
        if s.consent is not None and not s.consent.tier1_research_data and not s.consent.withdrawn
    )
    st.markdown(
        f"**Research consent:** {consent_given} consented (Tier 1) | "
        f"{consent_pending} pending | {consent_declined} declined"
    )

    level_options = [l.value for l in AnnotationLevel]

    # Table header
    hcol1, hcol2, hcol3, hcol4, hcol5 = st.columns([2, 2, 1, 1, 1])
    with hcol1:
        st.markdown("**Username**")
    with hcol2:
        st.markdown("**Name**")
    with hcol3:
        st.markdown("**Level**")
    with hcol4:
        st.markdown("**Consent**")
    with hcol5:
        st.markdown("**Active**")

    for student in students:
        col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
        with col1:
            st.write(f"**{student.username}**")
        with col2:
            st.write(student.display_name)
        with col3:
            new_level = st.selectbox(
                "Level",
                level_options,
                index=level_options.index(student.current_level)
                if student.current_level in level_options else 0,
                key=f"level_{student.student_id}",
                label_visibility="collapsed",
            )
            if new_level != student.current_level:
                update_student_levels(
                    student.student_id,
                    current_level=AnnotationLevel(new_level),
                    allowed_levels=[AnnotationLevel(l) for l in level_options[:level_options.index(new_level) + 1]],
                )
        with col4:
            if student.consent is None:
                st.write("⏳ Pending")
            elif student.consent.withdrawn:
                st.write("🔴 Withdrawn")
            elif student.consent.tier1_research_data:
                tier_label = "T1"
                if student.consent.tier2_publication_excerpts:
                    tier_label = "T1+T2"
                st.write(f"✅ {tier_label}")
            else:
                st.write("➖ Declined")
        with col5:
            st.write(f"{'🟢' if student.is_active else '🔴'}")


def _class_create_form():
    """Create a new class group."""
    with st.form("create_class_form"):
        st.subheader("Create New Class")
        name = st.text_input("Class name", placeholder="e.g., MT Post-Editing 2026 — Group A")
        levels = st.multiselect(
            "Default levels",
            [l.value for l in AnnotationLevel],
            default=[AnnotationLevel.NAVIGATOR, AnnotationLevel.GUIDED],
        )
        if st.form_submit_button("Create Class"):
            if name:
                create_class(name, [AnnotationLevel(l) for l in levels])
                st.success(f"Class '{name}' created!")
                st.rerun()


# ── Analytics Dashboard ──────────────────────────────────────────────────────


def _page_analytics():
    st.header("📊 Analytics Dashboard")

    tab_class, tab_student, tab_blindspot = st.tabs(
        ["Class Overview", "Individual Students", "ToM Blind Spot Analysis"]
    )

    with tab_class:
        st.info(
            "Class analytics will appear here once students complete exercises. "
            "Charts include: detection rate by MQM category, skill radar, "
            "over-editing tendency, and justification quality."
        )
        # Placeholder: will be implemented with plotly charts in P3

    with tab_student:
        st.info(
            "Select a student to view individual performance. "
            "Includes comparison against class average and blind spot alerts."
        )

    with tab_blindspot:
        st.info(
            "ToM Blind Spot Analysis — MQM x ToM heatmap with alert cards "
            "for systematic weaknesses. Coming in Phase 3."
        )


# ── Settings ─────────────────────────────────────────────────────────────────


def _page_settings():
    st.header("⚙️ Settings")

    tab_api, tab_mt, tab_system = st.tabs(["API Credentials", "MT Systems", "System Configuration"])

    with tab_api:
        _settings_api_credentials()

    with tab_mt:
        _settings_mt_systems()

    with tab_system:
        _settings_system_config()


def _settings_api_credentials():
    """API credentials management."""
    import os

    st.subheader("MT Systems")

    providers = {
        "Google Translate": {"env": "GOOGLE_TRANSLATE_API_KEY"},
        "DeepL": {"env": "DEEPL_AUTH_KEY"},
    }

    for name, info in providers.items():
        with st.expander(name):
            env_val = os.environ.get(info["env"], "")
            source = "Env var" if env_val else "Not configured"
            st.write(f"**Source:** {source}")
            if env_val:
                st.text_input("API Key", value="•" * 20, type="password", key=f"api_{name}")
                st.success("✓ Configured via environment variable")
            else:
                st.text_input("API Key", placeholder="Enter API key...", key=f"api_{name}")
                st.warning("⚠️ Not configured")

            if st.button("Test Connection", key=f"test_{name}"):
                st.info(f"Testing {name} connection... (feature coming in v2)")

    st.subheader("LLM Services")

    llm_providers = {
        "OpenAI (GPT-4.1)": {"env": "OPENAI_API_KEY"},
        "Anthropic (Claude)": {"env": "ANTHROPIC_API_KEY"},
        "Together.ai": {"env": "TOGETHER_API_KEY"},
    }

    for name, info in llm_providers.items():
        with st.expander(name):
            env_val = os.environ.get(info["env"], "")
            source = "Env var" if env_val else "Not configured"
            st.write(f"**Source:** {source}")
            if env_val:
                st.success("✓ Configured via environment variable")
            else:
                st.warning("⚠️ Not configured")


def _settings_mt_systems():
    """MT system toggle configuration."""
    mt_config = _load_mt_config()
    systems = mt_config.get("mt_systems", {})

    for name, config in systems.items():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.write(f"**{name}**")
        with col2:
            st.write(config.get("type", ""))
        with col3:
            enabled = st.checkbox(
                "Enabled", value=config.get("enabled", False), key=f"mt_sys_{name}"
            )


def _settings_system_config():
    """General system configuration."""
    config = _load_config()
    server = config.get("server", {})

    st.subheader("Student App")
    st.number_input("Port", value=server.get("student_ui_port", 7860), key="student_port")
    st.checkbox("Enable share link (Gradio share=True)", value=True, key="share_enabled")

    st.subheader("Error Injection")
    injection = config.get("error_injection", {})
    st.number_input(
        "Clean span ratio", value=injection.get("clean_span_ratio", 0.25),
        min_value=0.0, max_value=1.0, step=0.05, key="clean_ratio",
    )

    st.subheader("Data")
    st.text_input("Data directory", value=str(DATA_DIR), disabled=True)
    st.write(f"Items: {items_store.count()} | Exercises: {exercises_store.count()}")

    if st.button("Save Settings"):
        st.info("Settings persistence coming in v2.")


if __name__ == "__main__":
    main()
