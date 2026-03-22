"""Streamlit study management interface for the ECTEL 2026 pilot study.

Three sub-views: Setup, Monitor, Export.
Standalone app, separate from the main ToM-PE teacher dashboard.

Spec reference: ToM-PE_Study_Interface_Spec_v1.md §4
"""

import csv
import io
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median

import streamlit as st

# ── Paths ─────────────────────────────────────────────────────────────────────

STUDY_DIR = Path(__file__).resolve().parent
CONFIG_PATH = STUDY_DIR / "study_config.json"
RESPONSES_DIR = STUDY_DIR / "responses"
EXPORTS_DIR = STUDY_DIR / "exports"
SEGMENTS_DIR = STUDY_DIR / "segments"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _load_segments(config: dict) -> list[dict]:
    seg_path = STUDY_DIR / config.get("segment_file", "segments/ectel2026_pilot.json")
    if seg_path.exists():
        with open(seg_path) as f:
            data = json.load(f)
        return data.get("segments", [])
    return []


def _load_all_responses(study_id: str) -> list[dict]:
    """Load all response files for a study."""
    resp_dir = RESPONSES_DIR / study_id
    if not resp_dir.exists():
        return []
    responses = []
    for p in sorted(resp_dir.glob("participant_*.json")):
        with open(p) as f:
            responses.append(json.load(f))
    return responses


def _is_complete(resp: dict) -> bool:
    return resp.get("completion_timestamp") is not None


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    st.set_page_config(
        page_title="Study Manager — ECTEL 2026",
        page_icon="🔬",
        layout="wide",
    )

    st.title("Study Manager — ECTEL 2026 Pilot")
    st.caption("Small-scale evaluation study management")

    tab_setup, tab_monitor, tab_export = st.tabs(["Setup", "Monitor", "Export"])

    with tab_setup:
        _page_setup()
    with tab_monitor:
        _page_monitor()
    with tab_export:
        _page_export()


# ── Setup ─────────────────────────────────────────────────────────────────────


