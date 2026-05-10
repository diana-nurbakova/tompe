"""Expert MQM annotation tool for ToM-PE pipeline validation (Track C).

Self-contained Gradio app with two phases:
  - Phase A: Blind error annotation (84 items)
  - Phase B: Explanation quality review (24 items, with ground truth)

Items are loaded from JSON files on disk; annotations are saved directly
to per-annotator JSON directories. No dependency on the FastAPI backend.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import gradio as gr

from tompe.interfaces.components.colors import TAG_COLORS, TAG_LABELS
from tompe.interfaces.components.span_selector import (
    SPAN_SELECTOR_CSS,
    SPAN_SELECTOR_JS,
    render_annotation_chips,
    render_text_with_highlights,
)
from tompe.schemas.enums import PrimaryTag, Severity

logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────

ANNOTATION_SET_PATH = Path("data/annotations/annotation_set.json")
EXPLANATION_SET_PATH = Path("data/annotations/explanation_set.json")
ANNOTATIONS_DIR = Path("data/annotations")

# ── All 10 MQM categories ──────────────────────────────────────────────────

ALL_CATEGORIES = [
    PrimaryTag.MISTRANSLATION,
    PrimaryTag.OMISSION,
    PrimaryTag.ADDITION,
    PrimaryTag.GRAMMAR,
    PrimaryTag.TERMINOLOGY,
    PrimaryTag.STYLE,
    PrimaryTag.LOCALE,
    PrimaryTag.UNTRANSLATED,
    PrimaryTag.SPELLING,
    PrimaryTag.PUNCTUATION,
]

# ── Data I/O ────────────────────────────────────────────────────────────────


def load_annotation_set() -> list[dict]:
    """Load annotation items from JSON, sorted by display_order."""
    if not ANNOTATION_SET_PATH.exists():
        logger.warning("Annotation set not found at %s", ANNOTATION_SET_PATH)
        return []
    with open(ANNOTATION_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)
    return sorted(items, key=lambda x: x.get("display_order", 0))


def load_explanation_set() -> list[dict]:
    """Load explanation review items from JSON, sorted by display_order."""
    if not EXPLANATION_SET_PATH.exists():
        logger.warning("Explanation set not found at %s", EXPLANATION_SET_PATH)
        return []
    with open(EXPLANATION_SET_PATH, encoding="utf-8") as f:
        items = json.load(f)
    return sorted(items, key=lambda x: x.get("display_order", 0))


def save_annotation(annotator_id: str, annotation: dict) -> None:
    """Save a single Phase A annotation to disk."""
    out_dir = ANNOTATIONS_DIR / annotator_id
    out_dir.mkdir(parents=True, exist_ok=True)
    item_id = annotation.get("item_id", "unknown")
    path = out_dir / f"{item_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(annotation, f, indent=2, default=str)
    logger.info("Saved annotation for %s to %s", item_id, path)


def save_explanation_rating(annotator_id: str, rating: dict) -> None:
    """Save a single Phase B explanation rating to disk."""
    out_dir = ANNOTATIONS_DIR / annotator_id / "explanation_ratings"
    out_dir.mkdir(parents=True, exist_ok=True)
    item_id = rating.get("item_id", "unknown")
    error_index = rating.get("error_index", 0)
    path = out_dir / f"{item_id}_{error_index}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rating, f, indent=2, default=str)
    logger.info("Saved explanation rating to %s", path)


# ── CSS ─────────────────────────────────────────────────────────────────────

ANNOTATION_APP_CSS = """
.source-box {
    font-family: 'Georgia', serif;
    font-size: 15px;
    line-height: 1.7;
    padding: 14px 18px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    background: #f9fafb;
}
.category-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
    background: white;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s;
}
.category-btn:hover {
    border-color: #93c5fd;
    background: #f0f9ff;
}
.category-btn.selected {
    border-color: #3b82f6;
    background: #eff6ff;
    font-weight: 600;
}
.phase-header {
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}
.timer-display {
    font-family: monospace;
    font-size: 14px;
    color: #6b7280;
    text-align: right;
}
.explanation-card {
    padding: 14px 18px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #fafafa;
    margin-bottom: 10px;
}
.explanation-card h4 {
    margin: 0 0 8px 0;
    font-size: 14px;
    color: #374151;
}
.explanation-card p {
    margin: 4px 0;
    font-size: 14px;
    line-height: 1.6;
}
.error-info-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 600;
    margin-right: 6px;
}
.completion-screen {
    text-align: center;
    padding: 40px 20px;
}
.completion-screen h2 { color: #059669; }
"""

# Browser-side ticker that animates `.timer-display` elements. Each element
# tracks its own start time via `data-start-ms`; clicks on the per-item
# advance buttons reset all timers (annotation §2.4). Wired via
# `gr.Blocks.load(js=...)` below.
ANNOTATION_TIMER_JS = """
() => {
  if (window.__tompeAnnotationTimerInstalled) return;
  window.__tompeAnnotationTimerInstalled = true;
  function fmt(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var mm = String(Math.floor(s / 60)).padStart(2, '0');
    var ss = String(s % 60).padStart(2, '0');
    return mm + ':' + ss;
  }
  function tick() {
    document.querySelectorAll('.timer-display').forEach(function (el) {
      var start = parseInt(el.dataset.startMs || '', 10);
      if (!start || isNaN(start)) {
        start = Date.now();
        el.dataset.startMs = String(start);
      }
      var next = fmt(Date.now() - start);
      if (el.textContent !== next) el.textContent = next;
    });
  }
  function resetAll() {
    var now = String(Date.now());
    document.querySelectorAll('.timer-display').forEach(function (el) {
      el.dataset.startMs = now;
      el.textContent = '00:00';
    });
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest(
      '#btn-start-phase-a, #btn-submit-next, #btn-no-errors, ' +
      '#btn-start-phase-b, #btn-submit-expl'
    );
    if (btn) setTimeout(resetAll, 50);
  }, true);
  setInterval(tick, 500);
}
"""


# ── Helper functions ────────────────────────────────────────────────────────


def _format_elapsed(start_time: float) -> str:
    """Format elapsed seconds as mm:ss."""
    elapsed = int(time.time() - start_time)
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


def _render_source_box(source_text: str) -> str:
    """Render source text in a styled box."""
    escaped = (
        source_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<div class="source-box"><strong>Source (EN):</strong><br/>{escaped}</div>'


def _render_category_buttons(selected: str = "") -> str:
    """Render all 10 MQM category pill buttons as HTML."""
    buttons = []
    for cat in ALL_CATEGORIES:
        label = TAG_LABELS.get(cat, cat)
        dot_color = TAG_COLORS.get(cat, {}).get("dot", "#666")
        sel_class = " selected" if cat == selected else ""
        buttons.append(
            f'<span class="category-btn{sel_class}" '
            f'style="border-left: 3px solid {dot_color};">'
            f'<span style="width:8px;height:8px;border-radius:50%;'
            f'background:{dot_color};display:inline-block;"></span>'
            f'{label}</span>'
        )
    return '<div style="display:flex;flex-wrap:wrap;gap:6px;">' + "".join(buttons) + "</div>"


def _render_explanation_card(
    layer1: dict | None, layer2a: dict | None
) -> str:
    """Render the generated explanation for Phase B review."""
    parts = []
    if layer1:
        parts.append('<div class="explanation-card">')
        parts.append("<h4>Layer 1 -- Contrastive Explanation</h4>")
        for key, label in [
            ("mt_interpretation", "MT interpretation"),
            ("actual_meaning", "Actual meaning"),
            ("reader_impact", "Reader impact"),
            ("correction_rationale", "Correction rationale"),
        ]:
            val = layer1.get(key, "")
            if val:
                parts.append(f"<p><strong>{label}:</strong> {_esc(val)}</p>")
        parts.append("</div>")

    if layer2a:
        parts.append('<div class="explanation-card">')
        parts.append("<h4>Layer 2a -- System Behaviour</h4>")
        for key, label in [
            ("error_mechanism", "Error mechanism"),
            ("architectural_cause", "Architectural cause"),
            ("pattern_generalization", "Pattern generalization"),
        ]:
            val = layer2a.get(key, "")
            if val:
                parts.append(f"<p><strong>{label}:</strong> {_esc(val)}</p>")
        parts.append("</div>")

    if not parts:
        return '<div class="explanation-card"><p><em>No explanation available.</em></p></div>'
    return "\n".join(parts)


def _esc(text: str) -> str:
    """Escape HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Main builder ────────────────────────────────────────────────────────────


