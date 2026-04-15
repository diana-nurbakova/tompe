"""Gradio student interface for ToM-PE.

Provides: login, exercise list, core annotation workflow (3 phases),
span selection, MQM classification, justification, and feedback display.
Supports L0-L3 scaffolding levels, evaluation and post-editing modes.
"""

import json
import time
from pathlib import Path
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
    level = exercise.get("level", "analyst")
    mode = exercise.get("mode", "evaluation")
    name = exercise.get("name", "Unnamed Exercise")
    n_items = len(exercise.get("item_ids", []))
    domain = exercise.get("domain", "")
    direction = exercise.get("direction", "")
    score = assignment.get("score")
    current = assignment.get("current_item_index", 0)

    level_labels = {
        "navigator": "L0 Navigator", "scout": "L1 Scout",
        "analyst": "L2 Analyst", "expert": "L3 Expert",
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


_BADGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "badges"


_badge_cache: dict[str, str] = {}


def _badge_path(filename: str) -> str:
    """Return a base64 data URI for a badge image (no file serving needed)."""
    if filename in _badge_cache:
        return _badge_cache[filename]

    import base64
    filepath = _BADGES_DIR / filename
    if filepath.exists():
        data = base64.b64encode(filepath.read_bytes()).decode()
        uri = f"data:image/jpeg;base64,{data}"
    else:
        # Transparent 1x1 pixel fallback
        uri = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"

    _badge_cache[filename] = uri
    return uri


def _build_badge_collection_html(badge_data: dict) -> str:
    """Build HTML for the Badge Collection panel in My Progress."""
    if not badge_data:
        return ""

    html = '<div style="font-family:system-ui;padding:16px;background:#f8fafc;border-radius:12px;margin-bottom:16px;">'
    html += '<h3 style="margin-top:0;">My Badges</h3>'

    # Progression badges
    html += '<div style="margin-bottom:20px;">'
    html += '<h4 style="color:#6b7280;font-size:14px;text-transform:uppercase;letter-spacing:1px;">Progression</h4>'
    html += '<div style="display:flex;gap:12px;flex-wrap:wrap;">'
    prog_icons = {
        "navigator": _badge_path("scaffolding_navigator.jpg"),
        "scout": _badge_path("scaffolding_scout.jpg"),
        "analyst": _badge_path("scaffolding_analyst.jpg"),
        "expert": _badge_path("scaffolding_expert.jpg"),
    }
    prog_colors = {"navigator": "#E69F00", "scout": "#009E73", "analyst": "#0072B2", "expert": "#D4AF37"}
    for badge in badge_data.get("progression", []):
        bid = badge["badge_id"]
        earned = badge["earned"]
        name = badge["display_name"]
        color = prog_colors.get(bid, "#D4AF37")
        opacity = "1" if earned else "0.35"
        border_color = color if earned else "#4A4A4A"
        filter_css = "none" if earned else "grayscale(100%)"
        lock_icon = "" if earned else '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:20px;opacity:0.7;">&#128274;</div>'
        html += f'''
        <div style="text-align:center;width:72px;" title="{name}{" — Earned!" if earned else " — Locked"}">
            <div style="position:relative;width:64px;height:64px;margin:0 auto 4px;">
                <img src="{prog_icons.get(bid, "")}" style="width:64px;height:64px;border-radius:50%;
                    border:3px solid {border_color};opacity:{opacity};filter:{filter_css};object-fit:cover;" />
                {lock_icon}
            </div>
            <div style="font-size:11px;font-weight:600;color:{'#1B2838' if earned else '#9ca3af'};">{name}</div>
        </div>'''
    html += '</div></div>'

    # Specialisation badges
    html += '<div style="margin-bottom:20px;">'
    html += '<h4 style="color:#6b7280;font-size:14px;text-transform:uppercase;letter-spacing:1px;">Specialisation</h4>'
    html += '<div style="display:flex;gap:12px;flex-wrap:wrap;">'
    tier_colors = {"bronze": "#B87333", "silver": "#C0C0C0", "gold": "#D4AF37"}
    tier_labels = {"bronze": "B", "silver": "S", "gold": "G"}
    # Map badge_id → file name prefix (without tier suffix)
    spec_file_map = {
        "accuracy_hunter": "accuracy",
        "gap_finder": "gapfinder",
        "surplus_spotter": "surplusspotter",
        "code_switcher": "codeswitcher",
        "grammar_guard": "grammarguard",
        "sharp_eye": "sharpeye",
        "punctuation_pro": "punctuationpro",
        "term_specialist": "termspecialist",
        "style_sentinel": "stylesentinel",
        "locale_expert": "localeexpert",
    }
    for badge in badge_data.get("specialisation", []):
        bid = badge["badge_id"]
        name = badge["display_name"]
        highest = badge.get("highest_tier")
        count = badge.get("current_count", 0)
        next_thresh = badge.get("next_threshold")
        next_tier = badge.get("next_tier")

        # Determine icon path based on tier
        icon_tier = highest if highest else "bronze"
        file_prefix = spec_file_map.get(bid, bid.replace("_", ""))
        icon_path = _badge_path(f"specialisation_{file_prefix}_{icon_tier}.jpg")

        earned = highest is not None
        border_color = tier_colors.get(highest, "#4A4A4A") if earned else "#4A4A4A"
        opacity = "1" if earned else "0.35"
        filter_css = "none" if earned else "grayscale(100%)"
        lock_icon = "" if earned else '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:16px;opacity:0.7;">&#128274;</div>'

        # Tier indicator
        tier_badge = ""
        if highest:
            tier_badge = f'<div style="position:absolute;top:-2px;right:-2px;width:18px;height:18px;border-radius:50%;background:{tier_colors[highest]};color:white;font-size:10px;font-weight:bold;display:flex;align-items:center;justify-content:center;">{tier_labels[highest]}</div>'

        # Progress text
        progress_text = ""
        if next_thresh is not None:
            progress_text = f'<div style="font-size:10px;color:#9ca3af;">{count}/{next_thresh}</div>'
        elif highest == "gold":
            progress_text = f'<div style="font-size:10px;color:#D4AF37;">MAX</div>'

        tooltip = f"{name}"
        if highest:
            tooltip += f" ({highest.title()})"
        if next_thresh:
            tooltip += f" — {count}/{next_thresh} toward {next_tier}"

        html += f'''
        <div style="text-align:center;width:72px;" title="{tooltip}">
            <div style="position:relative;width:64px;height:64px;margin:0 auto 4px;">
                <img src="{icon_path}" style="width:64px;height:64px;border-radius:50%;
                    border:3px solid {border_color};opacity:{opacity};filter:{filter_css};object-fit:cover;" />
                {lock_icon}{tier_badge}
            </div>
            <div style="font-size:10px;font-weight:600;color:{'#1B2838' if earned else '#9ca3af'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</div>
            {progress_text}
        </div>'''
    html += '</div></div>'

    # Behaviour badges
    html += '<div style="margin-bottom:16px;">'
    html += '<h4 style="color:#6b7280;font-size:14px;text-transform:uppercase;letter-spacing:1px;">Achievements</h4>'
    html += '<div style="display:flex;gap:12px;flex-wrap:wrap;">'
    behav_icons = {
        "false_positive_discipline": _badge_path("behaviour_falsepositivediscipline.jpg"),
        "clean_sheet": _badge_path("behaviour_cleansheet.jpg"),
        "trap_detector": _badge_path("behaviour_trapdetector.jpg"),
    }
    behav_colors = {"false_positive_discipline": "#CC79A7", "clean_sheet": "#D4AF37", "trap_detector": "#D55E00"}
    for badge in badge_data.get("behaviour", []):
        bid = badge["badge_id"]
        name = badge["display_name"]
        earned = badge["earned"]
        color = behav_colors.get(bid, "#CC79A7")
        opacity = "1" if earned else "0.35"
        border_color = color if earned else "#4A4A4A"
        filter_css = "none" if earned else "grayscale(100%)"
        lock_icon = "" if earned else '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:16px;opacity:0.7;">&#128274;</div>'

        # Clean sheet counter
        counter = ""
        if bid == "clean_sheet" and earned and badge.get("count", 1) > 1:
            counter = f'<div style="position:absolute;bottom:-2px;right:-2px;min-width:18px;height:18px;border-radius:9px;background:#D4AF37;color:white;font-size:10px;font-weight:bold;display:flex;align-items:center;justify-content:center;padding:0 4px;">&times;{badge["count"]}</div>'

        # Progress for trap detector
        progress_text = ""
        if bid == "trap_detector" and not earned:
            prog = badge.get("progress", 0)
            progress_text = f'<div style="font-size:10px;color:#9ca3af;">{prog}/10</div>'

        html += f'''
        <div style="text-align:center;width:72px;" title="{name}{" — Earned!" if earned else " — " + badge.get("description", "")}">
            <div style="position:relative;width:64px;height:64px;margin:0 auto 4px;">
                <img src="{behav_icons.get(bid, "")}" style="width:64px;height:64px;border-radius:50%;
                    border:3px solid {border_color};opacity:{opacity};filter:{filter_css};object-fit:cover;" />
                {lock_icon}{counter}
            </div>
            <div style="font-size:10px;font-weight:600;color:{'#1B2838' if earned else '#9ca3af'};">{name}</div>
            {progress_text}
        </div>'''
    html += '</div></div>'

    # Total XP
    total_xp = badge_data.get("total_xp", 0)
    html += f'''
    <div style="text-align:center;padding:12px;background:linear-gradient(135deg,#1B2838,#2d3748);
        border-radius:8px;color:white;">
        <div style="font-size:12px;text-transform:uppercase;letter-spacing:2px;color:#D4AF37;margin-bottom:4px;">Total XP</div>
        <div style="font-size:28px;font-weight:bold;color:#D4AF37;">{total_xp:,}</div>
    </div>'''

    html += '</div>'
    return html


def _build_skill_radar_html(skill_data: dict, current_level: str = "navigator") -> str:
    """Build SVG skill radar chart for the 7 competency skills."""
    if not skill_data:
        return ""

    skills = [
        ("S1", "Surface form"),
        ("S2", "Grammar"),
        ("S3", "Lexical accuracy"),
        ("S4", "Completeness"),
        ("S5", "Terminology"),
        ("S6", "Style & register"),
        ("S7", "Contextual coherence"),
    ]

    level_colors = {
        "navigator": "#E69F00", "scout": "#009E73",
        "analyst": "#0072B2", "expert": "#D4AF37",
    }
    fill_color = level_colors.get(current_level, "#3b82f6")

    import math as _math
    n = len(skills)
    cx, cy = 150, 150
    max_r = 110
    mastery_r = max_r * 0.98

    # Build SVG
    svg = f'<svg viewBox="-50 -30 400 360" width="400" height="360" xmlns="http://www.w3.org/2000/svg">'

    # Background grid circles
    for frac in [0.25, 0.5, 0.75, 1.0]:
        r = max_r * frac
        svg += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="0.5"/>'

    # Mastery threshold dashed circle
    svg += f'<circle cx="{cx}" cy="{cy}" r="{mastery_r}" fill="none" stroke="#D4AF37" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>'

    # Axis lines and labels
    for i, (skill_id, label) in enumerate(skills):
        angle = -_math.pi / 2 + (2 * _math.pi * i / n)
        x_end = cx + max_r * _math.cos(angle)
        y_end = cy + max_r * _math.sin(angle)
        svg += f'<line x1="{cx}" y1="{cy}" x2="{x_end}" y2="{y_end}" stroke="#d1d5db" stroke-width="0.5"/>'

        # Label position (slightly beyond the axis)
        lx = cx + (max_r + 30) * _math.cos(angle)
        ly = cy + (max_r + 30) * _math.sin(angle)
        anchor = "middle"
        if _math.cos(angle) > 0.3:
            anchor = "start"
        elif _math.cos(angle) < -0.3:
            anchor = "end"
        svg += f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" dominant-baseline="central" font-size="8" fill="#6b7280" font-family="system-ui">{skill_id} {label}</text>'

    # Data polygon
    points = []
    for i, (skill_id, _) in enumerate(skills):
        angle = -_math.pi / 2 + (2 * _math.pi * i / n)
        val = skill_data.get(skill_id, 0)
        r = max_r * val
        x = cx + r * _math.cos(angle)
        y = cy + r * _math.sin(angle)
        points.append(f"{x},{y}")

    pts = " ".join(points)
    svg += f'<polygon points="{pts}" fill="{fill_color}" fill-opacity="0.25" stroke="{fill_color}" stroke-width="2"/>'

    # Data points
    for i, (skill_id, _) in enumerate(skills):
        angle = -_math.pi / 2 + (2 * _math.pi * i / n)
        val = skill_data.get(skill_id, 0)
        r = max_r * val
        x = cx + r * _math.cos(angle)
        y = cy + r * _math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="3" fill="{fill_color}" stroke="white" stroke-width="1"/>'

    svg += '</svg>'

    # Legend
    level_label = current_level.title() if current_level else "Navigator"
    html = f'''
    <div style="font-family:system-ui;padding:16px;background:#f8fafc;border-radius:12px;margin-bottom:16px;">
        <h3 style="margin-top:0;">Skill Radar</h3>
        <div style="text-align:center;">{svg}</div>
        <div style="display:flex;gap:16px;justify-content:center;font-size:12px;color:#6b7280;margin-top:8px;">
            <span><span style="display:inline-block;width:12px;height:2px;background:{fill_color};margin-right:4px;vertical-align:middle;"></span>Current</span>
            <span><span style="display:inline-block;width:12px;height:2px;background:#D4AF37;border-top:1px dashed #D4AF37;margin-right:4px;vertical-align:middle;"></span>Mastery (0.98)</span>
        </div>
        <div style="text-align:center;margin-top:8px;font-size:13px;color:#374151;">
            Level: <strong>{level_label}</strong>
        </div>
    </div>'''
    return html


def _build_badge_notification_html(badge_result: dict) -> str:
    """Build HTML for badge notification toasts after feedback."""
    newly_earned = badge_result.get("newly_earned_badges", [])
    xp_earned = badge_result.get("xp_earned", 0)

    if not newly_earned and xp_earned <= 0:
        return ""

    html = ""

    # XP earned bar
    if xp_earned > 0:
        total_xp = badge_result.get("total_xp", 0)
        html += f'''
        <div style="background:linear-gradient(135deg,#1B2838,#2d3748);border-radius:8px;padding:12px 16px;
            margin-top:12px;display:flex;align-items:center;justify-content:space-between;color:white;">
            <span style="font-size:14px;">+{xp_earned} XP earned</span>
            <span style="color:#D4AF37;font-weight:bold;">Total: {total_xp:,} XP</span>
        </div>'''

    # Badge notifications
    for badge in newly_earned:
        name = badge.get("display_name", "Badge")
        tier = badge.get("tier", "none")
        category = badge.get("category", "")
        desc = badge.get("description", "")

        tier_text = f" ({tier.title()})" if tier != "none" else ""
        tier_color = {"bronze": "#B87333", "silver": "#C0C0C0", "gold": "#D4AF37"}.get(tier, "#D4AF37")

        # Try to find badge icon
        icon_path = ""
        if category == "progression":
            icon_path = _badge_path(f"scaffolding_{badge['badge_id']}.jpg")
        elif category == "specialisation":
            spec_file_map = {
                "accuracy_hunter": "accuracy", "gap_finder": "gapfinder",
                "surplus_spotter": "surplusspotter", "code_switcher": "codeswitcher",
                "grammar_guard": "grammarguard", "sharp_eye": "sharpeye",
                "punctuation_pro": "punctuationpro", "term_specialist": "termspecialist",
                "style_sentinel": "stylesentinel", "locale_expert": "localeexpert",
            }
            prefix = spec_file_map.get(badge["badge_id"], badge["badge_id"].replace("_", ""))
            icon_path = _badge_path(f"specialisation_{prefix}_{tier}.jpg")
        elif category == "behaviour":
            icon_path = _badge_path(f"behaviour_{badge['badge_id'].replace('_', '')}.jpg")

        html += f'''
        <div style="background:linear-gradient(135deg,#1B2838,#2d3748);border:2px solid {tier_color};
            border-radius:12px;padding:16px;margin-top:12px;display:flex;align-items:center;gap:16px;
            animation:badgeFadeIn 0.5s ease-out;">
            <div style="flex-shrink:0;">
                <img src="{icon_path}" style="width:64px;height:64px;border-radius:50%;
                    border:3px solid {tier_color};object-fit:cover;"
                    onerror="this.style.display='none'" />
            </div>
            <div>
                <div style="color:{tier_color};font-size:12px;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px;">
                    Badge Earned!
                </div>
                <div style="color:white;font-size:16px;font-weight:bold;">
                    {name}{tier_text}
                </div>
                <div style="color:#9ca3af;font-size:13px;">{desc}</div>
            </div>
        </div>'''

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


# ── Adaptive justification prompts ───────────────────────────────────────────

_SURFACE_TAGS = {PrimaryTag.SPELLING, PrimaryTag.PUNCTUATION, PrimaryTag.GRAMMAR}
_MEANING_TAGS = {
    PrimaryTag.MISTRANSLATION, PrimaryTag.OMISSION, PrimaryTag.ADDITION,
    PrimaryTag.UNTRANSLATED, PrimaryTag.TERMINOLOGY,
}
_PRAGMATIC_TAGS = {PrimaryTag.STYLE, PrimaryTag.LOCALE}


def _get_justification_prompt(primary_tag: str) -> str:
    """Return an adaptive prompt based on the error's category."""
    if primary_tag in _SURFACE_TAGS:
        return "What's wrong here?"
    if primary_tag in _PRAGMATIC_TAGS:
        return "Why is this a problem and how would a reader misinterpret this?"
    # Default for meaning/terminology and unknown
    return "Why is this a problem?"


def _build_error_label_html(idx: int, annotation: dict, item_text: str = "") -> str:
    """Build an HTML card for one annotated error in the justification panel."""
    start = annotation.get("span_start", 0)
    end = annotation.get("span_end", 0)
    span_text = item_text[start:end] if item_text else f"chars {start}-{end}"
    tag = annotation.get("primary_tag", "unknown")
    severity = annotation.get("severity_label", annotation.get("severity", ""))
    tag_label = TAG_LABELS.get(tag, tag) if tag else "Unknown"

    return (
        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;'
        f'padding:8px 12px;margin-bottom:4px;">'
        f'<strong>Error {idx + 1}:</strong> '
        f'<span style="background:#fef3c7;padding:2px 6px;border-radius:3px;">'
        f'"{span_text[:60]}{"..." if len(span_text) > 60 else ""}"</span> '
        f'<span style="color:#6b7280;">— {tag_label}'
        f'{" / " + severity if severity else ""}</span>'
        f'</div>'
    )


# ── Main app builder ─────────────────────────────────────────────────────────


def build_student_app() -> gr.Blocks:
    """Build the Gradio student interface."""

    with gr.Blocks(
        title="ToM-PE — Student",
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
        item_start_time = gr.State(None)

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

                    # Phase indicator (kept as hidden state for handler compatibility)
                    phase_html = gr.HTML("", visible=False)

                    # Task description
                    task_desc = gr.Markdown("")

                    # Source + Translation side by side
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Source Text")
                            source_html = gr.HTML("")
                        with gr.Column():
                            gr.Markdown("### Translation")
                            translation_html = gr.HTML("")

                    # Textbox for span selection JS → Python communication
                    span_output = gr.Textbox(
                        elem_id="span-output-main",
                        label="Selected text (drag from translation, or type the error/context text)",
                        lines=1, max_lines=1, interactive=True,
                        placeholder="For omissions: type the surrounding context where text is missing...",
                    )

                    # Annotation chips
                    chips_html = gr.HTML("")

                    # ── Phase panels using Tabs (Gradio 6 compatible) ────
                    with gr.Tabs(elem_id="phase-tabs") as phase_tabs:
                        # ── Classification panel (Phase 1) ──────────────
                        with gr.TabItem("1. Annotate", id=10) as classification_panel:
                            # Error Types Guide (collapsible)
                            with gr.Accordion("Error Types Guide", open=False):
                                gr.HTML(_build_error_guide_html())

                            selection_label = gr.Markdown(
                                "*Drag and drop text from the translation into the field above, then classify the error.*"
                            )

                            # Category pills with colored dots
                            gr.Markdown("**Error Category:**")
                            pill_css_parts = []
                            for tag in STUDENT_PILL_CATEGORIES:
                                dot_color = TAG_COLORS.get(tag, {}).get("dot", "#666")
                                safe_id = tag.replace(".", "_").lower() if isinstance(tag, str) else str(tag).replace(".", "_").lower()
                                pill_css_parts.append(
                                    f'#pill-{safe_id} {{ border-left: 4px solid {dot_color} !important; }}'
                                )
                            gr.HTML(f'<style>{"".join(pill_css_parts)}</style>')

                            with gr.Row():
                                cat_buttons = {}
                                for tag in STUDENT_PILL_CATEGORIES:
                                    label = TAG_LABELS.get(tag, tag)
                                    dot_color = TAG_COLORS.get(tag, {}).get("dot", "#666")
                                    safe_id = tag.replace(".", "_").lower() if isinstance(tag, str) else str(tag).replace(".", "_").lower()
                                    cat_buttons[tag] = gr.Button(
                                        f"● {label}",
                                        size="sm",
                                        elem_classes=["pill-btn"],
                                        elem_id=f"pill-{safe_id}",
                                    )

                            selected_category = gr.State(None)

                            subtype_label = gr.Markdown("", visible=False)
                            subtype_dropdown = gr.Dropdown(
                                label="Subtype", choices=[], visible=False, interactive=True
                            )

                            severity_radio = gr.Radio(
                                choices=["minor", "major", "critical"],
                                label="Severity",
                                value="major",
                            )

                            with gr.Row():
                                add_error_btn = gr.Button("Add Error", variant="primary")
                                cancel_btn = gr.Button("Cancel")

                            errors_summary_html = gr.HTML(
                                '<div style="color:#9ca3af;font-size:14px;padding:8px 0;">'
                                'No errors marked yet. Select text above to annotate.</div>'
                            )

                            with gr.Row():
                                proceed_justify_btn = gr.Button(
                                    "Proceed to Justification ->",
                                    variant="primary",
                                )

                        # ── Justification panel (Phase 2) ───────────────
                        MAX_PER_ERROR = 8

                        with gr.TabItem("2. Justify", id=11) as justification_panel:
                            justify_header = gr.HTML(
                                '<div style="background:#eff6ff;border:2px solid #3b82f6;'
                                'border-radius:8px;padding:16px;margin-bottom:12px;">'
                                '<h3 style="margin:0 0 8px 0;color:#1d4ed8;">Justify Your Reasoning</h3>'
                                '<p style="margin:0;color:#374151;">'
                                'Before seeing the feedback, explain your reasoning for each annotation.</p>'
                                '</div>'
                            )

                            # Mode A: Global free-text (legacy)
                            with gr.Column(visible=False) as justify_freetext:
                                justify_text = gr.Textbox(
                                    label="Explain your reasoning",
                                    lines=4,
                                    placeholder=(
                                        "What did the MT system misunderstand? "
                                        "What was the author's intent? "
                                        "How would a reader misinterpret this?"
                                    ),
                                )

                            # Mode B: Per-error short (adaptive prompt)
                            with gr.Column(visible=False) as justify_per_error_short:
                                pe_short_groups = []
                                pe_short_labels = []
                                pe_short_texts = []
                                for i in range(MAX_PER_ERROR):
                                    with gr.Group(visible=False) as grp:
                                        lbl = gr.HTML("")
                                        txt = gr.Textbox(
                                            label="Your reasoning",
                                            lines=2,
                                            placeholder="Explain why this is an error...",
                                        )
                                    pe_short_groups.append(grp)
                                    pe_short_labels.append(lbl)
                                    pe_short_texts.append(txt)

                            # Mode C: Per-error structured (3 ToM fields)
                            with gr.Column(visible=False) as justify_per_error_struct:
                                pe_struct_groups = []
                                pe_struct_labels = []
                                pe_struct_mt = []
                                pe_struct_author = []
                                pe_struct_reader = []
                                for i in range(MAX_PER_ERROR):
                                    with gr.Group(visible=False) as grp:
                                        lbl = gr.HTML("")
                                        mt = gr.Textbox(
                                            label="What did the MT system misunderstand?",
                                            lines=2,
                                        )
                                        au = gr.Textbox(
                                            label="What was the author's actual intent?",
                                            lines=2,
                                        )
                                        rd = gr.Textbox(
                                            label="How would a reader misinterpret this?",
                                            lines=2,
                                        )
                                    pe_struct_groups.append(grp)
                                    pe_struct_labels.append(lbl)
                                    pe_struct_mt.append(mt)
                                    pe_struct_author.append(au)
                                    pe_struct_reader.append(rd)

                            # Confidence rating (spec requirement)
                            confidence_slider = gr.Slider(
                                minimum=1, maximum=5, step=1, value=3,
                                label="How confident are you in your annotations? (1 = not at all, 5 = very confident)",
                            )

                            submit_justify_btn = gr.Button(
                                "Submit & See Feedback", variant="primary"
                            )

                        # ── Feedback panel (Phase 3) ─────────────────
                        with gr.TabItem("3. Feedback", id=12) as feedback_panel:
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
                    refresh_progress_btn = gr.Button("Refresh Progress", size="sm")

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
                return [gr.update()] * 18

            data = json.loads(selected_json)
            assignment = data["assignment"]
            exercise = data["exercise"]
            item_idx = assignment.get("current_item_index", 0)
            item_ids = exercise.get("item_ids", [])

            if not item_ids:
                return [gr.update()] * 18

            # Load the current item
            try:
                item = api.get_item(item_ids[min(item_idx, len(item_ids) - 1)])
            except Exception:
                item = None

            if not item:
                return [gr.update()] * 18

            # Update assignment status
            if assignment["status"] == "not_started":
                try:
                    api.update_assignment(
                        assignment["assignment_id"],
                        {"status": "in_progress", "started_at": str(__import__("datetime").datetime.now())},
                    )
                except Exception:
                    pass

            level = exercise.get("level", "analyst")
            mode = exercise.get("mode", "evaluation")
            task_descriptions = {
                "navigator": (
                    "Pre-annotated errors are highlighted below. Your task is to verify each "
                    "annotation: **confirm** correct ones, **dispute** incorrect ones, and explain "
                    "your reasoning. Some annotations may be incorrect."
                ),
                "scout": (
                    "Approximate error regions are highlighted in yellow. Within each region, "
                    "**drag and drop the exact error text** into the 'Selected text' field below. "
                    "Then classify the error type, assign a severity, and explain your reasoning."
                ),
                "analyst": (
                    "Read the source text and translation carefully. **Drag and drop any text you "
                    "believe contains an error** from the translation into the 'Selected text' field "
                    "below. For **omissions**, type the surrounding context where content is missing. "
                    "Classify each error by type and severity, then explain your reasoning."
                ),
                "expert": (
                    "Evaluate this translation independently. **Drag and drop suspected errors** from "
                    "the translation into the 'Selected text' field. Note: some segments may be "
                    "error-free — marking a correct segment as erroneous counts against your score."
                ),
            }
            if mode == "postediting":
                task_text = (
                    "Read the source text and translation carefully. **Edit the translation directly** "
                    "to correct any errors. For each significant edit, explain why the change was needed."
                )
            else:
                task_text = task_descriptions.get(level, task_descriptions["analyst"])

            # Render source and translation
            source_text = item.get("source_text", "")
            presented_text = item.get("presented_text", "")

            # Level-specific annotations for display
            annotations_for_display = []
            if level == "navigator":
                # L0: Show pre-annotated errors (with some false annotations)
                for err in item.get("errors", []):
                    annotations_for_display.append({
                        "span_start": err.get("span_start", 0),
                        "span_end": err.get("span_end", 0),
                        "primary_tag": err.get("primary_tag", ""),
                        "annotation_id": err.get("error_id", str(uuid4())),
                        "mqm_label": f"{err.get('primary_tag', '')} > {err.get('error_type', '')}",
                        "severity_label": err.get("severity", ""),
                    })
                # Also add any false annotations from annotation_config
                for ann in item.get("annotations", []):
                    annotations_for_display.append({
                        "span_start": ann.get("span_start", 0),
                        "span_end": ann.get("span_end", 0),
                        "primary_tag": ann.get("primary_tag", ""),
                        "annotation_id": ann.get("error_id", str(uuid4())),
                        "mqm_label": ann.get("mqm_label", ""),
                        "severity_label": ann.get("severity_label", ""),
                    })
            elif level == "scout":
                # L1: Show approximate error regions as yellow highlights
                for err in item.get("errors", []):
                    start = max(0, err.get("span_start", 0) - 5)
                    end = min(len(presented_text), err.get("span_end", 0) + 5)
                    annotations_for_display.append({
                        "span_start": start,
                        "span_end": end,
                        "primary_tag": "",
                        "annotation_id": str(uuid4()),
                        "is_region_hint": True,
                    })

            # L3 Expert: add warning about clean segments
            if level == "expert":
                task_text += (
                    "\n\n**Note:** Some segments in this exercise contain no errors. "
                    "Marking a correct segment as erroneous will reduce your score."
                )

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
                gr.update(selected=10),  # phase_tabs → Annotate tab
                gr.update(visible=show_pe),  # pe_panel
                gr.update(value=presented_text if show_pe else ""),  # pe_textbox
                "annotate",  # current_phase
                time.time(),  # item_start_time
                gr.update(value=_build_errors_summary([])),  # errors_summary_html
            )

        def handle_span_selection(span_data, annotations, current_item):
            """Handle text selection from the span selector JS."""
            if not span_data:
                return annotations, gr.update(), gr.update(), gr.update(), None

            try:
                data = json.loads(span_data)
            except json.JSONDecodeError:
                return annotations, gr.update(), gr.update(), gr.update(), None

            # Handle annotation removal
            if "remove" in data:
                ann_id = data["remove"]
                annotations = [a for a in annotations if a.get("annotation_id") != ann_id]
                text = current_item.get("presented_text", "") if current_item else ""
                html = render_text_with_highlights(text, annotations)
                chips = render_annotation_chips(annotations)
                return annotations, gr.update(value=html), gr.update(value=chips), gr.update(), None

            # New selection — store in current_selection state
            return (
                annotations,
                gr.update(),
                gr.update(),
                gr.update(value=f'Classify: **"{data.get("text", "")[:50]}"**'),
                data,  # Store parsed selection in current_selection
            )

        def handle_category_click(tag, current_sel, span_data):
            """Handle MQM category pill button click."""
            subtypes = SUBTYPES.get(tag, [])
            return (
                tag,
                gr.update(visible=bool(subtypes), choices=subtypes, value=subtypes[0] if subtypes else None),
                gr.update(visible=bool(subtypes)),
            )

        def _build_errors_summary(annotations):
            """Build a visible summary of all annotated errors."""
            if not annotations:
                return (
                    '<div style="color:#9ca3af;font-size:14px;padding:8px 0;">'
                    'No errors marked yet. Select text above to annotate.</div>'
                )
            html = '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin:8px 0;">'
            html += f'<div style="font-weight:600;margin-bottom:8px;">Annotated Errors ({len(annotations)}):</div>'
            for i, ann in enumerate(annotations):
                tag = ann.get("primary_tag", "")
                label = TAG_LABELS.get(tag, tag)
                dot_color = TAG_COLORS.get(tag, {}).get("dot", "#666")
                bg_color = TAG_COLORS.get(tag, {}).get("highlight", "#f0f0f0")
                span_text = ann.get("span_text", "")[:40]
                subtype = ann.get("error_type", "")
                sev = ann.get("severity", "")
                html += (
                    f'<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
                    f'margin-bottom:4px;background:{bg_color};border-radius:6px;border-left:4px solid {dot_color};">'
                    f'<span style="font-weight:600;color:{dot_color};">{i+1}.</span> '
                    f'<span style="font-weight:600;">{label}</span>'
                )
                if subtype:
                    html += f' <span style="color:#6b7280;">({subtype})</span>'
                html += f' — <em>"{span_text}"</em>'
                html += f' <span style="color:#6b7280;margin-left:auto;">[{sev}]</span>'
                html += '</div>'
            html += '</div>'
            return html

        def handle_add_error(
            category, subtype, severity, selection_data, span_data, annotations, current_item
        ):
            """Add a classified error annotation."""
            no_change = annotations, gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

            # Try current_selection state first (from JS span selector)
            data = selection_data
            if not data and span_data:
                # Try parsing as JSON (from JS span selector)
                try:
                    parsed = json.loads(span_data)
                    if "remove" not in parsed and "start" in parsed:
                        data = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

                # Fall back: plain text — find it in the translation
                if not data and span_data.strip() and current_item:
                    text = current_item.get("presented_text", "")
                    search = span_data.strip()
                    idx = text.find(search)
                    if idx >= 0:
                        data = {"start": idx, "end": idx + len(search), "text": search}
                    else:
                        # Text not found in translation — likely an omission or description
                        # Use the typed text as the annotation label
                        data = {"start": 0, "end": 0, "text": search}

            if not data or not category:
                return no_change

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
            summary = _build_errors_summary(annotations)

            return (
                annotations,
                gr.update(value=html),
                gr.update(value=chips),
                gr.update(value=""),  # Clear span output
                gr.update(value="*Select more text or proceed to justification.*"),
                gr.update(value=summary),
            )

        def _submit_response_and_get_feedback(annotations, current_item, current_exercise, student_info, confidence_val=3):
            """Shared submission logic: submit response, return (response_id, feedback_html)."""
            mode = current_exercise.get("mode", "evaluation") if current_exercise else "evaluation"
            item_id = current_item.get("item_id", "")
            confidence_map = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "high"}
            conf_label = confidence_map.get(int(confidence_val), "medium")
            identified = []
            for ann in annotations:
                identified.append({
                    "span_start": ann["span_start"],
                    "span_end": ann["span_end"],
                    "student_mqm_category": _tag_to_mqm(ann.get("primary_tag", "")),
                    "student_severity": ann.get("severity", "major"),
                    "confidence": conf_label,
                })
            time_spent = 0  # not tracked for skip-justify mode
            try:
                resp = api.submit_response(
                    item_id=item_id, mode=mode,
                    identified_errors=identified, time_spent_seconds=time_spent,
                )
                response_id = resp.get("response_id")
            except Exception as e:
                return None, f'<div style="color:red;">Error: {e}</div>'
            feedback_content = ""
            if response_id:
                try:
                    fb = api.get_feedback(response_id)
                    feedback_content = _build_feedback_html(fb)
                    badge_result = fb.get("badges")
                    if badge_result:
                        feedback_content += _build_badge_notification_html(badge_result)
                except Exception as e:
                    feedback_content = f'<div style="color:#6b7280;">Feedback unavailable: {e}</div>'
            return response_id, feedback_content

        def handle_proceed_to_justify(annotations, current_item, current_exercise, student_info):
            """Transition from Phase 1 (Annotate) to Phase 2 (Justify), or skip to Feedback if mode=none."""
            just_type = "per_error_short"
            if current_exercise:
                raw = current_exercise.get("justification_type", "per_error_short")
                legacy = {"free_text": "global_free_text", "structured": "per_error_structured", "both": "global_free_text"}
                just_type = legacy.get(raw, raw)

            item_text = current_item.get("presented_text", "") if current_item else ""

            # "none" mode: skip justification, submit directly, jump to feedback
            n_extra = MAX_PER_ERROR * 3 + MAX_PER_ERROR * 5  # short(3 per slot) + struct(5 per slot)
            if just_type == "none":
                response_id, feedback_content = _submit_response_and_get_feedback(
                    annotations, current_item, current_exercise, student_info,
                )
                base = [
                    gr.update(selected=12),  # jump to Feedback tab
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                    "feedback",
                    gr.update(value=(
                        '<div class="phase-indicator" style="text-align:center;">'
                        "1 Annotate -> 2 Justify -> "
                        '<strong style="color:#3b82f6;">3 Feedback</strong></div>'
                    )),
                    response_id,
                    gr.update(value=feedback_content),
                ]
                return tuple(base + [gr.update()] * n_extra)

            # Normal modes: show justify panel
            base = [
                gr.update(selected=11),  # switch to Justify tab
                gr.update(visible=(just_type == "global_free_text")),
                gr.update(visible=(just_type == "per_error_short")),
                gr.update(visible=(just_type == "per_error_structured")),
                "justify",
                gr.update(
                    value=(
                        '<div class="phase-indicator" style="text-align:center;">'
                        "1 Annotate -> "
                        '<strong style="color:#3b82f6;">2 Justify</strong> -> '
                        "3 Feedback</div>"
                    )
                ),
                gr.update(),  # current_response_id (no change)
                gr.update(),  # feedback_html (no change)
            ]

            # Per-error short slot updates
            short_updates = []
            for i in range(MAX_PER_ERROR):
                if i < len(annotations):
                    ann = annotations[i]
                    prompt = _get_justification_prompt(ann.get("primary_tag", ""))
                    label_html = _build_error_label_html(i, ann, item_text)
                    short_updates.append(gr.update(visible=True))   # group
                    short_updates.append(gr.update(value=label_html))  # label
                    short_updates.append(gr.update(value="", label=prompt))  # textbox
                else:
                    short_updates.append(gr.update(visible=False))
                    short_updates.append(gr.update(value=""))
                    short_updates.append(gr.update(value=""))

            # Per-error structured slot updates
            struct_updates = []
            for i in range(MAX_PER_ERROR):
                if i < len(annotations):
                    ann = annotations[i]
                    label_html = _build_error_label_html(i, ann, item_text)
                    struct_updates.append(gr.update(visible=True))   # group
                    struct_updates.append(gr.update(value=label_html))  # label
                    struct_updates.append(gr.update(value=""))  # mt
                    struct_updates.append(gr.update(value=""))  # author
                    struct_updates.append(gr.update(value=""))  # reader
                else:
                    struct_updates.append(gr.update(visible=False))
                    struct_updates.append(gr.update(value=""))
                    struct_updates.append(gr.update(value=""))
                    struct_updates.append(gr.update(value=""))
                    struct_updates.append(gr.update(value=""))

            return tuple(base + short_updates + struct_updates)

        def handle_submit_justify(*args):
            """Submit annotations + justifications and get feedback.

            Args are positionally unpacked:
              [0] justify_text_val (global free text)
              [1..MAX_PER_ERROR] pe_short_text values
              [MAX_PER_ERROR+1 .. MAX_PER_ERROR+MAX_PER_ERROR*3] pe_struct mt/author/reader values
              then: confidence_val, item_start_time_val, annotations, current_item,
                    current_exercise, student_info
            """
            idx = 0
            justify_text_val = args[idx]; idx += 1
            pe_short_vals = list(args[idx:idx + MAX_PER_ERROR]); idx += MAX_PER_ERROR
            pe_struct_vals = list(args[idx:idx + MAX_PER_ERROR * 3]); idx += MAX_PER_ERROR * 3
            confidence_val = args[idx]; idx += 1
            item_start_time_val = args[idx]; idx += 1
            annotations = args[idx]; idx += 1
            current_item = args[idx]; idx += 1
            current_exercise = args[idx]; idx += 1
            student_info = args[idx]; idx += 1

            if not current_item:
                return gr.update(), gr.update(), None, gr.update(), gr.update()

            mode = current_exercise.get("mode", "evaluation") if current_exercise else "evaluation"
            item_id = current_item.get("item_id", "")

            # Determine justification type
            raw_jt = current_exercise.get("justification_type", "per_error_short") if current_exercise else "per_error_short"
            legacy = {"free_text": "global_free_text", "structured": "per_error_structured", "both": "global_free_text"}
            just_type = legacy.get(raw_jt, raw_jt)

            # Build identified errors from annotations
            confidence_map = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "high"}
            conf_label = confidence_map.get(int(confidence_val), "medium")
            identified = []
            for ann in annotations:
                identified.append({
                    "span_start": ann["span_start"],
                    "span_end": ann["span_end"],
                    "student_mqm_category": _tag_to_mqm(ann.get("primary_tag", "")),
                    "student_severity": ann.get("severity", "major"),
                    "confidence": conf_label,
                })

            # Calculate elapsed time
            time_spent = round(time.time() - item_start_time_val, 1) if item_start_time_val else 0

            # Submit response
            try:
                resp = api.submit_response(
                    item_id=item_id,
                    mode=mode,
                    identified_errors=identified,
                    time_spent_seconds=time_spent,
                )
                response_id = resp.get("response_id")
            except Exception as e:
                return (
                    gr.update(), gr.update(), None,
                    gr.update(value=f'<div style="color:red;">Error: {e}</div>'),
                    gr.update(),
                )

            # Build justifications based on mode
            justifications = []

            if just_type == "global_free_text":
                if justify_text_val:
                    justifications.append({
                        "format": "free_text",
                        "text": justify_text_val,
                    })

            elif just_type == "per_error_short":
                for i, ann in enumerate(annotations):
                    if i >= MAX_PER_ERROR:
                        break
                    text = pe_short_vals[i] if i < len(pe_short_vals) else ""
                    if text and text.strip():
                        prompt = _get_justification_prompt(ann.get("primary_tag", ""))
                        justifications.append({
                            "format": "per_error_short",
                            "error_id": ann.get("annotation_id"),
                            "text": text.strip(),
                            "prompt_shown": prompt,
                        })

            elif just_type == "per_error_structured":
                for i, ann in enumerate(annotations):
                    if i >= MAX_PER_ERROR:
                        break
                    base = i * 3
                    mt_val = pe_struct_vals[base] if base < len(pe_struct_vals) else ""
                    au_val = pe_struct_vals[base + 1] if base + 1 < len(pe_struct_vals) else ""
                    rd_val = pe_struct_vals[base + 2] if base + 2 < len(pe_struct_vals) else ""
                    if (mt_val and mt_val.strip()) or (au_val and au_val.strip()) or (rd_val and rd_val.strip()):
                        justifications.append({
                            "format": "per_error_structured",
                            "error_id": ann.get("annotation_id"),
                            "mt_misunderstanding": (mt_val or "").strip(),
                            "author_intent": (au_val or "").strip(),
                            "reader_impact": (rd_val or "").strip(),
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
                    # Append badge notifications
                    badge_result = fb.get("badges")
                    if badge_result:
                        feedback_content += _build_badge_notification_html(badge_result)
                except Exception as e:
                    feedback_content = f'<div style="color:#6b7280;">Feedback unavailable: {e}</div>'

            return (
                gr.Tabs(selected=12),  # switch phase_tabs to Feedback tab
                "feedback",  # phase
                response_id,
                gr.update(value=feedback_content),
                gr.update(),  # phase_html (hidden)
            )

        def handle_next_item(
            current_item_idx, current_exercise, current_assignment, student_info,
        ):
            """Advance to the next item in the exercise."""
            if not current_exercise:
                return [gr.update()] * (15 + MAX_PER_ERROR + MAX_PER_ERROR * 3)

            item_ids = current_exercise.get("item_ids", [])
            next_idx = current_item_idx + 1

            # Number of per-error text fields to reset
            _n_justify_resets = 1 + MAX_PER_ERROR + MAX_PER_ERROR * 3 + 1
            # = justify_text + short texts + struct mt/author/reader + confidence

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
                base = [
                    next_idx,
                    gr.update(value="<h3>Exercise Complete!</h3><p>Great work. Return to the Exercises tab to see your results.</p>"),
                    gr.update(selected=10),  # phase_tabs → Annotate
                    gr.update(),  # current_item
                    gr.update(value=""),
                    gr.update(value=""),
                    [],  # annotations_state
                    gr.update(value=""),  # chips_html
                    "annotate",  # current_phase
                    gr.update(),  # phase_html
                    None,  # item_start_time
                    gr.update(value=_build_errors_summary([])),  # errors_summary_html
                    gr.update(value=""),  # span_output clear
                ]
                resets = [gr.update(value="")] * (MAX_PER_ERROR + MAX_PER_ERROR * 3 + 1)  # short + struct + justify_text
                resets.append(gr.update(value=3))  # confidence
                return tuple(base + resets)

            # Load next item
            try:
                item = api.get_item(item_ids[next_idx])
            except Exception:
                return [gr.update()] * (15 + MAX_PER_ERROR + MAX_PER_ERROR * 3)

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
                gr.update(selected=10),  # phase_tabs → Annotate
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
                time.time(),  # item_start_time
                gr.update(value=_build_errors_summary([])),  # errors_summary_html
                gr.update(value=""),  # span_output clear
                *([gr.update(value="")] * (1 + MAX_PER_ERROR + MAX_PER_ERROR * 3)),  # justify_text + short + struct
                gr.update(value=3),  # confidence_slider
            )

        def handle_refresh_progress(student_info):
            """Load and render the My Progress tab content."""
            if not student_info or "student_id" not in student_info:
                return gr.update(value="<p>Log in to see your progress.</p>")

            try:
                progress_data = api.get_progress(student_info["student_id"])
            except Exception:
                return gr.update(value="<p>Could not load progress data.</p>")

            level = student_info.get("current_level", "navigator")
            # Handle AnnotationLevel enum values
            if hasattr(level, 'value'):
                level = level.value

            html = '<div style="font-family:system-ui;padding:16px;">'
            html += '<h3>Your Performance</h3>'

            # Summary metrics
            completed = progress_data.get("total_sessions", 0)
            avg_score = progress_data.get("avg_detection_rate", 0)
            badge_data = progress_data.get("badges", {})
            total_xp = badge_data.get("total_xp", 0) if badge_data else 0

            html += '<div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">'
            html += f'<div style="text-align:center;padding:16px;background:#f0f9ff;border-radius:8px;flex:1;min-width:100px;"><div style="font-size:24px;font-weight:bold;color:#3b82f6;">{completed}</div><div style="color:#6b7280;">Exercises</div></div>'
            html += f'<div style="text-align:center;padding:16px;background:#f0fdf4;border-radius:8px;flex:1;min-width:100px;"><div style="font-size:24px;font-weight:bold;color:#10b981;">{avg_score:.0f}%</div><div style="color:#6b7280;">Avg Score</div></div>'
            html += f'<div style="text-align:center;padding:16px;background:#fef3c7;border-radius:8px;flex:1;min-width:100px;"><div style="font-size:24px;font-weight:bold;color:#f59e0b;">{level.title()}</div><div style="color:#6b7280;">Level</div></div>'
            html += f'<div style="text-align:center;padding:16px;background:linear-gradient(135deg,#1B2838,#2d3748);border-radius:8px;flex:1;min-width:100px;"><div style="font-size:24px;font-weight:bold;color:#D4AF37;">{total_xp:,}</div><div style="color:#9ca3af;">XP</div></div>'
            html += '</div>'

            # Badge Collection
            if badge_data:
                html += _build_badge_collection_html(badge_data)

            # Skill Radar
            skill_data = progress_data.get("skill_profile", {})
            if skill_data:
                html += _build_skill_radar_html(skill_data, level)
            else:
                # Show radar with zeros if no skill data yet
                empty_skills = {f"S{i}": 0.0 for i in range(1, 8)}
                html += _build_skill_radar_html(empty_skills, level)

            # Recent scores
            recent = progress_data.get("recent_scores", [])
            if recent:
                html += '<h4 style="margin-top:24px;">Recent Exercises</h4>'
                for entry in recent[-5:]:
                    score_pct = int(entry.get("f1", 0) * 100)
                    html += f'<div style="padding:8px;border-bottom:1px solid #e5e7eb;">'
                    html += f'<strong>{entry.get("exercise_name", "Exercise")}</strong> — {score_pct}% F1'
                    html += f' | Time: {entry.get("time_spent", 0):.0f}s</div>'

            html += '</div>'
            return gr.update(value=html)

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
                phase_tabs, pe_panel, pe_textbox, current_phase,
                item_start_time, errors_summary_html,
            ],
        )

        # Span selection handler
        span_output.change(
            handle_span_selection,
            inputs=[span_output, annotations_state, current_item],
            outputs=[annotations_state, translation_html, chips_html, selection_label, current_selection],
        )

        # Category pill buttons — use fn with default arg to avoid closure issue
        def _make_category_handler(tag_value):
            def _handler():
                subtypes = SUBTYPES.get(tag_value, [])
                return (
                    tag_value,
                    gr.update(visible=bool(subtypes), choices=subtypes, value=subtypes[0] if subtypes else None),
                    gr.update(visible=bool(subtypes)),
                )
            return _handler

        for tag, btn in cat_buttons.items():
            btn.click(
                _make_category_handler(tag),
                outputs=[selected_category, subtype_dropdown, subtype_label],
                queue=False,
            )

        add_error_btn.click(
            handle_add_error,
            inputs=[
                selected_category, subtype_dropdown, severity_radio,
                current_selection, span_output, annotations_state, current_item,
            ],
            outputs=[
                annotations_state, translation_html, chips_html,
                span_output, selection_label, errors_summary_html,
            ],
        )

        cancel_btn.click(
            lambda: (gr.update(value=""), gr.update(value="*Select text to annotate.*")),
            outputs=[span_output, selection_label],
            queue=False,
        )

        # Build outputs list for proceed_justify: base + response_id + feedback + per-error slots
        _proceed_outputs = [
            phase_tabs,
            justify_freetext, justify_per_error_short, justify_per_error_struct,
            current_phase, phase_html,
            current_response_id, feedback_html,
        ]
        for i in range(MAX_PER_ERROR):
            _proceed_outputs.extend([pe_short_groups[i], pe_short_labels[i], pe_short_texts[i]])
        for i in range(MAX_PER_ERROR):
            _proceed_outputs.extend([
                pe_struct_groups[i], pe_struct_labels[i],
                pe_struct_mt[i], pe_struct_author[i], pe_struct_reader[i],
            ])

        proceed_justify_btn.click(
            handle_proceed_to_justify,
            inputs=[annotations_state, current_item, current_exercise, student_info],
            outputs=_proceed_outputs,
        )

        # Build inputs list for submit_justify: global text + per-error short texts + per-error struct fields + rest
        _submit_inputs = [justify_text]
        _submit_inputs.extend(pe_short_texts)
        for i in range(MAX_PER_ERROR):
            _submit_inputs.extend([pe_struct_mt[i], pe_struct_author[i], pe_struct_reader[i]])
        _submit_inputs.extend([
            confidence_slider, item_start_time,
            annotations_state, current_item, current_exercise, student_info,
        ])

        submit_justify_btn.click(
            handle_submit_justify,
            inputs=_submit_inputs,
            outputs=[
                phase_tabs,
                current_phase, current_response_id,
                feedback_html, phase_html,
            ],
        )

        _next_item_outputs = [
            current_item_idx, translation_html,
            phase_tabs, current_item,
            source_html, progress_html,
            annotations_state, chips_html,
            current_phase, phase_html,
            item_start_time, errors_summary_html,
            span_output,
            justify_text,
        ]
        _next_item_outputs.extend(pe_short_texts)
        for i in range(MAX_PER_ERROR):
            _next_item_outputs.extend([pe_struct_mt[i], pe_struct_author[i], pe_struct_reader[i]])
        _next_item_outputs.append(confidence_slider)

        next_item_btn.click(
            handle_next_item,
            inputs=[current_item_idx, current_exercise, current_assignment, student_info],
            outputs=_next_item_outputs,
        )

        refresh_progress_btn.click(
            handle_refresh_progress,
            inputs=[student_info],
            outputs=[progress_content],
        )

        # Auto-load progress when My Progress tab is selected
        def _on_tab_select(student_info_val, evt: gr.SelectData):
            if evt.index == 2:  # My Progress tab
                return handle_refresh_progress(student_info_val)
            return gr.update()

        main_tabs.select(
            _on_tab_select,
            inputs=[student_info],
            outputs=[progress_content],
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
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="ToM-PE Student App")
    parser.add_argument("--share", action="store_true", help="Create a public Gradio share link")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    assets_dir = str(project_root / "assets")

    app = build_student_app()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=args.share,
        allowed_paths=[assets_dir],
        theme=gr.themes.Soft(),
        css="""
        .pill-btn { border-radius: 16px !important; font-size: 14px !important; }
        .phase-indicator { font-size: 14px; color: #6b7280; padding: 8px 0; }
        @keyframes badgeFadeIn { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        """,
    )


if __name__ == "__main__":
    main()
