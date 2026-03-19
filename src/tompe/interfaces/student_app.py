"""Gradio student interface for ToM-PE.

Provides: login, exercise list, core annotation workflow (3 phases),
span selection, MQM classification, justification, and feedback display.
Supports L0-L3 scaffolding levels, evaluation and post-editing modes.
"""

import json
from typing import Any
from uuid import uuid4

import gradio as gr

from tompe.interfaces.api_client import APIError, ToMPEClient
from tompe.interfaces.components.colors import (
    STUDENT_PILL_CATEGORIES,
    TAG_COLORS,
    TAG_LABELS,
)
from tompe.interfaces.components.span_selector import (
    render_annotation_chips,
    render_text_with_highlights,
)
from tompe.schemas.enums import PrimaryTag, Severity

# ── Globals ──────────────────────────────────────────────────────────────────

api = ToMPEClient()

# Subtypes per primary tag (from MQM taxonomy)
SUBTYPES: dict[str, list[str]] = {
    PrimaryTag.MISTRANSLATION: [
        "false_cognate", "word_sense", "number_error", "literal_translation",
        "negation", "ambiguity", "other",
    ],
    PrimaryTag.OMISSION: ["partial_omission", "full_omission", "qualifier_dropped"],
    PrimaryTag.ADDITION: ["hallucination", "repetition", "over_specification"],
    PrimaryTag.GRAMMAR: [
        "agreement", "tense_mood", "word_order", "article", "preposition", "other",
    ],
    PrimaryTag.TERMINOLOGY: ["wrong_term", "inconsistent_term", "missing_term"],
    PrimaryTag.STYLE: ["register", "unidiomatic", "awkward", "verbosity"],
    PrimaryTag.LOCALE: ["date_format", "number_format", "currency", "measurement"],
    PrimaryTag.UNTRANSLATED: ["full_segment", "partial_segment", "proper_noun"],
}

# Error type guide content (spec §3.3.3)
ERROR_GUIDE: dict[str, dict[str, str]] = {
    PrimaryTag.MISTRANSLATION: {
        "definition": "The translation conveys a different meaning than the source.",
        "example": 'FR "sensible" -> EN "sensible" (should be "sensitive")',
    },
    PrimaryTag.OMISSION: {
        "definition": "Content present in the source is missing from the translation.",
        "example": '"Minister of Health" instead of "Minister of Health and Prevention"',
    },
    PrimaryTag.ADDITION: {
        "definition": "The translation includes content not present in the source.",
        "example": "Adding a qualifier or phrase that doesn't exist in the original.",
    },
    PrimaryTag.GRAMMAR: {
        "definition": "The translation violates grammatical rules of the target language.",
        "example": '"The ministers has announced" (subject-verb agreement error)',
    },
    PrimaryTag.TERMINOLOGY: {
        "definition": "A domain-specific term is incorrect or inconsistent with reference terminology.",
        "example": '"regulation" instead of "directive" (EU legal terminology)',
    },
    PrimaryTag.STYLE: {
        "definition": "The translation is grammatical but reads unnaturally or uses inappropriate formality.",
        "example": "Using informal language in a legal document.",
    },
    PrimaryTag.LOCALE: {
        "definition": "Formatting (dates, numbers, currency) does not match target locale conventions.",
        "example": '"3/15/2026" instead of "15/03/2026" for EU context.',
    },
    PrimaryTag.UNTRANSLATED: {
        "definition": "Source language text left untranslated in the target.",
        "example": "French phrase left in the English translation.",
    },
}


# ── Helper functions ─────────────────────────────────────────────────────────