def _page_setup():
    config = _load_config()

    st.subheader("Study Configuration")

    col1, col2 = st.columns(2)
    with col1:
        study_id = st.text_input("Study ID", value=config.get("study_id", "ectel2026_pilot"))
        title = st.text_input("Title", value=config.get("title", "MT Quality Evaluation Study"))
        description = st.text_area(
            "Description",
            value=config.get("description", ""),
            height=80,
        )
    with col2:
        status = st.selectbox(
            "Status",
            ["draft", "active", "closed"],
            index=["draft", "active", "closed"].index(config.get("status", "draft")),
        )
        form_assignment = st.radio(
            "Form assignment",
            ["random", "alternating"],
            index=0 if config.get("form_assignment", "random") == "random" else 1,
            horizontal=True,
        )

    col3, col4 = st.columns(2)
    with col3:
        open_from = st.text_input("Open from (ISO)", value=config.get("open_from", ""))
    with col4:
        close_at = st.text_input("Close at (ISO)", value=config.get("close_at", ""))

    # Segment file
    st.divider()
    st.subheader("Segment File")

    seg_files = list(SEGMENTS_DIR.glob("*.json"))
    seg_file_names = [str(p.relative_to(STUDY_DIR)) for p in seg_files]
    current_seg = config.get("segment_file", "")

    if seg_file_names:
        idx = seg_file_names.index(current_seg) if current_seg in seg_file_names else 0
        segment_file = st.selectbox("Segment file", seg_file_names, index=idx)
    else:
        segment_file = st.text_input("Segment file path", value=current_seg)

    # Upload new segment file
    uploaded = st.file_uploader("Upload new segment file", type=["json"])
    if uploaded:
        dest = SEGMENTS_DIR / uploaded.name
        dest.write_bytes(uploaded.read())
        st.success(f"Uploaded {uploaded.name} to segments/")
        st.rerun()

    # Segment preview
    segments = _load_segments({**config, "segment_file": segment_file})
    if segments:
        conditions = Counter(s["condition"] for s in segments)
        st.markdown(f"**{len(segments)} segments loaded:**")
        for cond, count in sorted(conditions.items()):
            st.markdown(f"- {cond}: {count}")

        with st.expander("Preview segments"):
            preview_data = []
            for s in segments:
                tgt_preview = s.get("target_text", "")
                if s.get("form_variant"):
                    tgt_preview = f"A: {s['form_variant'].get('A', {}).get('target_text', '')[:50]}..."
                else:
                    tgt_preview = (tgt_preview or "")[:50]
                preview_data.append({
                    "ID": s["id"],
                    "Condition": s["condition"],
                    "Error type": s.get("error_type", "-"),
                    "ToM": s.get("tom_level", "-"),
                    "Source": s["source_text"][:60],
                    "Target": tgt_preview,
                })
            st.dataframe(preview_data, use_container_width=True, hide_index=True)

    # Consent text
    st.divider()
    st.subheader("Consent Text")

    consent_cfg = config.get("consent", {})
    consent_text = st.text_area(
        "Consent text (Markdown supported)",
        value=consent_cfg.get("text", ""),
        height=150,
    )
    col5, col6 = st.columns(2)
    with col5:
        researcher_name = st.text_input("Researcher name", value=consent_cfg.get("researcher_name", ""))
    with col6:
        researcher_email = st.text_input("Researcher email", value=consent_cfg.get("researcher_email", ""))
    institution = st.text_input("Institution", value=consent_cfg.get("institution", ""))

    # Questionnaire preview
    st.divider()
    st.subheader("Post-Task Questionnaire")
    post_qs = config.get("post_task_questions", [])
    st.markdown(f"**{len(post_qs)} questions configured**")
    with st.expander("Preview questionnaire"):
        for i, q in enumerate(post_qs):
            qtype = q.get("type", "?")
            st.markdown(f"**Q{i+1}** ({qtype}): {q.get('text', '')}")
            if qtype in ("likert", "single_choice"):
                opts = q.get("labels", q.get("options", []))
                st.caption(f"Options: {', '.join(str(o) for o in opts)}")

    # Save
    st.divider()
    col_save, col_launch = st.columns(2)

    with col_save:
        if st.button("Save Configuration", type="primary"):
            updated = {
                **config,
                "study_id": study_id,
                "title": title,
                "description": description,
                "status": status,
                "form_assignment": form_assignment,
                "open_from": open_from,
                "close_at": close_at,
                "segment_file": segment_file,
                "consent": {
                    **consent_cfg,
                    "text": consent_text,
                    "researcher_name": researcher_name,
                    "researcher_email": researcher_email,
                    "institution": institution,
                },
            }
            _save_config(updated)
            st.success("Configuration saved.")

    with col_launch:
        if st.button("Launch Study App"):
            st.info(
                "To launch the Gradio study app, run:\n\n"
                f"`python {STUDY_DIR / 'study_app.py'}`\n\n"
                "Or use: `tompe-study` (after pip install)"
            )

    # Status display
    if config.get("status") == "active":
        st.divider()
        st.success(f"Study Status: ACTIVE")


# ── Monitor ───────────────────────────────────────────────────────────────────


