"""Custom span selector component for Gradio.

Uses gr.HTML + inline JavaScript for click-drag text selection in the translation
text. Communicates selection events back to Python via a hidden gr.Textbox.

The component renders highlighted text with existing annotations and allows
students to select new spans by clicking and dragging.
"""

import json
from typing import Any

from tompe.interfaces.components.colors import TAG_COLORS, TAG_LABELS

# ── HTML/JS for the span selector widget ─────────────────────────────────────

SPAN_SELECTOR_CSS = """
<style>
.span-selector-container {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 16px;
    line-height: 1.8;
    padding: 16px 20px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    background: #fafafa;
    cursor: text;
    user-select: text;
    -webkit-user-select: text;
    position: relative;
    min-height: 60px;
}
.span-selector-container:hover {
    border-color: #93c5fd;
}
.span-selector-container .error-highlight {
    padding: 2px 0;
    border-radius: 3px;
    position: relative;
    cursor: pointer;
}
.span-selector-container .error-highlight .remove-btn {
    display: none;
    position: absolute;
    top: -8px;
    right: -8px;
    width: 18px;
    height: 18px;
    background: #ef4444;
    color: white;
    border: none;
    border-radius: 50%;
    font-size: 11px;
    cursor: pointer;
    line-height: 18px;
    text-align: center;
    z-index: 10;
}
.span-selector-container .error-highlight:hover .remove-btn {
    display: block;
}
.span-selector-container .temp-selection {
    background: #bfdbfe;
    padding: 2px 0;
    border-radius: 3px;
}
.annotation-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 13px;
    margin: 2px 4px;
    border: 1px solid #d1d5db;
    background: white;
}
.annotation-chip .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.annotation-chip .remove-chip {
    cursor: pointer;
    color: #9ca3af;
    font-weight: bold;
    margin-left: 4px;
}
.annotation-chip .remove-chip:hover {
    color: #ef4444;
}
.l0-annotation-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    vertical-align: super;
}
</style>
"""

SPAN_SELECTOR_JS = """
<script>
(function() {
    const container = document.getElementById('span-text-{widget_id}');
    if (!container) return;

    container.addEventListener('mouseup', function(e) {
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed) return;

        const range = selection.getRangeAt(0);

        // Compute character offsets relative to the text content
        const treeWalker = document.createTreeWalker(
            container, NodeFilter.SHOW_TEXT, null, false
        );
        let charOffset = 0;
        let startOffset = -1;
        let endOffset = -1;
        let node;

        while (node = treeWalker.nextNode()) {
            if (node === range.startContainer) {
                startOffset = charOffset + range.startOffset;
            }
            if (node === range.endContainer) {
                endOffset = charOffset + range.endOffset;
            }
            charOffset += node.textContent.length;
        }

        if (startOffset >= 0 && endOffset > startOffset) {
            const selectedText = selection.toString().trim();
            if (selectedText.length > 0) {
                // Find the textarea in span-output-{widget_id} — try multiple selectors
                let textarea = null;
                const output = document.getElementById('span-output-{widget_id}');
                if (output) {
                    textarea = output.querySelector('textarea') || output.querySelector('input');
                }
                // Fallback: search by label text
                if (!textarea) {
                    document.querySelectorAll('textarea').forEach(function(ta) {
                        if (ta.closest('[data-testid]') && ta.value !== undefined) {
                            const label = ta.closest('.gradio-textbox, .gradio-group');
                            if (label && label.textContent.includes('Selected text')) {
                                textarea = ta;
                            }
                        }
                    });
                }
                if (textarea) {
                    // Set value using native setter to trigger React/Gradio state
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(textarea, selectedText);
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    // Also try the input element setter
                    try {
                        const inputSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        inputSetter.call(textarea, selectedText);
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    } catch(e) {}
                }
            }
        }
        selection.removeAllRanges();
    });
})();
</script>
"""


