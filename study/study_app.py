"""Gradio study app for the ECTEL 2026 small-scale evaluation study.

Linear flow: Consent -> 20 Segment evaluations -> Post-task questionnaire -> Thank you.
No scaffolding, no feedback, no backward navigation.
Separate from the main ToM-PE training platform.

Spec reference: ToM-PE_Study_Interface_Spec_v1.md
"""

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import gradio as gr

# ── Paths ─────────────────────────────────────────────────────────────────────

STUDY_DIR = Path(__file__).resolve().parent
CONFIG_PATH = STUDY_DIR / "study_config.json"
RESPONSES_DIR = STUDY_DIR / "responses"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_config() -> dict:
    """Load the study configuration."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _load_segments(config: dict) -> list[dict]:
    """Load segment data from the configured segment file."""
    seg_path = STUDY_DIR / config["segment_file"]
    with open(seg_path) as f:
        data = json.load(f)
    return data["segments"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _generate_participant_id() -> str:
    """Anonymous participant ID: short hash of a UUID4."""
    return hashlib.sha256(uuid4().bytes).hexdigest()[:8]


def _assign_form() -> str:
    """Randomly assign form A or B."""
    return random.choice(["A", "B"])


def _build_segment_order(segments: list[dict]) -> list[int]:
    """Build a pseudo-random segment ordering with constraints.

    Constraints (from spec §3.2):
    - First segment is always an L1 error (warm-up)
    - No more than 2 consecutive segments from the same condition
    """
    indices = list(range(len(segments)))

    # Find L1 segments for warm-up
    l1_indices = [i for i in indices if segments[i]["condition"] == "L1"]
    rest_indices = [i for i in indices if i not in l1_indices]

    if not l1_indices:
        # Fallback: just shuffle everything
        random.shuffle(indices)
        return indices

    # Pick one L1 as the first segment
    first = random.choice(l1_indices)
    remaining = [i for i in indices if i != first]
    random.shuffle(remaining)

    # Enforce the no-more-than-2-consecutive-same-condition constraint
    ordered = [first]
    attempts = 0
    while remaining and attempts < 500:
        # Try to find a valid next segment
        placed = False
        for j, idx in enumerate(remaining):
            cond = segments[idx]["condition"]
            # Check last 2 in ordered
            if len(ordered) >= 2:
                last_two = [segments[ordered[-1]]["condition"], segments[ordered[-2]]["condition"]]
                if last_two[0] == cond and last_two[1] == cond:
                    continue
            ordered.append(remaining.pop(j))
            placed = True
            break
        if not placed:
            # Can't satisfy constraint strictly; just append the rest
            ordered.extend(remaining)
            remaining = []
        attempts += 1

    return ordered


def _resolve_target_text(segment: dict, form: str) -> str:
    """Get the target text for a segment, resolving form variants for L2."""
    if segment.get("form_variant") and form in segment["form_variant"]:
        return segment["form_variant"][form]["target_text"]
    return segment.get("target_text", "")


def _get_fluency_variant(segment: dict, form: str) -> str | None:
    """Get the fluency variant label for L2 segments."""
    if segment.get("form_variant") and form in segment["form_variant"]:
        return segment["form_variant"][form].get("fluency")
    return None


def _save_response(response_data: dict, config: dict) -> None:
    """Save participant response to disk."""
    study_dir = RESPONSES_DIR / config["study_id"]
    study_dir.mkdir(parents=True, exist_ok=True)
    path = study_dir / f"participant_{response_data['participant_id']}.json"
    with open(path, "w") as f:
        json.dump(response_data, f, indent=2, ensure_ascii=False)


# ── CSS ───────────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
.study-container { max-width: 900px; margin: 0 auto; }
.segment-text {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 16px;
    line-height: 1.6;
    padding: 16px;
    border: 1px solid #ddd;
    border-radius: 8px;
    background: #fafafa;
    min-height: 80px;
}
.segment-label {
    font-weight: bold;
    margin-bottom: 4px;
    color: #555;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.progress-bar {
    font-size: 14px;
    color: #888;
    margin-bottom: 12px;
}
.consent-box {
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 20px;
    background: #f9f9f9;
    max-height: 400px;
    overflow-y: auto;
}
"""