def _page_monitor():
    config = _load_config()
    study_id = config.get("study_id", "ectel2026_pilot")

    st.subheader(f"Study: {study_id}")
    status = config.get("status", "draft")
    close_at = config.get("close_at", "?")
    if status == "active":
        st.markdown(f"**Status:** :green[ACTIVE] (closes {close_at})")
    elif status == "closed":
        st.markdown(f"**Status:** :red[CLOSED]")
    else:
        st.markdown(f"**Status:** :orange[DRAFT]")

    responses = _load_all_responses(study_id)

    if not responses:
        st.info("No responses yet. Share the study link with participants to begin collecting data.")
        return

    completed = [r for r in responses if _is_complete(r)]
    in_progress = [r for r in responses if not _is_complete(r) and r.get("segments")]
    declined = [r for r in responses if not r.get("segments") and not _is_complete(r)]

    # Participation summary
    st.divider()
    st.subheader("Participation Summary")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Completed", len(completed))
        st.metric("In progress", len(in_progress))
        st.metric("Dropped out", len(declined))
    with col2:
        form_a = sum(1 for r in completed if r.get("form") == "A")
        form_b = sum(1 for r in completed if r.get("form") == "B")
        st.metric("Form A", form_a)
        st.metric("Form B", form_b)
        balance_ok = abs(form_a - form_b) <= 5
        if balance_ok:
            st.success("Balance: OK")
        else:
            st.warning(f"Form imbalance: A={form_a}, B={form_b}")

    # Quality flags
    if completed:
        # Check for speeders
        completion_times = []
        for r in completed:
            try:
                t0 = datetime.fromisoformat(r["consent_timestamp"])
                t1 = datetime.fromisoformat(r["completion_timestamp"])
                mins = (t1 - t0).total_seconds() / 60
                completion_times.append(mins)
            except (ValueError, TypeError, KeyError):
                pass

        speeders = sum(1 for t in completion_times if t < 10)
        if speeders > 0:
            st.warning(f"  {speeders} participant(s) completed in under 10 minutes (possible non-engagement)")

    # Detection rates by condition
    st.divider()
    st.subheader("Quick Stats (completed participants)")

    if completed:
        segments_data = _load_segments(config)
        seg_lookup = {s["id"]: s for s in segments_data}

        # Aggregate detection rates and times by condition
        condition_stats: dict[str, dict] = {}
        for r in completed:
            for seg_resp in r.get("segments", []):
                seg_id = seg_resp["segment_id"]
                seg_def = seg_lookup.get(seg_id, {})
                cond = seg_resp.get("condition", seg_def.get("condition", "?"))

                # For L2, split by fluency variant
                label = cond
                fv = seg_resp.get("fluency_variant")
                if cond == "L2" and fv:
                    label = f"L2 ({fv})"

                if label not in condition_stats:
                    condition_stats[label] = {"detected": 0, "total": 0, "times": []}

                condition_stats[label]["total"] += 1
                # "detected" = marked as not acceptable (for error segments)
                # For clean segments, "detected" = false alarm (marked not acceptable)
                if not seg_resp.get("acceptable", True):
                    condition_stats[label]["detected"] += 1
                rt = seg_resp.get("response_time_seconds", 0)
                if rt > 0:
                    condition_stats[label]["times"].append(rt)

        # Display as bar chart approximation
        display_order = ["L1", "L2 (fluent)", "L2 (disfluent)", "L3", "clean"]
        for label in display_order:
            stats = condition_stats.get(label)
            if not stats or stats["total"] == 0:
                continue
            rate = stats["detected"] / stats["total"]
            med_time = median(stats["times"]) if stats["times"] else 0
            pct = int(rate * 100)

            bar_filled = int(rate * 20)
            bar_empty = 20 - bar_filled
            bar = "█" * bar_filled + "░" * bar_empty

            col_label = "Detection" if label != "clean" else "False alarm"
            st.text(f"  {label:15s}  {bar}  {pct:3d}%   median {med_time:.0f}s")

        # Completions over time
        st.divider()
        st.subheader("Completions Over Time")
        completion_dates = []
        for r in completed:
            try:
                dt = datetime.fromisoformat(r["completion_timestamp"])
                completion_dates.append(dt.date())
            except (ValueError, TypeError, KeyError):
                pass

        if completion_dates:
            date_counts = Counter(completion_dates)
            dates_sorted = sorted(date_counts.keys())
            cumulative = []
            running = 0
            chart_data = []
            for d in dates_sorted:
                running += date_counts[d]
                chart_data.append({"date": d.isoformat(), "completions": running})
            st.line_chart(
                data={row["date"]: row["completions"] for row in chart_data},
            )

        # Questionnaire summary
        st.divider()
        st.subheader("Questionnaire Summary")

        q_data = [r.get("questionnaire", {}) for r in completed if r.get("questionnaire")]
        if q_data:
            # Language proficiency
            fr_scores = [q.get("lang_fr") for q in q_data if q.get("lang_fr") is not None]
            en_scores = [q.get("lang_en") for q in q_data if q.get("lang_en") is not None]
            if fr_scores:
                numeric_fr = [s if isinstance(s, (int, float)) else 0 for s in fr_scores]
                if any(numeric_fr):
                    st.markdown(f"**Mean FR proficiency:** {mean(numeric_fr):.1f} / 5")
            if en_scores:
                numeric_en = [s if isinstance(s, (int, float)) else 0 for s in en_scores]
                if any(numeric_en):
                    st.markdown(f"**Mean EN proficiency:** {mean(numeric_en):.1f} / 5")

            # Fields of study
            fields = [q.get("field") for q in q_data if q.get("field")]
            if fields:
                field_counts = Counter(fields)
                top_fields = field_counts.most_common(5)
                st.markdown("**Fields of study:** " + ", ".join(f"{f} ({c})" for f, c in top_fields))

            # MT usage
            mt_usage = [q.get("mt_usage") for q in q_data if q.get("mt_usage")]
            if mt_usage:
                usage_counts = Counter(mt_usage)
                st.markdown("**MT usage:** " + ", ".join(f"{u} ({c})" for u, c in usage_counts.most_common()))

    if st.button("Refresh", type="secondary"):
        st.rerun()