def _build_exercise_card(assignment: dict, exercise: dict) -> str:
    """Build HTML card for an exercise in the list view."""
    status = assignment.get("status", "not_started")
    level = exercise.get("level", "independent")
    mode = exercise.get("mode", "evaluation")
    name = exercise.get("name", "Unnamed Exercise")
    n_items = len(exercise.get("item_ids", []))
    domain = exercise.get("domain", "")
    direction = exercise.get("direction", "")
    score = assignment.get("score")
    current = assignment.get("current_item_index", 0)

    level_labels = {
        "navigator": "L0 Navigator", "guided": "L1 Guided",
        "independent": "L2 Independent", "expert": "L3 Expert",
    }
    mode_labels = {"evaluation": "Evaluation", "postediting": "Post-Editing", "both": "Both"}

    status_html = {
        "not_started": '<span style="color:#f59e0b">&#9679; Not started</span>',
        "in_progress": f'<span style="color:#3b82f6">&#9679; In progress ({current}/{n_items})</span>',
        "completed": f'<span style="color:#22c55e">&#10003; Completed{f" — Score: {score}%" if score else ""}</span>',
    }.get(status, status)

    btn_text = {"not_started": "Start Exercise", "in_progress": "Continue", "completed": "Review Feedback"}
    btn = btn_text.get(status, "Open")

    meta_parts = []
    if domain:
        meta_parts.append(domain)
    if direction:
        meta_parts.append(direction)
    meta_str = " | ".join(meta_parts)

    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;background:white;">
        <div style="font-weight:600;font-size:16px;margin-bottom:6px;">{name}</div>
        <div style="font-size:14px;color:#6b7280;margin-bottom:4px;">
            Level: {level_labels.get(level, level)} | Mode: {mode_labels.get(mode, mode)}
        </div>
        <div style="font-size:14px;color:#6b7280;margin-bottom:8px;">
            Items: {n_items}{f" | {meta_str}" if meta_str else ""}
        </div>
        <div style="font-size:14px;">{status_html}</div>
    </div>
    """


def _build_pill_buttons_html() -> str:
    """Build HTML for the MQM category pill buttons."""
    pills = []
    for tag in STUDENT_PILL_CATEGORIES:
        colors = TAG_COLORS.get(tag, {"dot": "#666"})
        label = TAG_LABELS.get(tag, tag)
        pills.append(
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'padding:6px 14px;border-radius:16px;border:2px solid #e5e7eb;'
            f'background:white;cursor:pointer;font-size:14px;margin:3px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;'
            f'background:{colors["dot"]}"></span>{label}</span>'
        )
    return '<div style="display:flex;flex-wrap:wrap;gap:2px;">' + "".join(pills) + "</div>"


def _build_feedback_html(feedback_data: dict) -> str:
    """Build HTML for the feedback phase (Phase 3)."""
    summary = feedback_data.get("summary", {})
    errors = feedback_data.get("errors", [])
    fps = feedback_data.get("false_positives", [])

    # Summary bar
    html = f"""
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px;margin-bottom:16px;">
        <div style="font-weight:600;font-size:16px;margin-bottom:8px;">Results</div>
        <div style="display:flex;gap:24px;font-size:14px;">
            <span>Detected: <strong>{summary.get("detected", 0)}/{summary.get("total_errors", 0)}</strong></span>
            <span style="color:#ef4444;">Missed: <strong>{summary.get("missed", 0)}</strong></span>
            <span style="color:#f59e0b;">False positives: <strong>{summary.get("false_positives", 0)}</strong></span>
            <span>Score: <strong>{summary.get("score_pct", 0)}%</strong></span>
        </div>
    </div>
    """

    # Per-error cards
    for err in errors:
        detected = err.get("detected", False)
        tag = err.get("primary_tag", "")
        label = TAG_LABELS.get(tag, tag)
        colors = TAG_COLORS.get(tag, {"dot": "#666", "highlight": "#f3f4f6"})
        severity = err.get("severity", "")
        status_icon = "&#10003;" if detected else "&#10007;"
        status_color = "#22c55e" if detected else "#ef4444"
        status_text = "Found" if detected else "Missed"

        html += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                <span style="color:{status_color};font-size:18px;font-weight:bold;">{status_icon}</span>
                <span style="font-weight:600;">{status_text}</span>
                <span style="background:{colors['highlight']};color:{colors['dot']};padding:2px 8px;border-radius:4px;font-size:13px;">{label}</span>
                <span style="color:#6b7280;font-size:13px;">{severity}</span>
            </div>
            <div style="font-size:14px;color:#374151;margin-bottom:4px;">
                <em>"{err.get("span_text", "") or err.get("original_text", "")}"</em>
                {f' &rarr; <em>"{err.get("original_text", "")}"</em>' if detected and err.get("original_text") else ""}
            </div>
        """

        # Student justification (shown first)
        just = err.get("student_justification")
        if just:
            html += '<div style="background:#f0fdf4;border-left:3px solid #86efac;padding:8px 12px;margin:8px 0;font-size:14px;">'
            html += "<strong>Your reasoning:</strong><br>"
            if just.get("text"):
                html += just["text"]
            else:
                parts = []
                if just.get("mt_misunderstanding"):
                    parts.append(f"<strong>MT misunderstanding:</strong> {just['mt_misunderstanding']}")
                if just.get("author_intent"):
                    parts.append(f"<strong>Author intent:</strong> {just['author_intent']}")
                if just.get("reader_impact"):
                    parts.append(f"<strong>Reader impact:</strong> {just['reader_impact']}")
                html += "<br>".join(parts)
            html += "</div>"

        # Layer 1: Contrastive explanation
        l1 = err.get("layer1")
        if l1:
            html += """
            <div style="background:#eff6ff;border-left:3px solid #93c5fd;padding:8px 12px;margin:8px 0;font-size:14px;">
                <strong>Explanation:</strong><br>
            """
            html += f"<strong>MT interpretation:</strong> {l1.get('mt_interpretation', '')}<br>"
            html += f"<strong>Actual meaning:</strong> {l1.get('actual_meaning', '')}<br>"
            html += f"<strong>Reader impact:</strong> {l1.get('reader_impact', '')}<br>"
            html += f"<strong>Correction:</strong> {l1.get('correction_rationale', '')}"
            html += "</div>"

        # Layer 2a: How It Works
        l2a = err.get("layer2a")
        if l2a:
            html += """
            <details style="margin:8px 0;">
                <summary style="cursor:pointer;font-weight:600;font-size:14px;color:#6b7280;">How It Works</summary>
                <div style="background:#fdf4ff;border-left:3px solid #d8b4fe;padding:8px 12px;margin-top:4px;font-size:14px;">
            """
            html += f"{l2a.get('error_mechanism', '')}<br>"
            if l2a.get("pattern_generalization"):
                html += f"<em>{l2a['pattern_generalization']}</em>"
            html += "</div></details>"

        # Layer 2b: Under the Hood
        l2b = err.get("layer2b")
        if l2b:
            html += """
            <details style="margin:8px 0;">
                <summary style="cursor:pointer;font-weight:600;font-size:14px;color:#9ca3af;">Under the Hood</summary>
                <div style="background:#f5f5f4;border-left:3px solid #a8a29e;padding:8px 12px;margin-top:4px;font-size:14px;">
            """
            html += f"{l2b.get('technical_description', '')}"
            if l2b.get("key_concepts"):
                html += f"<br><strong>Key concepts:</strong> {', '.join(l2b['key_concepts'])}"
            html += "</div></details>"

        html += "</div>"

    # False positive cards
    for fp in fps:
        html += f"""
        <div style="border:1px solid #fde68a;border-radius:8px;padding:12px;margin-bottom:8px;background:#fffbeb;">
            <span style="color:#f59e0b;font-weight:bold;">False positive</span> —
            <span style="font-size:14px;">This span does not contain an error.</span>
        </div>
        """

    return html