# ── App Builder ───────────────────────────────────────────────────────────────


def build_app() -> gr.Blocks:
    """Build and return the Gradio study app."""

    config = _load_config()
    all_segments = _load_segments(config)
    consent_cfg = config.get("consent", {})
    post_questions = config.get("post_task_questions", [])
    total_segments = len(all_segments)

    with gr.Blocks(
        title=config.get("title", "MT Quality Evaluation Study"),
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(),
    ) as app:

        # ── State ──────────────────────────────────────────────────────
        state = gr.State({
            "phase": "consent",      # consent | segment | questionnaire | thankyou
            "participant_id": None,
            "form": None,
            "segment_order": [],
            "current_idx": 0,
            "consent_timestamp": None,
            "responses": [],
            "segment_displayed_at": None,
        })

        # ── Consent Screen ─────────────────────────────────────────────
        with gr.Column(visible=True, elem_classes="study-container") as consent_screen:
            gr.Markdown(f"# {config.get('title', 'MT Quality Evaluation Study')}")

            consent_text = consent_cfg.get("text", "You are invited to participate in a research study...")
            researcher_email = consent_cfg.get("researcher_email", "[email]")
            institution = consent_cfg.get("institution", "[institution]")

            gr.Markdown(f"""
<div class="consent-box">

**{consent_cfg.get('title', 'Informed Consent')}**

{consent_text}

- **Task**: Read {total_segments} short French-English text pairs and judge translation quality (approx. 25 minutes).
- **Data**: Your responses are anonymous. No identifying information is collected or stored.
- **Withdrawal**: You may close the browser at any time. Partial data will be deleted.
- **Contact**: {researcher_email} ({institution})

By clicking "I consent", you confirm that you have read this information and agree to participate.

</div>
""")
            consent_btn = gr.Button("I consent and wish to participate", variant="primary", size="lg")
            decline_btn = gr.Button("I do not wish to participate", variant="secondary")

        # ── Decline Screen ─────────────────────────────────────────────
        with gr.Column(visible=False, elem_classes="study-container") as decline_screen:
            gr.Markdown("## Thank you\n\nYou may close this window.")

        # ── Segment Evaluation Screen ──────────────────────────────────
        with gr.Column(visible=False, elem_classes="study-container") as segment_screen:
            progress_md = gr.Markdown("Segment 1 of 20", elem_classes="progress-bar")

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown('<div class="segment-label">Source (French)</div>')
                    source_text = gr.Textbox(
                        label="Source (French)",
                        interactive=False,
                        lines=5,
                        show_label=False,
                        elem_classes="segment-text",
                    )
                with gr.Column(scale=1):
                    gr.Markdown('<div class="segment-label">Translation (English)</div>')
                    target_text = gr.Textbox(
                        label="Translation (English)",
                        interactive=False,
                        lines=5,
                        show_label=False,
                        elem_classes="segment-text",
                    )

            gr.Markdown("---")

            acceptable_radio = gr.Radio(
                label="1. Is this translation acceptable?",
                choices=["Yes, the translation is acceptable", "No, there is a problem"],
                value=None,
            )

            justification_box = gr.Textbox(
                label="2. If no: describe the problem briefly.",
                placeholder="Please describe the problem briefly, even in a few words.",
                lines=3,
                visible=False,
            )

            confidence_radio = gr.Radio(
                label="3. How confident are you in your judgment?",
                choices=["1 - Not at all confident", "2", "3", "4", "5 - Very confident"],
                value=None,
            )

            next_btn = gr.Button("Next segment", variant="primary", interactive=False)

        # ── Questionnaire Screen ───────────────────────────────────────
        with gr.Column(visible=False, elem_classes="study-container") as questionnaire_screen:
            gr.Markdown("## Thank you for completing the evaluation!\n\nPlease answer a few short questions about yourself and your experience.")
            gr.Markdown("---")

            # Build questionnaire components dynamically
            q_components = {}
            for q in post_questions:
                qid = q["id"]
                if q["type"] == "likert":
                    q_components[qid] = gr.Radio(
                        label=q["text"],
                        choices=q.get("labels", [str(i+1) for i in range(q.get("scale", 5))]),
                        value=None,
                    )
                elif q["type"] == "single_choice":
                    q_components[qid] = gr.Radio(
                        label=q["text"],
                        choices=q.get("options", []),
                        value=None,
                    )
                elif q["type"] == "text":
                    q_components[qid] = gr.Textbox(
                        label=q["text"],
                        lines=1,
                    )
                elif q["type"] == "textarea":
                    q_components[qid] = gr.Textbox(
                        label=q["text"],
                        placeholder=q.get("placeholder", ""),
                        lines=4,
                    )

            submit_btn = gr.Button("Submit", variant="primary", size="lg")

        # ── Thank You Screen ───────────────────────────────────────────
        with gr.Column(visible=False, elem_classes="study-container") as thankyou_screen:
            gr.Markdown(f"""## Thank you for your participation!

Your responses have been recorded anonymously.

If you have any questions about this study, please contact {researcher_email}.

You may now close this window.
""")

        # ── Event Handlers ─────────────────────────────────────────────

        def on_consent(s):
            """Handle consent: generate ID, assign form, build order, show first segment."""
            pid = _generate_participant_id()
            form = _assign_form()
            order = _build_segment_order(all_segments)
            now = _now_iso()

            s["phase"] = "segment"
            s["participant_id"] = pid
            s["form"] = form
            s["segment_order"] = order
            s["current_idx"] = 0
            s["consent_timestamp"] = now
            s["responses"] = []
            s["segment_displayed_at"] = _now_iso()

            # First segment
            seg_idx = order[0]
            seg = all_segments[seg_idx]
            src = seg["source_text"]
            tgt = _resolve_target_text(seg, form)
            progress = f"**Segment 1 of {total_segments}**"

            return (
                s,
                gr.update(visible=False),  # consent_screen
                gr.update(visible=True),   # segment_screen
                progress,                  # progress_md
                src,                       # source_text
                tgt,                       # target_text
                None,                      # acceptable_radio
                "",                        # justification_box
                gr.update(visible=False),  # justification_box visibility
                None,                      # confidence_radio
                gr.update(interactive=False),  # next_btn
            )

        consent_btn.click(
            on_consent,
            inputs=[state],
            outputs=[
                state, consent_screen, segment_screen,
                progress_md, source_text, target_text,
                acceptable_radio, justification_box, justification_box,
                confidence_radio, next_btn,
            ],
        )

        def on_decline(s):
            s["phase"] = "declined"
            return s, gr.update(visible=False), gr.update(visible=True)

        decline_btn.click(
            on_decline,
            inputs=[state],
            outputs=[state, consent_screen, decline_screen],
        )

        def on_acceptable_change(choice, s):
            """Show/hide justification box and update next button state."""
            show_just = choice == "No, there is a problem"
            return gr.update(visible=show_just)

        acceptable_radio.change(
            on_acceptable_change,
            inputs=[acceptable_radio, state],
            outputs=[justification_box],
        )

        def check_next_enabled(acceptable, confidence):
            """Enable Next button only when Q1 and Q3 are answered."""
            enabled = acceptable is not None and confidence is not None
            return gr.update(interactive=enabled)

        acceptable_radio.change(
            check_next_enabled,
            inputs=[acceptable_radio, confidence_radio],
            outputs=[next_btn],
        )
        confidence_radio.change(
            check_next_enabled,
            inputs=[acceptable_radio, confidence_radio],
            outputs=[next_btn],
        )

        def on_next(acceptable_val, justification_val, confidence_val, s):
            """Save current segment response and advance to next or questionnaire."""
            idx = s["current_idx"]
            order = s["segment_order"]
            form = s["form"]
            seg_idx = order[idx]
            seg = all_segments[seg_idx]

            # Parse confidence to int
            conf_int = int(confidence_val[0]) if confidence_val else None

            # Build response record
            now = _now_iso()
            displayed_at = s.get("segment_displayed_at", now)
            # Calculate response time
            try:
                t0 = datetime.fromisoformat(displayed_at)
                t1 = datetime.fromisoformat(now)
                rt = int((t1 - t0).total_seconds())
            except (ValueError, TypeError):
                rt = 0

            response = {
                "segment_id": seg["id"],
                "condition": seg["condition"],
                "fluency_variant": _get_fluency_variant(seg, form),
                "tom_level": seg["tom_level"],
                "displayed_at": displayed_at,
                "submitted_at": now,
                "response_time_seconds": rt,
                "acceptable": acceptable_val == "Yes, the translation is acceptable",
                "justification": justification_val if acceptable_val == "No, there is a problem" else None,
                "confidence": conf_int,
            }
            s["responses"].append(response)

            # Auto-save after each segment
            response_data = {
                "participant_id": s["participant_id"],
                "study_id": config["study_id"],
                "form": s["form"],
                "consent_timestamp": s["consent_timestamp"],
                "completion_timestamp": None,
                "segment_order": [all_segments[i]["id"] for i in order],
                "segments": s["responses"],
                "questionnaire": None,
            }
            _save_response(response_data, config)

            # Advance
            next_idx = idx + 1

            if next_idx >= len(order):
                # All segments done -> questionnaire
                s["phase"] = "questionnaire"
                s["current_idx"] = next_idx

                return (
                    s,
                    gr.update(visible=False),   # segment_screen
                    gr.update(visible=True),    # questionnaire_screen
                    gr.update(visible=False),   # thankyou_screen (not yet)
                    "",                         # progress_md
                    "",                         # source_text
                    "",                         # target_text
                    None,                       # acceptable_radio
                    "",                         # justification_box
                    gr.update(visible=False),   # justification_box visibility
                    None,                       # confidence_radio
                    gr.update(interactive=False),  # next_btn
                )

            # Show next segment
            s["current_idx"] = next_idx
            s["segment_displayed_at"] = _now_iso()

            next_seg_idx = order[next_idx]
            next_seg = all_segments[next_seg_idx]
            src = next_seg["source_text"]
            tgt = _resolve_target_text(next_seg, form)
            progress = f"**Segment {next_idx + 1} of {total_segments}**"

            return (
                s,
                gr.update(visible=True),    # segment_screen
                gr.update(visible=False),   # questionnaire_screen
                gr.update(visible=False),   # thankyou_screen
                progress,                   # progress_md
                src,                        # source_text
                tgt,                        # target_text
                None,                       # acceptable_radio (reset)
                "",                         # justification_box (reset)
                gr.update(visible=False),   # justification_box visibility
                None,                       # confidence_radio (reset)
                gr.update(interactive=False),  # next_btn (disabled until answered)
            )

        next_btn.click(
            on_next,
            inputs=[acceptable_radio, justification_box, confidence_radio, state],
            outputs=[
                state, segment_screen, questionnaire_screen, thankyou_screen,
                progress_md, source_text, target_text,
                acceptable_radio, justification_box, justification_box,
                confidence_radio, next_btn,
            ],
        )

        def on_submit(*args):
            """Save questionnaire and show thank you."""
            # Last arg is state
            s = args[-1]
            q_values = args[:-1]

            # Build questionnaire dict
            questionnaire = {}
            for i, q in enumerate(post_questions):
                val = q_values[i] if i < len(q_values) else None
                qid = q["id"]
                # For likert, convert label to index if needed
                if q["type"] == "likert" and val is not None:
                    labels = q.get("labels", [])
                    if val in labels:
                        questionnaire[qid] = labels.index(val) + 1
                    else:
                        questionnaire[qid] = val
                else:
                    questionnaire[qid] = val

            s["phase"] = "thankyou"

            # Final save
            response_data = {
                "participant_id": s["participant_id"],
                "study_id": config["study_id"],
                "form": s["form"],
                "consent_timestamp": s["consent_timestamp"],
                "completion_timestamp": _now_iso(),
                "segment_order": [all_segments[i]["id"] for i in s["segment_order"]],
                "segments": s["responses"],
                "questionnaire": questionnaire,
            }
            _save_response(response_data, config)

            return (
                s,
                gr.update(visible=False),  # questionnaire_screen
                gr.update(visible=True),   # thankyou_screen
            )

        submit_btn.click(
            on_submit,
            inputs=list(q_components.values()) + [state],
            outputs=[state, questionnaire_screen, thankyou_screen],
        )

    return app


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    """Launch the study app."""
    config = _load_config()
    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        show_error=True,
    )


if __name__ == "__main__":
    main()