def render_text_with_highlights(
    text: str,
    annotations: list[dict[str, Any]],
    widget_id: str = "main",
    level: str = "analyst",
) -> str:
    """Render translation text with colored error highlights.

    Args:
        text: The translation text to render.
        annotations: List of annotation dicts with keys:
            - span_start, span_end: character offsets
            - primary_tag: PrimaryTag value
            - annotation_id: unique ID for removal
            - (optional) mqm_label, severity_label, tom_hint: for L0
            - (optional) is_region_hint: True for L1 yellow regions
        widget_id: Unique ID for the widget instance.
        level: Scaffolding level ("navigator", "scout", "analyst", "expert").

    Returns:
        Complete HTML string with CSS, text, and JS.
    """
    # Sort annotations by span_start (handle overlaps by taking first)
    sorted_anns = sorted(annotations, key=lambda a: a.get("span_start", 0))

    # Build HTML with highlights
    html_parts = []
    last_end = 0

    for ann in sorted_anns:
        start = ann.get("span_start", 0)
        end = ann.get("span_end", 0)
        tag = ann.get("primary_tag", "")
        ann_id = ann.get("annotation_id", "")
        is_hint = ann.get("is_region_hint", False)

        if start < last_end:
            continue  # Skip overlapping

        # Text before this annotation
        if start > last_end:
            html_parts.append(_escape_html(text[last_end:start]))

        # Determine colors
        if is_hint:
            bg = "#FEF9C3"  # Yellow for region hints
        elif tag in TAG_COLORS:
            bg = TAG_COLORS[tag]["highlight"]
        else:
            bg = "#E5E7EB"

        # The highlighted span
        span_text = _escape_html(text[start:end])
        badge = ""

        if level == "navigator" and not is_hint:
            # L0: show full badges
            label = ann.get("mqm_label", TAG_LABELS.get(tag, ""))
            sev = ann.get("severity_label", "")
            dot_color = TAG_COLORS.get(tag, {}).get("dot", "#666")
            badge = (
                f' <span class="l0-annotation-badge" style="background:{bg};color:{dot_color}">'
                f'{label} &middot; {sev}</span>'
            )

        remove_btn = ""
        if level in ("analyst", "expert", "scout"):
            remove_btn = (
                f'<button class="remove-btn" '
                f'onclick="removeAnnotation_{widget_id}(\'{ann_id}\')">&times;</button>'
            )

        html_parts.append(
            f'<span class="error-highlight" style="background:{bg};cursor:pointer;" '
            f'data-ann-id="{ann_id}" '
            f'title="Double-click to select this text for annotation" '
            f'ondblclick="fillSelectedText_{widget_id}(this.textContent.replace(/×$/, \'\').trim())">'
            f'{span_text}{remove_btn}</span>{badge}'
        )
        last_end = end

    # Remaining text
    if last_end < len(text):
        html_parts.append(_escape_html(text[last_end:]))

    text_html = "".join(html_parts)

    # Remove annotation JS function
    remove_js = f"""
    <script>
    function removeAnnotation_{widget_id}(annId) {{
        const output = document.getElementById('span-output-{widget_id}');
        if (output) {{
            const textarea = output.querySelector('textarea');
            if (textarea) {{
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value'
                ).set;
                nativeInputValueSetter.call(textarea, JSON.stringify({{remove: annId}}));
                textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}
    }}
    </script>
    """

    return (
        SPAN_SELECTOR_CSS
        + f'<div id="span-text-{widget_id}" class="span-selector-container">'
        + text_html
        + "</div>"
        + remove_js
        + SPAN_SELECTOR_JS.replace("{widget_id}", widget_id)
    )


def render_annotation_chips(annotations: list[dict[str, Any]]) -> str:
    """Render a list of annotation chips below the text.

    Each chip shows: colored dot + category label + span text excerpt + remove button.
    """
    if not annotations:
        return '<div style="color:#9ca3af;font-size:14px;padding:8px 0;">No errors marked yet. Select text above to annotate.</div>'

    chips = []
    for ann in annotations:
        tag = ann.get("primary_tag", "")
        label = TAG_LABELS.get(tag, tag)
        dot_color = TAG_COLORS.get(tag, {}).get("dot", "#666")
        span_text = ann.get("span_text", "")[:30]
        sev = ann.get("severity", "")
        ann_id = ann.get("annotation_id", "")

        chips.append(
            f'<span class="annotation-chip">'
            f'<span class="dot" style="background:{dot_color}"></span>'
            f'{label} &middot; <em>{_escape_html(span_text)}</em> &middot; {sev}'
            f'<span class="remove-chip" onclick="removeAnnotation_main(\'{ann_id}\')">&times;</span>'
            f'</span>'
        )

    return '<div style="padding:8px 0;display:flex;flex-wrap:wrap;gap:4px;">' + "".join(chips) + '</div>'


def render_classification_panel(selected_text: str = "") -> str:
    """Render the MQM classification pill buttons as HTML.

    This is displayed when a span is selected. The actual interaction is handled
    by Gradio buttons in the student app, not by this HTML.
    """
    if not selected_text:
        return ""

    return (
        f'<div style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;">'
        f'<div style="font-weight:600;margin-bottom:8px;">Classify: "{_escape_html(selected_text[:50])}"</div>'
        f'</div>'
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