# ── Export ────────────────────────────────────────────────────────────────────


def _page_export():
    config = _load_config()
    study_id = config.get("study_id", "ectel2026_pilot")
    responses = _load_all_responses(study_id)

    completed = [r for r in responses if _is_complete(r)]
    st.subheader(f"Study: {study_id}")
    st.markdown(f"**Completed participants:** {len(completed)}")

    if not completed:
        st.info("No completed responses to export.")
        return

    st.divider()
    st.subheader("Export Format")

    fmt = st.radio(
        "Format",
        [
            "CSV -- one row per segment per participant",
            "JSON -- one file per participant (raw format)",
            "CSV (wide) -- one row per participant, columns per segment",
        ],
        index=0,
    )

    st.divider()
    st.subheader("Include")

    inc_segments = st.checkbox("Segment responses", value=True)
    inc_questionnaire = st.checkbox("Post-task questionnaire", value=True)
    inc_timing = st.checkbox("Timing data", value=True)
    inc_partial = st.checkbox("Partial completions (in-progress participants)", value=False)

    source_responses = completed
    if inc_partial:
        source_responses = responses

    # CSV long preview
    if "CSV --" in fmt and fmt.startswith("CSV"):
        st.divider()
        st.subheader("CSV Preview (first 5 rows)")
        preview_rows = _build_csv_rows(source_responses, inc_segments, inc_questionnaire, inc_timing)[:5]
        if preview_rows:
            st.dataframe(preview_rows, use_container_width=True, hide_index=True)

    st.divider()

    if st.button("Generate Export", type="primary"):
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if "JSON" in fmt:
            # ZIP of JSON files
            export_path = EXPORTS_DIR / f"{study_id}_responses.json"
            with open(export_path, "w") as f:
                json.dump(source_responses, f, indent=2, ensure_ascii=False)
            st.success(f"Exported to {export_path}")
            with open(export_path) as f:
                st.download_button(
                    "Download JSON",
                    f.read(),
                    file_name=f"{study_id}_responses.json",
                    mime="application/json",
                )

        elif "wide" in fmt:
            rows = _build_csv_wide_rows(source_responses, inc_questionnaire)
            export_path = EXPORTS_DIR / f"{study_id}_responses_wide.csv"
            _write_csv(export_path, rows)
            st.success(f"Exported to {export_path}")
            with open(export_path) as f:
                st.download_button(
                    "Download CSV (wide)",
                    f.read(),
                    file_name=f"{study_id}_responses_wide.csv",
                    mime="text/csv",
                )

        else:
            rows = _build_csv_rows(source_responses, inc_segments, inc_questionnaire, inc_timing)
            export_path = EXPORTS_DIR / f"{study_id}_responses.csv"
            _write_csv(export_path, rows)
            st.success(f"Exported to {export_path}")
            with open(export_path) as f:
                st.download_button(
                    "Download CSV",
                    f.read(),
                    file_name=f"{study_id}_responses.csv",
                    mime="text/csv",
                )