def build_annotation_app(annotator_id: str = "annotator_1") -> gr.Blocks:
    """Build the Gradio expert annotation interface."""

    annotation_items = load_annotation_set()
    explanation_items = load_explanation_set()
    total_a = len(annotation_items) if annotation_items else 84
    total_b = len(explanation_items) if explanation_items else 24

    with gr.Blocks(
        title="ToM-PE Expert Annotation",
        css=ANNOTATION_APP_CSS,
        theme=gr.themes.Soft(),
    ) as app:

        # ── Shared state ────────────────────────────────────────────────
        current_index_a = gr.State(0)
        current_index_b = gr.State(0)
        annotations_state = gr.State([])  # errors for current item
        timestamp_start = gr.State(0.0)
        selected_category = gr.State("")

        # ================================================================
        # LOGIN VIEW
        # ================================================================
        with gr.Column(visible=True) as login_view:
            gr.Markdown("# ToM-PE Expert Annotation Tool")
            gr.Markdown(
                "Welcome. This tool has two phases:\n"
                f"- **Phase A**: Error annotation ({total_a} items, blind)\n"
                f"- **Phase B**: Explanation quality review ({total_b} items)\n\n"
                "Your annotations are saved automatically after each item."
            )
            annotator_input = gr.Textbox(
                label="Annotator ID",
                value=annotator_id,
                placeholder="e.g., annotator_1",
            )
            start_btn = gr.Button(
                "Start Phase A", variant="primary", size="lg",
                elem_id="btn-start-phase-a",
            )

        # ================================================================
        # PHASE A: ERROR ANNOTATION
        # ================================================================
        with gr.Column(visible=False) as phase_a_view:
            with gr.Row():
                phase_a_header = gr.Markdown("## Phase A: Error Annotation")
                timer_a = gr.HTML(
                    '<div class="timer-display">00:00</div>'
                )

            item_counter_a = gr.Markdown(f"**Item 1 / {total_a}**")
            source_html_a = gr.HTML("")
            gr.Markdown("**Translation (FR):** *Select a span to annotate*")
            translation_html_a = gr.HTML("")
            span_output = gr.Textbox(
                label="Selected text",
                elem_id="span-output-main",
                interactive=True,
                visible=True,
                max_lines=1,
            )

            # Category buttons (Gradio buttons for interactivity)
            gr.Markdown("**Error category:**")
            with gr.Row():
                cat_buttons: dict[str, gr.Button] = {}
                for cat in ALL_CATEGORIES[:5]:
                    label = TAG_LABELS.get(cat, cat)
                    dot_color = TAG_COLORS.get(cat, {}).get("dot", "#666")
                    cat_buttons[cat] = gr.Button(
                        f"● {label}",
                        size="sm",
                        elem_classes=["category-btn"],
                    )
            with gr.Row():
                for cat in ALL_CATEGORIES[5:]:
                    label = TAG_LABELS.get(cat, cat)
                    dot_color = TAG_COLORS.get(cat, {}).get("dot", "#666")
                    cat_buttons[cat] = gr.Button(
                        f"● {label}",
                        size="sm",
                        elem_classes=["category-btn"],
                    )

            selected_cat_display = gr.Markdown("*No category selected*")
            severity_radio = gr.Radio(
                choices=["minor", "major", "critical"],
                label="Severity",
                value="major",
            )
            add_error_btn = gr.Button(
                "Add Error", variant="secondary", size="sm"
            )
            status_msg_a = gr.Markdown("")

            gr.Markdown("**Annotations for this item:**")
            chips_html = gr.HTML(render_annotation_chips([]))

            confidence_radio = gr.Radio(
                choices=["Low", "Medium", "High"],
                label="Confidence",
                value="Medium",
            )
            notes_box = gr.Textbox(
                label="Notes (optional)",
                placeholder="Any observations about this item...",
                lines=2,
            )
            with gr.Row():
                no_errors_btn = gr.Button(
                    "No Errors Found", variant="secondary",
                    elem_id="btn-no-errors",
                )
                submit_next_btn = gr.Button(
                    "Submit & Next", variant="primary",
                    elem_id="btn-submit-next",
                )

        # ================================================================
        # PHASE A -> B TRANSITION
        # ================================================================
        with gr.Column(visible=False) as transition_view:
            gr.Markdown(
                '<div class="completion-screen">'
                "<h2>Phase A Complete</h2>"
                f"<p>You annotated all {total_a} items. Thank you!</p>"
                "<p>Phase B involves reviewing generated explanations. "
                "You will see ground-truth errors and rate the quality of "
                "the pedagogical explanations.</p>"
                "</div>"
            )
            start_phase_b_btn = gr.Button(
                "Start Phase B", variant="primary", size="lg",
                elem_id="btn-start-phase-b",
            )

        # ================================================================
        # PHASE B: EXPLANATION QUALITY REVIEW
        # ================================================================
        with gr.Column(visible=False) as phase_b_view:
            with gr.Row():
                phase_b_header = gr.Markdown(
                    "## Phase B: Explanation Quality Review"
                )
                timer_b = gr.HTML(
                    '<div class="timer-display">00:00</div>'
                )

            item_counter_b = gr.Markdown(f"**Explanation 1 / {total_b}**")
            source_html_b = gr.HTML("")
            gr.Markdown("**Translation with error highlighted:**")
            translation_html_b = gr.HTML("")

            error_info_html = gr.HTML("")
            explanation_html = gr.HTML("")

            gr.Markdown("### Rate this explanation")
            accuracy_radio = gr.Radio(
                choices=["Incorrect", "Partially correct", "Correct"],
                label="Factual accuracy",
                value=None,
            )
            clarity_radio = gr.Radio(
                choices=["Unclear", "Somewhat clear", "Clear"],
                label="Pedagogical clarity",
                value=None,
            )
            completeness_radio = gr.Radio(
                choices=["Incomplete", "Adequate", "Thorough"],
                label="Completeness",
                value=None,
            )
            comment_box = gr.Textbox(
                label="Comment (optional)",
                placeholder="Any observations about the explanation quality...",
                lines=2,
            )
            status_msg_b = gr.Markdown("")
            submit_expl_btn = gr.Button(
                "Submit & Next", variant="primary",
                elem_id="btn-submit-expl",
            )

        # ================================================================
        # DONE VIEW
        # ================================================================
        with gr.Column(visible=False) as done_view:
            done_html = gr.HTML("")

        # ── Phase A: Load an item ───────────────────────────────────────

        def _load_item_a(index: int) -> tuple:
            """Return UI updates for item at given index."""
            if not annotation_items or index >= len(annotation_items):
                return (
                    "**All items completed.**",
                    "",
                    "",
                    "",
                    render_annotation_chips([]),
                    [],
                    time.time(),
                    "",
                )
            item = annotation_items[index]
            source = item.get("source_text", "")
            translation = item.get("presented_text", "")
            source_html = _render_source_box(source)
            trans_html = render_text_with_highlights(
                translation, [], widget_id="main", level="expert"
            )
            counter = f"**Item {index + 1} / {total_a}**"
            return (
                counter,
                source_html,
                trans_html,
                "",          # span_output
                render_annotation_chips([]),
                [],          # annotations_state
                time.time(), # timestamp_start
                "",          # status_msg
            )

        # ── Phase A: Category selection ─────────────────────────────────

        def _select_category(cat: str) -> tuple[str, str]:
            label = TAG_LABELS.get(cat, cat)
            dot_color = TAG_COLORS.get(cat, {}).get("dot", "#666")
            display = (
                f'**Selected:** <span style="color:{dot_color}">●</span> {label}'
            )
            return cat, display

        for cat_val, cat_btn in cat_buttons.items():
            cat_btn.click(
                fn=lambda c=cat_val: _select_category(c),
                inputs=[],
                outputs=[selected_category, selected_cat_display],
            )

        # ── Phase A: Add error ──────────────────────────────────────────

        def _add_error(
            span_text: str,
            category: str,
            severity: str,
            anns: list[dict],
            idx: int,
        ) -> tuple:
            if not span_text or not span_text.strip():
                return (
                    anns,
                    render_annotation_chips(anns),
                    gr.update(),
                    "*Select a span in the translation first.*",
                )
            if not category:
                return (
                    anns,
                    render_annotation_chips(anns),
                    gr.update(),
                    "*Select an error category first.*",
                )

            # Find span offsets in the presented text
            item = annotation_items[idx] if idx < len(annotation_items) else {}
            translation = item.get("presented_text", "")
            span_start = translation.find(span_text.strip())
            if span_start == -1:
                span_start = 0
            span_end = span_start + len(span_text.strip())

            ann_id = str(uuid4())[:8]
            new_ann = {
                "annotation_id": ann_id,
                "span_start": span_start,
                "span_end": span_end,
                "span_text": span_text.strip(),
                "primary_tag": category,
                "severity": severity or "major",
            }
            anns = anns + [new_ann]

            # Update translation highlights
            trans_html = render_text_with_highlights(
                translation, anns, widget_id="main", level="expert"
            )

            return (
                anns,
                render_annotation_chips(anns),
                trans_html,
                "",
            )

        add_error_btn.click(
            fn=_add_error,
            inputs=[
                span_output,
                selected_category,
                severity_radio,
                annotations_state,
                current_index_a,
            ],
            outputs=[
                annotations_state,
                chips_html,
                translation_html_a,
                status_msg_a,
            ],
        )

        # ── Phase A: Submit & Next ──────────────────────────────────────

        def _submit_item_a(
            anns: list[dict],
            idx: int,
            t_start: float,
            confidence: str,
            notes: str,
            ann_id_input: str,
            no_errors: bool = False,
        ) -> tuple:
            """Save annotation and advance to next item (or transition)."""
            if not annotation_items:
                return (
                    idx, [], time.time(), "", "",
                    gr.update(), gr.update(),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(), gr.update(),
                    "",
                )

            item = annotation_items[idx] if idx < len(annotation_items) else {}
            now = datetime.now(timezone.utc)
            t_end = time.time()
            duration = t_end - t_start if t_start else 0.0

            errors = []
            for a in anns:
                errors.append({
                    "span_start": a.get("span_start", 0),
                    "span_end": a.get("span_end", 0),
                    "span_text": a.get("span_text", ""),
                    "category": a.get("primary_tag", ""),
                    "severity": a.get("severity", "major"),
                })

            record = {
                "annotation_id": str(uuid4()),
                "annotator_id": ann_id_input,
                "item_id": item.get("item_id", f"item_{idx}"),
                "item_source": item.get("item_source", ""),
                "tom_level": item.get("tom_level"),
                "timestamp_start": datetime.fromtimestamp(
                    t_start, tz=timezone.utc
                ).isoformat() if t_start else now.isoformat(),
                "timestamp_end": now.isoformat(),
                "duration_seconds": round(duration, 2),
                "errors": errors,
                "no_errors_found": no_errors,
                "confidence": (confidence or "Medium").lower(),
                "notes": notes or None,
                "is_practice": item.get("is_practice", False),
            }

            try:
                save_annotation(ann_id_input, record)
            except Exception:
                logger.exception("Failed to save annotation for item %s", idx)

            next_idx = idx + 1

            # Check if Phase A is complete
            if next_idx >= len(annotation_items):
                return (
                    next_idx, [], time.time(), "", "*No category selected*",
                    gr.update(), gr.update(),
                    gr.update(visible=False),  # phase_a_view
                    gr.update(visible=True),   # transition_view
                    render_annotation_chips([]),
                    gr.update(value="major"),
                    "",
                )

            # Load next item
            (
                counter, source_h, trans_h, span_val,
                chips_h, new_anns, new_ts, status
            ) = _load_item_a(next_idx)

            return (
                next_idx,
                new_anns,
                new_ts,
                counter,
                "*No category selected*",
                source_h,
                trans_h,
                gr.update(visible=True),   # phase_a_view stays visible
                gr.update(visible=False),  # transition_view stays hidden
                chips_h,
                gr.update(value="major"),
                "",
            )

        submit_outputs = [
            current_index_a,
            annotations_state,
            timestamp_start,
            item_counter_a,
            selected_cat_display,
            source_html_a,
            translation_html_a,
            phase_a_view,
            transition_view,
            chips_html,
            severity_radio,
            status_msg_a,
        ]

        submit_next_btn.click(
            fn=lambda anns, idx, ts, conf, notes, aid: _submit_item_a(
                anns, idx, ts, conf, notes, aid, no_errors=False
            ),
            inputs=[
                annotations_state,
                current_index_a,
                timestamp_start,
                confidence_radio,
                notes_box,
                annotator_input,
            ],
            outputs=submit_outputs,
        )

        no_errors_btn.click(
            fn=lambda anns, idx, ts, conf, notes, aid: _submit_item_a(
                [], idx, ts, conf, notes, aid, no_errors=True
            ),
            inputs=[
                annotations_state,
                current_index_a,
                timestamp_start,
                confidence_radio,
                notes_box,
                annotator_input,
            ],
            outputs=submit_outputs,
        )

        # ── Login -> Phase A ────────────────────────────────────────────

        def _start_phase_a() -> tuple:
            vals = _load_item_a(0)
            counter, source_h, trans_h, span_val, chips_h, anns, ts, status = vals
            return (
                gr.update(visible=False),  # login_view
                gr.update(visible=True),   # phase_a_view
                0,          # current_index_a
                anns,       # annotations_state
                ts,         # timestamp_start
                counter,    # item_counter_a
                source_h,   # source_html_a
                trans_h,    # translation_html_a
                chips_h,    # chips_html
                "",         # selected_category
            )

        start_btn.click(
            fn=_start_phase_a,
            inputs=[],
            outputs=[
                login_view,
                phase_a_view,
                current_index_a,
                annotations_state,
                timestamp_start,
                item_counter_a,
                source_html_a,
                translation_html_a,
                chips_html,
                selected_category,
            ],
        )

        # ── Phase A -> Phase B transition ───────────────────────────────

        def _load_item_b(index: int) -> tuple:
            """Return UI updates for explanation review item."""
            if not explanation_items or index >= len(explanation_items):
                return ("**All items reviewed.**", "", "", "", "", time.time())

            item = explanation_items[index]
            source = item.get("source_text", "")
            translation = item.get("presented_text", "")
            error_span = item.get("error_span_text", "")
            error_cat = item.get("error_category", "")
            error_sev = item.get("error_severity", "")
            original = item.get("original_text", "")

            # Build error highlight annotation
            span_start = translation.find(error_span) if error_span else -1
            highlight_anns = []
            if span_start >= 0:
                highlight_anns.append({
                    "span_start": span_start,
                    "span_end": span_start + len(error_span),
                    "span_text": error_span,
                    "primary_tag": error_cat,
                    "annotation_id": "gt_error",
                })

            source_h = _render_source_box(source)
            trans_h = render_text_with_highlights(
                translation, highlight_anns, widget_id="review", level="navigator"
            )

            # Error info
            dot_color = TAG_COLORS.get(error_cat, {}).get("dot", "#666")
            bg_color = TAG_COLORS.get(error_cat, {}).get("highlight", "#f0f0f0")
            cat_label = TAG_LABELS.get(error_cat, error_cat)
            error_info = (
                f'<div style="padding:10px;background:#f9fafb;border-radius:8px;'
                f'border:1px solid #e5e7eb;margin:8px 0;">'
                f'<span class="error-info-badge" style="background:{bg_color};'
                f'color:{dot_color};">{cat_label} &middot; {error_sev}</span>'
            )
            if original and error_span:
                error_info += (
                    f'<span style="font-size:14px;color:#374151;">'
                    f'&ldquo;{_esc(error_span)}&rdquo; &rarr; '
                    f'&ldquo;{_esc(original)}&rdquo;</span>'
                )
            error_info += "</div>"

            # Explanation cards
            layer1 = item.get("layer1_explanation")
            layer2a = item.get("layer2a_explanation")
            expl_h = _render_explanation_card(layer1, layer2a)

            counter = f"**Explanation {index + 1} / {total_b}**"
            return (counter, source_h, trans_h, error_info, expl_h, time.time())

        def _start_phase_b() -> tuple:
            vals = _load_item_b(0)
            counter, source_h, trans_h, error_info, expl_h, ts = vals
            return (
                gr.update(visible=False),  # transition_view
                gr.update(visible=True),   # phase_b_view
                0,          # current_index_b
                ts,         # timestamp_start
                counter,    # item_counter_b
                source_h,   # source_html_b
                trans_h,    # translation_html_b
                error_info, # error_info_html
                expl_h,     # explanation_html
                gr.update(value=None),  # accuracy_radio
                gr.update(value=None),  # clarity_radio
                gr.update(value=None),  # completeness_radio
                "",         # comment_box
                "",         # status_msg_b
            )

        start_phase_b_btn.click(
            fn=_start_phase_b,
            inputs=[],
            outputs=[
                transition_view,
                phase_b_view,
                current_index_b,
                timestamp_start,
                item_counter_b,
                source_html_b,
                translation_html_b,
                error_info_html,
                explanation_html,
                accuracy_radio,
                clarity_radio,
                completeness_radio,
                comment_box,
                status_msg_b,
            ],
        )

        # ── Phase B: Submit explanation rating ──────────────────────────

        def _submit_explanation(
            idx: int,
            t_start: float,
            accuracy: str | None,
            clarity: str | None,
            completeness: str | None,
            comment: str,
            ann_id_input: str,
        ) -> tuple:
            """Save rating and advance (or finish)."""
            # Validate
            if not accuracy or not clarity or not completeness:
                return (
                    idx, t_start,
                    gr.update(), gr.update(), gr.update(),
                    gr.update(), gr.update(),
                    gr.update(value=accuracy),
                    gr.update(value=clarity),
                    gr.update(value=completeness),
                    gr.update(),
                    "*Please complete all three rating scales.*",
                    gr.update(visible=True),   # phase_b_view
                    gr.update(visible=False),  # done_view
                )

            item = explanation_items[idx] if idx < len(explanation_items) else {}
            now = datetime.now(timezone.utc)
            t_end = time.time()
            duration = t_end - t_start if t_start else 0.0

            # Normalise labels to schema values
            accuracy_map = {
                "Incorrect": "incorrect",
                "Partially correct": "partially_correct",
                "Correct": "correct",
            }
            clarity_map = {
                "Unclear": "unclear",
                "Somewhat clear": "somewhat_clear",
                "Clear": "clear",
            }
            completeness_map = {
                "Incomplete": "incomplete",
                "Adequate": "adequate",
                "Thorough": "thorough",
            }

            record = {
                "rating_id": str(uuid4()),
                "annotator_id": ann_id_input,
                "item_id": item.get("item_id", f"item_{idx}"),
                "error_index": item.get("error_index", 0),
                "tom_level": item.get("tom_level"),
                "factual_accuracy": accuracy_map.get(accuracy, accuracy),
                "pedagogical_clarity": clarity_map.get(clarity, clarity),
                "completeness": completeness_map.get(completeness, completeness),
                "comment": comment or None,
                "timestamp_start": datetime.fromtimestamp(
                    t_start, tz=timezone.utc
                ).isoformat() if t_start else now.isoformat(),
                "timestamp_end": now.isoformat(),
                "duration_seconds": round(duration, 2),
            }

            try:
                save_explanation_rating(ann_id_input, record)
            except Exception:
                logger.exception("Failed to save explanation rating %s", idx)

            next_idx = idx + 1

            # Check if Phase B is complete
            if next_idx >= len(explanation_items):
                summary = _build_completion_summary(ann_id_input)
                return (
                    next_idx, time.time(),
                    gr.update(), gr.update(), gr.update(),
                    gr.update(), gr.update(),
                    gr.update(value=None),
                    gr.update(value=None),
                    gr.update(value=None),
                    gr.update(),
                    "",
                    gr.update(visible=False),  # phase_b_view
                    gr.update(visible=True),   # done_view -> show
                )

            # Load next explanation
            counter, source_h, trans_h, error_info, expl_h, ts = _load_item_b(
                next_idx
            )
            return (
                next_idx, ts,
                counter, source_h, trans_h,
                error_info, expl_h,
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=""),
                "",
                gr.update(visible=True),
                gr.update(visible=False),
            )

        submit_expl_btn.click(
            fn=_submit_explanation,
            inputs=[
                current_index_b,
                timestamp_start,
                accuracy_radio,
                clarity_radio,
                completeness_radio,
                comment_box,
                annotator_input,
            ],
            outputs=[
                current_index_b,
                timestamp_start,
                item_counter_b,
                source_html_b,
                translation_html_b,
                error_info_html,
                explanation_html,
                accuracy_radio,
                clarity_radio,
                completeness_radio,
                comment_box,
                status_msg_b,
                phase_b_view,
                done_view,
            ],
        )

        # ── Completion summary ──────────────────────────────────────────

        def _build_completion_summary(ann_id: str) -> str:
            """Count saved files and build a summary HTML block."""
            ann_dir = ANNOTATIONS_DIR / ann_id
            rating_dir = ann_dir / "explanation_ratings"
            n_annotations = len(list(ann_dir.glob("*.json"))) if ann_dir.exists() else 0
            n_ratings = len(list(rating_dir.glob("*.json"))) if rating_dir.exists() else 0
            return (
                '<div class="completion-screen">'
                "<h2>All Done!</h2>"
                f"<p>Phase A annotations saved: <strong>{n_annotations}</strong></p>"
                f"<p>Phase B ratings saved: <strong>{n_ratings}</strong></p>"
                "<p>Thank you for your contribution to the ToM-PE validation study.</p>"
                "</div>"
            )

        # Wire the done view to display the summary when Phase B finishes.
        # We use an additional event: when done_view becomes visible, populate it.
        def _show_done(idx_b: int, ann_id: str) -> str:
            return _build_completion_summary(ann_id)

        done_view.select(
            fn=_show_done,
            inputs=[current_index_b, annotator_input],
            outputs=[done_html],
        )

        # Also populate done_html on the submit that transitions to done_view.
        # We attach a secondary handler via .then() on submit_expl_btn.
        # Gradio does not support .select on Column, so we populate inline.
        # Instead, update done_html inside _submit_explanation by adding it
        # to the outputs. Let's add a load event as a workaround:
        app.load(
            fn=lambda: "",
            inputs=[],
            outputs=[done_html],
        )

        # Override: populate done_html whenever phase_b finishes.
        # We do this by chaining a .then() after submit_expl_btn.
        submit_expl_btn.click(
            fn=lambda ann_id: _build_completion_summary(ann_id),
            inputs=[annotator_input],
            outputs=[done_html],
        )

        # Animate `.timer-display` elements once the page loads.
        app.load(fn=None, inputs=None, outputs=None, js=ANNOTATION_TIMER_JS)

    return app


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = build_annotation_app()
    app.launch(server_port=7861)