def _build_error_guide_html() -> str:
    """Build the Error Types Guide accordion content."""
    html = ""
    for tag in STUDENT_PILL_CATEGORIES:
        colors = TAG_COLORS.get(tag, {"dot": "#666"})
        label = TAG_LABELS.get(tag, tag)
        guide = ERROR_GUIDE.get(tag, {})

        html += f"""
        <div style="margin-bottom:12px;padding:8px 0;border-bottom:1px solid #f3f4f6;">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                <span style="width:10px;height:10px;border-radius:50%;background:{colors['dot']};display:inline-block;"></span>
                <strong>{label}</strong>
            </div>
            <div style="font-size:14px;color:#374151;margin-left:16px;">
                {guide.get("definition", "")}
            </div>
            <div style="font-size:13px;color:#6b7280;margin-left:16px;font-style:italic;">
                Example: {guide.get("example", "")}
            </div>
        </div>
        """
    return html


# ── Main app builder ─────────────────────────────────────────────────────────


def build_student_app() -> gr.Blocks:
    """Build the Gradio student interface."""

    with gr.Blocks(
        title="ToM-PE — Student",
        theme=gr.themes.Soft(),
        css="""
        .pill-btn { border-radius: 16px !important; font-size: 14px !important; }
        .phase-indicator { font-size: 14px; color: #6b7280; padding: 8px 0; }
        """,
    ) as app:
        # ── State ────────────────────────────────────────────────────────
        session_token = gr.State(None)
        student_info = gr.State({})
        current_assignment = gr.State(None)
        current_exercise = gr.State(None)
        current_item = gr.State(None)
        current_item_idx = gr.State(0)
        annotations_state = gr.State([])  # List of annotation dicts
        current_selection = gr.State(None)  # Current text selection
        current_phase = gr.State("annotate")  # annotate/justify/feedback
        current_response_id = gr.State(None)

        # ── Login view ───────────────────────────────────────────────────
        with gr.Column(visible=True) as login_view:
            gr.Markdown("# ToM-PE\n### Translation Quality Training")
            with gr.Column(scale=1):
                login_username = gr.Textbox(label="Username", placeholder="Enter your username")
                login_password = gr.Textbox(
                    label="Password", type="password", placeholder="Enter your password"
                )
                login_btn = gr.Button("Log In", variant="primary")
                login_error = gr.Markdown(visible=False)
                gr.Markdown(
                    "*Forgot password? Contact your instructor.*",
                    elem_classes=["phase-indicator"],
                )

        # ── Consent view ─────────────────────────────────────────────────
        with gr.Column(visible=False) as consent_view:
            gr.Markdown("# Research Participation & Data Consent")
            consent_text_display = gr.Markdown("")
            gr.Markdown("---")
            gr.Markdown(
                "**Your decision does not affect your grade or access to the platform.** "
                "You may use ToM-PE for your coursework regardless of your choices below."
            )

            with gr.Group():
                consent_tier1 = gr.Checkbox(
                    label=(
                        "Tier 1 — I consent to the use of my interaction and annotation data "
                        "(error classifications, scores, timing, progression patterns) for "
                        "research purposes. Results are reported anonymously or as group averages."
                    ),
                    value=False,
                )
                consent_tier2 = gr.Checkbox(
                    label=(
                        "Tier 2 — I consent to the use of short, fully anonymized excerpts "
                        "from my justification texts in academic publications."
                    ),
                    value=False,
                )

            gr.Markdown(
                "*You may withdraw your consent at any time from your profile settings. "
                "If you withdraw, your data will be excluded from all future analyses.*"
            )

            with gr.Row():
                consent_submit_btn = gr.Button(
                    "Continue to ToM-PE", variant="primary", scale=2
                )
                consent_decline_info = gr.Markdown(
                    "*You can leave both boxes unchecked and still continue — "
                    "your data simply won't be used for research.*",
                    elem_classes=["phase-indicator"],
                )

        # ── Main view ────────────────────────────────────────────────────
        with gr.Column(visible=False) as main_view:
            # Header
            with gr.Row():
                gr.Markdown("## ToM-PE")
                header_user = gr.Markdown("", elem_id="header-user")

            with gr.Tabs() as main_tabs:
                # ── Exercise List Tab ────────────────────────────────────
                with gr.TabItem("Exercises", id=0):
                    exercises_html = gr.HTML("<p>Loading exercises...</p>")
                    with gr.Row():
                        exercise_selector = gr.Dropdown(
                            label="Select exercise to start/continue",
                            choices=[],
                            interactive=True,
                        )
                        start_btn = gr.Button("Open Exercise", variant="primary")

                # ── Exercise Item Tab ────────────────────────────────────
                with gr.TabItem("Exercise", id=1) as exercise_tab:
                    # Exercise header
                    exercise_header = gr.Markdown("")

                    # Navigation
                    with gr.Row():
                        prev_btn = gr.Button("< Previous", size="sm", scale=1)
                        progress_html = gr.HTML(
                            '<div style="text-align:center;color:#6b7280;">Item 0 of 0</div>'
                        )
                        next_btn = gr.Button("Next >", size="sm", scale=1)

                    # Phase indicator
                    phase_html = gr.HTML(
                        '<div class="phase-indicator" style="text-align:center;">'
                        '<strong style="color:#3b82f6;">1 Annotate</strong> -> '
                        '2 Justify -> 3 Feedback</div>'
                    )

                    # Task description
                    task_desc = gr.Markdown("")

                    # Source text
                    gr.Markdown("### Source Text")
                    source_html = gr.HTML("")

                    # Translation text with span selector
                    gr.Markdown("### Translation")
                    translation_html = gr.HTML("")

                    # Hidden textbox for span selection JS → Python communication
                    span_output = gr.Textbox(
                        visible=False, elem_id="span-output-main", label="span_output"
                    )

                    # Annotation chips
                    chips_html = gr.HTML("")

                    # ── Error Types Guide (collapsible) ──────────────────
                    with gr.Accordion("Error Types Guide", open=False):
                        gr.HTML(_build_error_guide_html())

                    # ── Classification panel (Phase 1) ───────────────────
                    with gr.Column(visible=True) as classification_panel:
                        selection_label = gr.Markdown(
                            "*Select text in the translation above to mark an error.*"
                        )

                        # Category pills
                        gr.Markdown("**Error Category:**")
                        with gr.Row():
                            cat_buttons = {}
                            for tag in STUDENT_PILL_CATEGORIES:
                                label = TAG_LABELS.get(tag, tag)
                                cat_buttons[tag] = gr.Button(
                                    f"● {label}",
                                    size="sm",
                                    elem_classes=["pill-btn"],
                                )

                        selected_category = gr.State(None)

                        # Subtypes (shown after category selection)
                        subtype_label = gr.Markdown("", visible=False)
                        subtype_dropdown = gr.Dropdown(
                            label="Subtype", choices=[], visible=False, interactive=True
                        )

                        # Severity
                        severity_radio = gr.Radio(
                            choices=["minor", "major", "critical"],
                            label="Severity",
                            value="major",
                        )

                        with gr.Row():
                            add_error_btn = gr.Button("Add Error", variant="primary")
                            cancel_btn = gr.Button("Cancel")

                        with gr.Row():
                            proceed_justify_btn = gr.Button(
                                "Proceed to Justification ->",
                                variant="primary",
                            )

                    # ── Justification panel (Phase 2) ────────────────────
                    with gr.Column(visible=False) as justification_panel:
                        gr.Markdown("### Justify Your Reasoning")
                        gr.Markdown(
                            "*Before seeing the feedback, explain your reasoning for each annotation.*"
                        )

                        # Mode A: Free-text
                        with gr.Column(visible=True) as justify_freetext:
                            justify_text = gr.Textbox(
                                label="Explain your reasoning",
                                lines=4,
                                placeholder=(
                                    "What did the MT system misunderstand? "
                                    "What was the author's intent? "
                                    "How would a reader misinterpret this?"
                                ),
                            )

                        # Mode B: Structured ToM
                        with gr.Column(visible=False) as justify_structured:
                            justify_mt = gr.Textbox(
                                label="What did the MT system misunderstand?",
                                lines=2,
                                placeholder="The MT system likely interpreted...",
                            )
                            justify_author = gr.Textbox(
                                label="What was the author's actual intent?",
                                lines=2,
                                placeholder="The author meant...",
                            )
                            justify_reader = gr.Textbox(
                                label="How would a reader misinterpret this?",
                                lines=2,
                                placeholder="A reader would think...",
                            )

                        submit_justify_btn = gr.Button(
                            "Submit & See Feedback", variant="primary"
                        )

                    # ── Feedback panel (Phase 3) ─────────────────────────
                    with gr.Column(visible=False) as feedback_panel:
                        gr.Markdown("### Feedback")
                        feedback_html = gr.HTML("")
                        next_item_btn = gr.Button(
                            "Next Item ->", variant="primary"
                        )

                    # ── Post-editing panel ───────────────────────────────
                    with gr.Column(visible=False) as pe_panel:
                        gr.Markdown("### Edit the Translation")
                        pe_textbox = gr.Textbox(
                            label="Translation — edit directly",
                            lines=6,
                            interactive=True,
                        )
                        pe_changes_html = gr.HTML("")
                        pe_proceed_btn = gr.Button(
                            "Proceed to Justification ->", variant="primary"
                        )

                # ── My Progress Tab ──────────────────────────────────────
                with gr.TabItem("My Progress", id=2):
                    progress_content = gr.HTML(
                        "<p>Complete exercises to see your progress here.</p>"
                    )

        # ── Event handlers ───────────────────────────────────────────────

        def handle_login(username, password):
            """Handle login attempt. Routes to consent form if first login."""
            no_change = (
                gr.update(), gr.update(), gr.update(), gr.update(),
                None, {}, gr.update(), gr.update(), gr.update(), gr.update(),
            )
            if not username or not password:
                return (
                    gr.update(),  # login_view
                    gr.update(),  # consent_view
                    gr.update(),  # main_view
                    gr.update(value="*Please enter both username and password.*", visible=True),
                    None,  # session_token
                    {},  # student_info
                    gr.update(),  # header_user
                    gr.update(),  # exercises_html
                    gr.update(),  # exercise_selector
                    gr.update(),  # consent_text_display
                )
            try:
                data = api.login(username, password)
            except (APIError, Exception) as e:
                msg = e.detail if isinstance(e, APIError) else str(e)
                return (
                    gr.update(), gr.update(), gr.update(),
                    gr.update(value=f"*Login failed: {msg}*", visible=True),
                    None, {}, gr.update(), gr.update(), gr.update(), gr.update(),
                )

            info = {
                "student_id": data["student_id"],
                "display_name": data["display_name"],
                "current_level": data["current_level"],
                "allowed_levels": data["allowed_levels"],
                "token": data["token"],
            }

            # Check if consent is pending
            consent_pending = data.get("consent_pending", False)

            if consent_pending:
                # Load consent text from API
                consent_md = ""
                try:
                    consent_data = api.get_consent_text()
                    consent_md = consent_data.get("text", "")
                except Exception:
                    consent_md = "*Could not load consent form. Please contact your instructor.*"

                return (
                    gr.update(visible=False),  # hide login
                    gr.update(visible=True),  # show consent
                    gr.update(visible=False),  # hide main
                    gr.update(visible=False),  # hide error
                    data["token"],
                    info,
                    gr.update(),  # header_user (not visible yet)
                    gr.update(),  # exercises_html
                    gr.update(),  # exercise_selector
                    gr.update(value=consent_md),  # consent text
                )

            # No consent needed — go straight to main
            exercises_content, choices = _load_exercises(info)

            return (
                gr.update(visible=False),  # hide login
                gr.update(visible=False),  # hide consent
                gr.update(visible=True),  # show main
                gr.update(visible=False),  # hide error
                data["token"],
                info,
                gr.update(value=f"**{data['display_name']}** ({data['current_level']})"),
                gr.update(value=exercises_content),
                gr.update(choices=choices),
                gr.update(),  # consent text (no change)
            )

        def handle_consent_submit(tier1, tier2, student_info):
            """Submit consent decision and transition to main view."""
            # Submit consent to API (whether they checked anything or not)
            try:
                api.submit_consent(tier1, tier2)
            except Exception:
                pass  # Consent submission failure shouldn't block platform use

            # Load exercises and proceed to main view
            exercises_content, choices = _load_exercises(student_info)

            return (
                gr.update(visible=False),  # hide consent
                gr.update(visible=True),  # show main
                gr.update(value=f"**{student_info.get('display_name', '')}** ({student_info.get('current_level', '')})"),
                gr.update(value=exercises_content),
                gr.update(choices=choices),
            )

        def _load_exercises(info: dict) -> tuple[str, list]:
            """Load exercises for the logged-in student."""
            try:
                assignments = api.get_assignments(info["student_id"])
            except Exception:
                return "<p>Could not load exercises.</p>", []

            if not assignments:
                return (
                    '<p style="color:#6b7280;">No exercises assigned yet. '
                    "Your instructor will assign exercises to you.</p>",
                    [],
                )

            html = ""
            choices = []
            for a in assignments:
                try:
                    ex = api.get_exercise(a["exercise_id"])
                    html += _build_exercise_card(a, ex)
                    label = f"{ex['name']} ({a['status']})"
                    choices.append((label, json.dumps({"assignment": a, "exercise": ex})))
                except Exception:
                    continue

            return html, choices

        def handle_start_exercise(selected_json, student_info):
            """Start or continue an exercise."""
            if not selected_json:
                return [gr.update()] * 8

            data = json.loads(selected_json)
            assignment = data["assignment"]
            exercise = data["exercise"]
            item_idx = assignment.get("current_item_index", 0)
            item_ids = exercise.get("item_ids", [])

            if not item_ids:
                return [gr.update()] * 8

            # Load the current item
            try:
                item = api.get_item(item_ids[min(item_idx, len(item_ids) - 1)])
            except Exception:
                item = None

            if not item:
                return [gr.update()] * 8

            # Update assignment status
            if assignment["status"] == "not_started":
                try:
                    api.update_assignment(
                        assignment["assignment_id"],
                        {"status": "in_progress", "started_at": str(__import__("datetime").datetime.now())},
                    )
                except Exception:
                    pass

            level = exercise.get("level", "independent")
            mode = exercise.get("mode", "evaluation")
            task_descriptions = {
                "navigator": (
                    "Pre-annotated errors are highlighted below. Your task is to verify each "
                    "annotation: **confirm** correct ones, **dispute** incorrect ones, and explain "
                    "your reasoning. Some annotations may be incorrect."
                ),
                "guided": (
                    "Approximate error regions are highlighted in yellow. Within each region, "
                    "**select the exact error span** by clicking and dragging. Then classify the "
                    "error type, assign a severity, and explain your reasoning."
                ),
                "independent": (
                    "Read the source text and translation carefully. **Select any text you believe "
                    "contains an error** by clicking and dragging. Classify each error by type and "
                    "severity, then explain your reasoning."
                ),
                "expert": (
                    "Evaluate this translation independently. Note: some segments may be error-free "
                    "— marking a correct segment as erroneous counts against your score."
                ),
            }
            if mode == "postediting":
                task_text = (
                    "Read the source text and translation carefully. **Edit the translation directly** "
                    "to correct any errors. For each significant edit, explain why the change was needed."
                )
            else:
                task_text = task_descriptions.get(level, task_descriptions["independent"])

            # Render source and translation
            source_text = item.get("source_text", "")
            presented_text = item.get("presented_text", "")

            # For L0 Navigator, show pre-annotations
            annotations_for_display = []
            if level == "navigator":
                for ann in item.get("annotations", []):
                    annotations_for_display.append({
                        "span_start": ann.get("span_start", 0),
                        "span_end": ann.get("span_end", 0),
                        "primary_tag": ann.get("primary_tag", ""),
                        "annotation_id": ann.get("error_id", str(uuid4())),
                        "mqm_label": ann.get("mqm_label", ""),
                        "severity_label": ann.get("severity_label", ""),
                    })

            translation_display = render_text_with_highlights(
                presented_text, annotations_for_display, level=level
            )

            n_items = len(item_ids)
            progress = f'<div style="text-align:center;color:#6b7280;">Item {item_idx + 1} of {n_items}</div>'

            header = f"**{exercise['name']}** | Level: {level.title()} | Mode: {mode.title()}"

            show_pe = mode == "postediting"

            return (
                gr.update(selected=1),  # Switch to Exercise tab
                assignment,  # current_assignment
                exercise,  # current_exercise
                item,  # current_item
                item_idx,  # current_item_idx
                gr.update(value=header),  # exercise_header
                gr.update(value=task_text),  # task_desc
                gr.update(
                    value=f'<div style="font-family:Georgia,serif;font-size:16px;line-height:1.8;padding:16px;background:#f9fafb;border-radius:8px;">{source_text}</div>'
                ),  # source_html
                gr.update(value=translation_display),  # translation_html
                gr.update(value=progress),  # progress_html
                [],  # annotations_state reset
                gr.update(value=""),  # chips_html
                gr.update(visible=not show_pe),  # classification_panel
                gr.update(visible=False),  # justification_panel
                gr.update(visible=False),  # feedback_panel
                gr.update(visible=show_pe),  # pe_panel
                gr.update(value=presented_text if show_pe else ""),  # pe_textbox
                "annotate",  # current_phase
            )

        def handle_span_selection(span_data, annotations, current_item):
            """Handle text selection from the span selector JS."""
            if not span_data:
                return annotations, gr.update(), gr.update(), gr.update()

            try:
                data = json.loads(span_data)
            except json.JSONDecodeError:
                return annotations, gr.update(), gr.update(), gr.update()

            # Handle annotation removal
            if "remove" in data:
                ann_id = data["remove"]
                annotations = [a for a in annotations if a.get("annotation_id") != ann_id]
                # Re-render
                text = current_item.get("presented_text", "") if current_item else ""
                html = render_text_with_highlights(text, annotations)
                chips = render_annotation_chips(annotations)
                return annotations, gr.update(value=html), gr.update(value=chips), gr.update()

            # New selection
            return (
                annotations,
                gr.update(),
                gr.update(),
                gr.update(value=f'Classify: **"{data.get("text", "")[:50]}"**'),
            )

        def handle_category_click(tag, current_sel, span_data):
            """Handle MQM category pill button click."""
            subtypes = SUBTYPES.get(tag, [])
            return (
                tag,
                gr.update(visible=bool(subtypes), choices=subtypes, value=subtypes[0] if subtypes else None),
                gr.update(visible=bool(subtypes)),
            )

        def handle_add_error(
            category, subtype, severity, span_data, annotations, current_item
        ):
            """Add a classified error annotation."""
            if not span_data or not category:
                return annotations, gr.update(), gr.update(), gr.update(), gr.update()

            try:
                data = json.loads(span_data)
            except json.JSONDecodeError:
                return annotations, gr.update(), gr.update(), gr.update(), gr.update()

            if "remove" in data:
                return annotations, gr.update(), gr.update(), gr.update(), gr.update()

            ann = {
                "annotation_id": str(uuid4()),
                "span_start": data.get("start", 0),
                "span_end": data.get("end", 0),
                "span_text": data.get("text", ""),
                "primary_tag": category,
                "error_type": subtype or "",
                "severity": severity or "major",
            }
            annotations = annotations + [ann]

            text = current_item.get("presented_text", "") if current_item else ""
            html = render_text_with_highlights(text, annotations)
            chips = render_annotation_chips(annotations)

            return (
                annotations,
                gr.update(value=html),
                gr.update(value=chips),
                gr.update(value=""),  # Clear span output
                gr.update(value="*Select more text or proceed to justification.*"),
            )

        def handle_proceed_to_justify(annotations, current_exercise):
            """Transition from Phase 1 (Annotate) to Phase 2 (Justify)."""
            just_type = "free_text"
            if current_exercise:
                just_type = current_exercise.get("justification_type", "free_text")

            show_free = just_type in ("free_text", "both")
            show_struct = just_type in ("structured", "both")

            return (
                gr.update(visible=False),  # hide classification
                gr.update(visible=True),  # show justification
                gr.update(visible=show_free),
                gr.update(visible=show_struct),
                "justify",
                gr.update(
                    value=(
                        '<div class="phase-indicator" style="text-align:center;">'
                        "1 Annotate -> "
                        '<strong style="color:#3b82f6;">2 Justify</strong> -> '
                        "3 Feedback</div>"
                    )
                ),
            )

        def handle_submit_justify(
            justify_text_val, justify_mt_val, justify_author_val, justify_reader_val,
            annotations, current_item, current_exercise, student_info,
        ):
            """Submit annotations + justifications and get feedback."""
            if not current_item:
                return gr.update(), gr.update(), gr.update(), None, gr.update()

            mode = current_exercise.get("mode", "evaluation") if current_exercise else "evaluation"
            item_id = current_item.get("item_id", "")

            # Build identified errors from annotations
            identified = []
            for ann in annotations:
                identified.append({
                    "span_start": ann["span_start"],
                    "span_end": ann["span_end"],
                    "student_mqm_category": _tag_to_mqm(ann.get("primary_tag", "")),
                    "student_severity": ann.get("severity", "major"),
                    "confidence": "medium",
                })

            # Submit response
            try:
                resp = api.submit_response(
                    item_id=item_id,
                    mode=mode,
                    identified_errors=identified,
                    time_spent_seconds=0,
                )
                response_id = resp.get("response_id")
            except Exception as e:
                return (
                    gr.update(), gr.update(), gr.update(), None,
                    gr.update(value=f'<div style="color:red;">Error: {e}</div>'),
                )

            # Submit justifications
            justifications = []
            if justify_text_val:
                justifications.append({
                    "format": "free_text",
                    "text": justify_text_val,
                })
            if justify_mt_val or justify_author_val or justify_reader_val:
                justifications.append({
                    "format": "structured",
                    "mt_misunderstanding": justify_mt_val or "",
                    "author_intent": justify_author_val or "",
                    "reader_impact": justify_reader_val or "",
                })

            if justifications and response_id:
                try:
                    api.submit_justifications(response_id, justifications)
                except Exception:
                    pass

            # Get feedback
            feedback_content = ""
            if response_id:
                try:
                    fb = api.get_feedback(response_id)
                    feedback_content = _build_feedback_html(fb)
                except Exception as e:
                    feedback_content = f'<div style="color:#6b7280;">Feedback unavailable: {e}</div>'

            return (
                gr.update(visible=False),  # hide justification
                gr.update(visible=True),  # show feedback
                "feedback",  # phase
                response_id,
                gr.update(value=feedback_content),
                gr.update(
                    value=(
                        '<div class="phase-indicator" style="text-align:center;">'
                        "1 Annotate -> 2 Justify -> "
                        '<strong style="color:#3b82f6;">3 Feedback</strong></div>'
                    )
                ),
            )

        def handle_next_item(
            current_item_idx, current_exercise, current_assignment, student_info,
        ):
            """Advance to the next item in the exercise."""
            if not current_exercise:
                return [gr.update()] * 8

            item_ids = current_exercise.get("item_ids", [])
            next_idx = current_item_idx + 1

            if next_idx >= len(item_ids):
                # Exercise complete
                if current_assignment:
                    try:
                        api.update_assignment(
                            current_assignment["assignment_id"],
                            {"status": "completed", "current_item_index": next_idx},
                        )
                    except Exception:
                        pass
                return (
                    next_idx,
                    gr.update(value="<h3>Exercise Complete!</h3><p>Great work. Return to the Exercises tab to see your results.</p>"),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(value=""),
                    gr.update(value=""),
                )

            # Load next item
            try:
                item = api.get_item(item_ids[next_idx])
            except Exception:
                return [gr.update()] * 8

            # Update assignment
            if current_assignment:
                try:
                    api.update_assignment(
                        current_assignment["assignment_id"],
                        {"current_item_index": next_idx},
                    )
                except Exception:
                    pass

            text = item.get("presented_text", "")
            source = item.get("source_text", "")
            n = len(item_ids)

            return (
                next_idx,
                gr.update(value=render_text_with_highlights(text, [])),
                gr.update(visible=True),  # classification
                gr.update(visible=False),  # justification
                gr.update(visible=False),  # feedback
                item,
                gr.update(
                    value=f'<div style="font-family:Georgia,serif;font-size:16px;line-height:1.8;padding:16px;background:#f9fafb;border-radius:8px;">{source}</div>'
                ),
                gr.update(
                    value=f'<div style="text-align:center;color:#6b7280;">Item {next_idx + 1} of {n}</div>'
                ),
                [],  # Reset annotations
                gr.update(value=""),  # Reset chips
                "annotate",
                gr.update(
                    value=(
                        '<div class="phase-indicator" style="text-align:center;">'
                        '<strong style="color:#3b82f6;">1 Annotate</strong> -> '
                        "2 Justify -> 3 Feedback</div>"
                    )
                ),
            )

        # ── Wire up events ───────────────────────────────────────────────

        login_btn.click(
            handle_login,
            inputs=[login_username, login_password],
            outputs=[
                login_view, consent_view, main_view, login_error,
                session_token, student_info, header_user,
                exercises_html, exercise_selector, consent_text_display,
            ],
        )

        # Also login on Enter key in password field
        login_password.submit(
            handle_login,
            inputs=[login_username, login_password],
            outputs=[
                login_view, consent_view, main_view, login_error,
                session_token, student_info, header_user,
                exercises_html, exercise_selector, consent_text_display,
            ],
        )

        # Consent form submission
        consent_submit_btn.click(
            handle_consent_submit,
            inputs=[consent_tier1, consent_tier2, student_info],
            outputs=[
                consent_view, main_view, header_user,
                exercises_html, exercise_selector,
            ],
        )

        start_btn.click(
            handle_start_exercise,
            inputs=[exercise_selector, student_info],
            outputs=[
                main_tabs, current_assignment, current_exercise,
                current_item, current_item_idx, exercise_header,
                task_desc, source_html, translation_html,
                progress_html, annotations_state, chips_html,
                classification_panel, justification_panel,
                feedback_panel, pe_panel, pe_textbox, current_phase,
            ],
        )

        # Span selection handler
        span_output.change(
            handle_span_selection,
            inputs=[span_output, annotations_state, current_item],
            outputs=[annotations_state, translation_html, chips_html, selection_label],
        )

        # Category pill buttons
        for tag, btn in cat_buttons.items():
            btn.click(
                lambda t=tag: handle_category_click(t, None, None),
                outputs=[selected_category, subtype_dropdown, subtype_label],
            )

        add_error_btn.click(
            handle_add_error,
            inputs=[
                selected_category, subtype_dropdown, severity_radio,
                span_output, annotations_state, current_item,
            ],
            outputs=[
                annotations_state, translation_html, chips_html,
                span_output, selection_label,
            ],
        )

        cancel_btn.click(
            lambda: (gr.update(value=""), gr.update(value="*Select text to annotate.*")),
            outputs=[span_output, selection_label],
        )

        proceed_justify_btn.click(
            handle_proceed_to_justify,
            inputs=[annotations_state, current_exercise],
            outputs=[
                classification_panel, justification_panel,
                justify_freetext, justify_structured,
                current_phase, phase_html,
            ],
        )

        submit_justify_btn.click(
            handle_submit_justify,
            inputs=[
                justify_text, justify_mt, justify_author, justify_reader,
                annotations_state, current_item, current_exercise, student_info,
            ],
            outputs=[
                justification_panel, feedback_panel,
                current_phase, current_response_id,
                feedback_html, phase_html,
            ],
        )

        next_item_btn.click(
            handle_next_item,
            inputs=[current_item_idx, current_exercise, current_assignment, student_info],
            outputs=[
                current_item_idx, translation_html,
                classification_panel, justification_panel,
                feedback_panel, current_item,
                source_html, progress_html,
                annotations_state, chips_html,
                current_phase, phase_html,
            ],
        )

    return app


def _tag_to_mqm(tag: str) -> str:
    """Map PrimaryTag to MQMCategory string for API submission."""
    mapping = {
        PrimaryTag.MISTRANSLATION: "accuracy",
        PrimaryTag.OMISSION: "accuracy",
        PrimaryTag.ADDITION: "accuracy",
        PrimaryTag.UNTRANSLATED: "accuracy",
        PrimaryTag.GRAMMAR: "fluency",
        PrimaryTag.SPELLING: "fluency",
        PrimaryTag.PUNCTUATION: "fluency",
        PrimaryTag.TERMINOLOGY: "terminology",
        PrimaryTag.STYLE: "style",
        PrimaryTag.LOCALE: "locale",
    }
    return mapping.get(tag, "accuracy")


def main():
    """Launch the student interface."""
    app = build_student_app()
    app.launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