def _build_csv_rows(
    responses: list[dict],
    inc_segments: bool,
    inc_questionnaire: bool,
    inc_timing: bool,
) -> list[dict]:
    """Build CSV long-format rows: one row per segment per participant."""
    rows = []
    for r in responses:
        pid = r.get("participant_id", "?")
        form = r.get("form", "?")
        q = r.get("questionnaire", {}) or {}

        if not inc_segments:
            # One row per participant with questionnaire only
            row = {"participant_id": pid, "form": form}
            if inc_questionnaire:
                row.update({
                    "lang_fr": q.get("lang_fr"),
                    "lang_en": q.get("lang_en"),
                    "field": q.get("field"),
                    "study_level": q.get("study_level"),
                    "mt_usage": q.get("mt_usage"),
                    "strategy": q.get("strategy"),
                })
            rows.append(row)
            continue

        for i, seg in enumerate(r.get("segments", [])):
            row = {
                "participant_id": pid,
                "form": form,
                "segment_id": seg.get("segment_id"),
                "segment_order_position": i + 1,
                "condition": seg.get("condition"),
                "fluency_variant": seg.get("fluency_variant"),
                "tom_level": seg.get("tom_level"),
                "acceptable": seg.get("acceptable"),
                "justification": seg.get("justification"),
                "confidence": seg.get("confidence"),
            }
            if inc_timing:
                row["displayed_at"] = seg.get("displayed_at")
                row["submitted_at"] = seg.get("submitted_at")
                row["response_time_seconds"] = seg.get("response_time_seconds")
            if inc_questionnaire:
                row["lang_fr"] = q.get("lang_fr")
                row["lang_en"] = q.get("lang_en")
                row["field"] = q.get("field")
                row["study_level"] = q.get("study_level")
                row["mt_usage"] = q.get("mt_usage")
                row["strategy"] = q.get("strategy")
            rows.append(row)
    return rows


def _build_csv_wide_rows(responses: list[dict], inc_questionnaire: bool) -> list[dict]:
    """Build CSV wide-format: one row per participant, columns per segment."""
    rows = []
    for r in responses:
        row = {
            "participant_id": r.get("participant_id"),
            "form": r.get("form"),
            "consent_timestamp": r.get("consent_timestamp"),
            "completion_timestamp": r.get("completion_timestamp"),
        }
        for i, seg in enumerate(r.get("segments", [])):
            prefix = f"seg{i+1}"
            row[f"{prefix}_id"] = seg.get("segment_id")
            row[f"{prefix}_condition"] = seg.get("condition")
            row[f"{prefix}_acceptable"] = seg.get("acceptable")
            row[f"{prefix}_confidence"] = seg.get("confidence")
            row[f"{prefix}_rt"] = seg.get("response_time_seconds")
        if inc_questionnaire:
            q = r.get("questionnaire", {}) or {}
            for key in ["lang_fr", "lang_en", "field", "study_level", "mt_usage", "strategy"]:
                row[f"q_{key}"] = q.get(key)
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write a list of dicts to CSV."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    # Ensure all keys are present
    for row in rows[1:]:
        for k in row:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
