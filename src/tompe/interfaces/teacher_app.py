"""Streamlit teacher interface for ToM-PE.

Provides: corpus browser, MT generation trigger, review queue, exercise builder,
class management, analytics dashboard, and settings. Calls services directly
(same machine, no HTTP overhead for v1).
"""

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit as st
import yaml

# Load .env file into environment
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

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
    nav_pages = [
        "📂 Browse Corpus",
        "📤 Upload Corpus",
        "🔄 Generate & Inject Errors",
        "📋 Review Queue",
        "📋 Published Items",
        "📚 Exercise Builder",
        "👥 Class Management",
        "📊 Analytics Dashboard",
        "🔬 Study Management",
        "⚙️ Settings",
    ]
    nav_override = st.session_state.pop("nav_page", None)
    if nav_override and nav_override in nav_pages:
        st.session_state["nav_radio"] = nav_override
    page = st.sidebar.radio(
        "Go to",
        nav_pages,
        key="nav_radio",
        label_visibility="collapsed",
    )

    # Ensure a default class exists
    _ensure_default_class()

    # ── Page routing ─────────────────────────────────────────────────────
    if page == "📂 Browse Corpus":
        _page_browse_corpus()
    elif page == "📤 Upload Corpus":
        _page_upload_corpus()
    elif page == "🔄 Generate & Inject Errors":
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
    elif page == "🔬 Study Management":
        _page_study_management()
    elif page == "⚙️ Settings":
        _page_settings()


def _ensure_default_class():
    """Create a default class if none exists."""
    classes = list_classes()
    if not classes:
        create_class(
            "Default Class",
            default_levels=[AnnotationLevel.NAVIGATOR, AnnotationLevel.SCOUT, AnnotationLevel.ANALYST],
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

                corpus_dir = DATA_DIR / "corpora"
                all_segments: list[dict] = []
                for origin in (sources or ["europarl"]):
                    all_segments.extend(load_corpus(corpus_dir, origin))

                segments = filter_segments(all_segments, min_tokens=min_tok, max_tokens=max_tok)

                if domain != "All":
                    segments = [s for s in segments if s.get("domain") == domain]
                if direction == "FR→EN":
                    segments = [s for s in segments if s.get("source_lang") == "fr"]
                elif direction == "EN→FR":
                    segments = [s for s in segments if s.get("source_lang") == "en"]
                if register != "All":
                    segments = [s for s in segments if s.get("register") == register]
                if search:
                    q = search.lower()
                    segments = [
                        s for s in segments
                        if q in s.get("source_text", "").lower()
                        or q in s.get("reference_translation", "").lower()
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
            n_tokens = len(s.get("source_text", "").split())
            src_lang = s.get("source_lang", "?").upper()
            tgt_lang = s.get("target_lang", "?").upper()
            data.append({
                "Select": False,
                "Source": s.get("source_text", "")[:80],
                "Reference": s.get("reference_translation", "")[:80],
                "Direction": f"{src_lang}→{tgt_lang}",
                "Domain": s.get("domain", ""),
                "Tokens": n_tokens,
                "Corpus": s.get("corpus_origin", ""),
                "ID": s.get("segment_id", ""),
            })

        edited = st.data_editor(
            data,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "Source": st.column_config.TextColumn("Source", width="large"),
                "Reference": st.column_config.TextColumn("Reference", width="large"),
                "Direction": st.column_config.TextColumn("Direction"),
            },
            hide_index=True,
            width="stretch",
        )

        selected_ids = [row["ID"] for row in edited if row.get("Select")]
        if selected_ids:
            st.session_state["selected_segment_ids"] = selected_ids
            st.success(f"Selected: {len(selected_ids)} segments")
            if st.button("Next Step: Generate & Inject Errors →", type="primary"):
                st.session_state["nav_page"] = "🔄 Generate & Inject Errors"
                st.rerun()


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
    st.header("🔄 Generate Translations & Inject Errors")
    st.caption(
        "This pipeline: (1) translates selected segments with MT systems, "
        "(2) injects controlled MQM errors into translations, and "
        "(3) generates pedagogical explanations for each error."
    )

    selected_ids = st.session_state.get("selected_segment_ids", [])
    if not selected_ids:
        st.info("No segments selected. Go to Browse Corpus and select segments first.")
        return

    st.write(f"**Selected segments:** {len(selected_ids)}")

    # MT system selection
    mt_config = _load_mt_config()
    mt_systems = mt_config.get("mt_systems", {})

    st.subheader("MT Systems")
    env_keys = {
        "google": "GOOGLE_TRANSLATE_API_KEY",
        "deepl": "DEEPL_AUTH_KEY",
        "gpt4": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "ollama": "OLLAMA_BASE_URL",
        "together": "TOGETHER_API_KEY",
    }
    selected_systems = []
    cols = st.columns(3)
    for i, (name, config) in enumerate(mt_systems.items()):
        with cols[i % 3]:
            enabled = config.get("enabled", False)
            has_key = bool(os.environ.get(env_keys.get(name, ""), ""))
            if enabled and has_key:
                status = "✓"
            elif enabled and not has_key:
                status = "⚠️ No API key"
            else:
                status = "disabled"
            label = f"{name} ({status})"
            if st.checkbox(label, value=enabled, key=f"mt_{name}"):
                selected_systems.append(name)

    st.subheader("LLM Translation Prompt")
    st.caption(
        "These prompts apply to LLM-based translators (GPT-4, Claude, etc.). "
        "DeepL and Google use their own APIs and ignore this prompt. "
        "The source/target languages are detected automatically from each segment."
    )
    prompt_presets = {
        "EU Formal": "You are a professional EU translator. Translate the following text, maintaining formal register and EU terminology conventions.",
        "General": "Translate the following text accurately and naturally.",
        "Legal": "You are a legal translator specializing in EU law. Translate with precise legal terminology.",
    }
    preset = st.selectbox("Load preset", list(prompt_presets.keys()))
    prompt = st.text_area("Translation prompt", value=prompt_presets.get(preset, ""), height=100)

    st.subheader("Error Injection Settings")
    st.caption(
        "Configure which error types to inject into the reference translations. "
        "The system uses an LLM to introduce realistic, controlled errors."
    )
    col_err1, col_err2 = st.columns(2)
    with col_err1:
        inject_mistranslation = st.checkbox("Mistranslation", value=True, key="inj_mistrans")
        inject_grammar = st.checkbox("Grammar", value=True, key="inj_grammar")
        inject_omission = st.checkbox("Omission", value=True, key="inj_omission")
        inject_addition = st.checkbox("Addition", value=False, key="inj_addition")
        inject_terminology = st.checkbox("Terminology", value=False, key="inj_terminology")
    with col_err2:
        inject_style = st.checkbox("Style", value=False, key="inj_style")
        inject_spelling = st.checkbox("Spelling", value=False, key="inj_spelling")
        inject_punctuation = st.checkbox("Punctuation", value=False, key="inj_punctuation")
        inject_untranslated = st.checkbox("Untranslated", value=False, key="inj_untranslated")

    severity_dist = st.columns(3)
    with severity_dist[0]:
        n_minor = st.number_input("Minor errors", value=1, min_value=0, max_value=5, key="sev_minor")
    with severity_dist[1]:
        n_major = st.number_input("Major errors", value=1, min_value=0, max_value=5, key="sev_major")
    with severity_dist[2]:
        n_critical = st.number_input("Critical errors", value=0, min_value=0, max_value=3, key="sev_critical")

    if st.button("Generate Translations & Inject Errors", type="primary"):
        if not selected_systems:
            st.warning("Please select at least one MT system.")
        else:
            from tompe.schemas.enums import PrimaryTag, Severity
            error_tags = []
            if inject_mistranslation: error_tags.append(PrimaryTag.MISTRANSLATION)
            if inject_grammar: error_tags.append(PrimaryTag.GRAMMAR)
            if inject_omission: error_tags.append(PrimaryTag.OMISSION)
            if inject_addition: error_tags.append(PrimaryTag.ADDITION)
            if inject_terminology: error_tags.append(PrimaryTag.TERMINOLOGY)
            if inject_style: error_tags.append(PrimaryTag.STYLE)
            if inject_spelling: error_tags.append(PrimaryTag.SPELLING)
            if inject_punctuation: error_tags.append(PrimaryTag.PUNCTUATION)
            if inject_untranslated: error_tags.append(PrimaryTag.UNTRANSLATED)
            if not error_tags:
                st.warning("Select at least one error type to inject.")
            else:
                sev_dist = {}
                if n_minor > 0: sev_dist[Severity.MINOR] = n_minor
                if n_major > 0: sev_dist[Severity.MAJOR] = n_major
                if n_critical > 0: sev_dist[Severity.CRITICAL] = n_critical
                if not sev_dist:
                    st.warning("Set at least one severity count > 0.")
                else:
                    _run_translation_pipeline(
                        selected_ids, selected_systems, mt_config, prompt,
                        error_tags, sev_dist,
                    )


def _run_translation_pipeline(selected_ids, selected_systems, mt_config, prompt,
                              error_tags=None, severity_dist=None):
    """Run MT generation + error injection for selected segments."""
    import asyncio
    from tompe.pipeline.segment_selector import load_corpus, compute_complexity
    from tompe.pipeline.mt_generator import translate_segment
    from tompe.pipeline.error_injector import inject_errors_reference_based, ErrorProfile
    from tompe.pipeline.explanation_generator import generate_all_explanations

    # Use a single event loop to avoid "Event loop is closed" errors
    loop = asyncio.new_event_loop()

    def run_async(coro):
        return loop.run_until_complete(coro)
    from tompe.schemas.corpus import CorpusSegment
    from tompe.schemas.item import AssessmentItem, ItemMetadata
    from tompe.schemas.enums import (
        AnnotationLevel, ItemPathway, MQMCategory, PrimaryTag, Severity, TOMLevel,
    )
    from tompe.schemas.annotation import AnnotationConfig

    # 1. Load all corpus segments and find the selected ones
    corpus_dir = DATA_DIR / "corpora"
    all_segments: list[dict] = []
    for origin in ["europarl", "dgt_tm", "eurlex", "unpc"]:
        if (corpus_dir / origin / "segments_en_fr.jsonl").exists():
            all_segments.extend(load_corpus(corpus_dir, origin))

    selected_raw = [s for s in all_segments if s.get("segment_id") in selected_ids]

    if not selected_raw:
        st.error("Could not find selected segments in corpus.")
        return

    st.divider()
    status_container = st.container()
    with status_container:
        st.subheader("Pipeline Progress")
        status_text = st.empty()
        progress = st.progress(0)
        log_expander = st.expander("Detailed log", expanded=True)
        # Make log scrollable with fixed height
        st.markdown(
            '<style>div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] '
            '{ max-height: 300px; overflow-y: auto; }</style>',
            unsafe_allow_html=True,
        )
    status_text.info(f"Starting pipeline: {len(selected_raw)} segments × {len(selected_systems)} MT systems = {len(selected_raw) * len(selected_systems)} items to generate...")
    results = []
    errors_list = []
    total = len(selected_raw) * len(selected_systems)
    done = 0

    for raw in selected_raw:
        # Build CorpusSegment
        complexity = compute_complexity(raw["source_text"])
        segment = CorpusSegment(
            segment_id=raw["segment_id"],
            source_text=raw["source_text"],
            reference_translation=raw["reference_translation"],
            source_lang=raw["source_lang"],
            target_lang=raw["target_lang"],
            corpus_origin=raw["corpus_origin"],
            domain=raw.get("domain", "general"),
            complexity_score=complexity,
            terminology_density=0.0,
            register=raw.get("register", "formal"),
        )

        for system_name in selected_systems:
            system_config = mt_config.get("mt_systems", {}).get(system_name, {})
            done += 1
            pct = done / total
            progress.progress(pct)
            status_text.info(
                f"**[{done}/{total}]** Translating with **{system_name}** — "
                f"segment `{segment.segment_id[:12]}...` "
                f"({done * 100 // total}% complete)"
            )

            try:
                # Translate
                with log_expander:
                    st.write(f"Step 1/3: Translating with {system_name}...")
                mt_output = run_async(translate_segment(segment, system_name, system_config))

                # Inject errors into reference (controlled pathway)
                injection_config = mt_config.get("injection_llm", {})
                error_profile = ErrorProfile(
                    primary_tags=error_tags or [PrimaryTag.MISTRANSLATION, PrimaryTag.GRAMMAR, PrimaryTag.OMISSION],
                    severity_distribution=severity_dist or {Severity.MINOR: 1, Severity.MAJOR: 1},
                    direction=f"{segment.source_lang}2{segment.target_lang}",
                )
                with log_expander:
                    st.write(f"Step 2/3: Injecting errors...")
                presented_text, injected_errors = run_async(
                    inject_errors_reference_based(segment, error_profile, injection_config)
                )
                with log_expander:
                    st.write(f"  Injected {len(injected_errors)} errors")

                # Generate explanations (Layer 1 + 2a)
                explanations_l1 = []
                explanations_l2 = []
                try:
                    with log_expander:
                        st.write(f"Step 3/3: Generating explanations...")
                    explanation_tuples = run_async(
                        generate_all_explanations(
                            source_text=segment.source_text,
                            reference=segment.reference_translation,
                            errors=injected_errors,
                            mt_system=system_name,
                            llm_config=injection_config,
                        )
                    )
                    for l1, l2a, _l2b in explanation_tuples:
                        explanations_l1.append(l1)
                        explanations_l2.append(l2a)
                        # Attach explanation to error object
                    for i_err, err in enumerate(injected_errors):
                        if i_err < len(explanation_tuples):
                            err.explanation = explanation_tuples[i_err][0]
                            err.system_behavior = explanation_tuples[i_err][1]
                except Exception as expl_err:
                    st.warning(f"Explanation generation failed: {expl_err}")

                # Build AssessmentItem
                from uuid import uuid4
                item_id = str(uuid4())
                item = AssessmentItem(
                    item_id=item_id,
                    segment_id=segment.segment_id,
                    source_text=segment.source_text,
                    source_lang=segment.source_lang,
                    target_lang=segment.target_lang,
                    presented_text=presented_text,
                    reference_translation=segment.reference_translation,
                    mt_system=system_name,
                    pathway=ItemPathway.CONTROLLED,
                    errors=injected_errors,
                    clean_spans=[],
                    annotations=[],
                    annotation_config=AnnotationConfig(level=AnnotationLevel.ANALYST),
                    difficulty_level=min(5, max(1, len(injected_errors) + 1)),
                    domain=segment.domain,
                    item_status="draft",
                    explanations_layer1=explanations_l1,
                    explanations_layer2=explanations_l2,
                    metadata=ItemMetadata(
                        tom_profile={},
                        mqm_profile={},
                        estimated_time_minutes=3.0,
                        has_clean_segments=False,
                        scaffolding_level=AnnotationLevel.ANALYST,
                        pathway=ItemPathway.CONTROLLED,
                        translation_direction=f"{segment.source_lang}→{segment.target_lang}",
                    ),
                )
                items_store.save(item)
                results.append(item_id)
                with log_expander:
                    st.write(f"  ✅ Item `{item_id[:8]}` saved ({len(injected_errors)} errors)")

            except Exception as e:
                errors_list.append(f"{segment.segment_id[:8]} / {system_name}: {e}")
                with log_expander:
                    st.write(f"  ❌ Failed: {e}")
                continue

    progress.progress(1.0)
    loop.close()

    if results:
        status_text.empty()
        st.balloons()
        st.success(
            f"**Pipeline complete!** Generated **{len(results)}** draft items"
            + (f" ({len(errors_list)} failures)" if errors_list else "")
            + ". Review and publish them before building exercises."
        )
        st.button(
            "Next Step: Review Queue →",
            type="primary",
            on_click=lambda: st.session_state.update(nav_page="📋 Review Queue"),
            key="next_review",
        )
    else:
        status_text.empty()
        st.error("No items were generated. Check the detailed log above for errors.")


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
            if st.button(label, key=f"item_{item.item_id}", width="stretch"):
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
    iid = item.item_id  # Use full ID for unique keys
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
        st.text_area("Source", value=item.source_text, height=100, disabled=True, key=f"review_src_{iid}")
    with col2:
        st.markdown("**Translation (with errors)**")
        st.text_area("Translation", value=item.presented_text, height=100, disabled=True, key=f"review_tgt_{iid}")

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
                    key=f"err_cat_{iid}_{i}",
                )
            with col2:
                st.text_input("Error type", value=err.error_type, key=f"err_type_{iid}_{i}")
            with col3:
                st.selectbox(
                    "Severity", [s.value for s in Severity],
                    index=[s.value for s in Severity].index(err.severity)
                    if err.severity in [s.value for s in Severity] else 0,
                    key=f"err_sev_{iid}_{i}",
                )

            if hasattr(err, "injected_text"):
                st.text_input("Error text", value=err.injected_text, key=f"err_text_{iid}_{i}")
            st.text_input("Correct text", value=err.original_text, key=f"err_orig_{iid}_{i}")

            # Explanation layers
            if hasattr(err, "explanation") and err.explanation:
                st.markdown("**Layer 1 — Contrastive**")
                st.text_area(
                    "MT interpretation", value=err.explanation.mt_interpretation,
                    key=f"l1_mt_{iid}_{i}", height=60,
                )
                st.text_area(
                    "Actual meaning", value=err.explanation.actual_meaning,
                    key=f"l1_actual_{iid}_{i}", height=60,
                )

            if hasattr(err, "system_behavior") and err.system_behavior:
                st.markdown("**Layer 2a — Conceptual**")
                st.text_area(
                    "Error mechanism", value=err.system_behavior.error_mechanism,
                    key=f"l2a_{iid}_{i}", height=60,
                )

    # Teacher notes
    st.subheader("Teacher Notes")
    notes = st.text_area("Internal notes", value=item.teacher_notes or "", key=f"teacher_notes_{iid}")

    # Action buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🟢 Approve & Publish", type="primary", width="stretch"):
            items_store.update(item.item_id, AssessmentItem, {
                "item_status": "published",
                "teacher_notes": notes,
            })
            st.success("Item published!")
            st.rerun()
    with col2:
        if st.button("🟠 Save as Reviewed", width="stretch"):
            items_store.update(item.item_id, AssessmentItem, {
                "item_status": "reviewed",
                "teacher_notes": notes,
            })
            st.success("Item saved as reviewed.")
            st.rerun()
    with col3:
        if st.button("🔴 Reject", width="stretch"):
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
    st.dataframe(data, width="stretch")


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
            ["navigator", "scout", "analyst", "expert"],
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
            default=[AnnotationLevel.NAVIGATOR, AnnotationLevel.SCOUT],
        )
        if st.form_submit_button("Create Class"):
            if name:
                create_class(name, [AnnotationLevel(l) for l in levels])
                st.success(f"Class '{name}' created!")
                st.rerun()


# ── Analytics Dashboard ──────────────────────────────────────────────────────


def _page_analytics():
    st.header("📊 Analytics Dashboard")

    tab_class, tab_student, tab_blindspot, tab_export = st.tabs(
        ["Class Overview", "Individual Students", "ToM Blind Spot Analysis", "Data Export"]
    )

    with tab_class:
        _analytics_class_overview()

    with tab_student:
        _analytics_individual_student()

    with tab_blindspot:
        _analytics_blindspot()

    with tab_export:
        _analytics_data_export()


def _analytics_class_overview():
    """Class-level analytics with detection rates and skill profiles."""
    from tompe.schemas.scoring import ScoringResult
    from tompe.services.datastore import responses_store, feedback_store
    from tompe.schemas.response import StudentResponse

    classes = list_classes()
    if not classes:
        st.info("No classes yet.")
        return

    class_options = {c.class_name: c.class_id for c in classes}
    sel_class = st.selectbox("Class", list(class_options.keys()), key="analytics_class")
    class_id = class_options[sel_class]
    students = list_students(class_id)

    if not students:
        st.info("No students in this class.")
        return

    # Gather all scores
    all_scores = feedback_store.list_all(ScoringResult)
    student_ids = {s.student_id for s in students}

    # Match scores to students via responses
    all_responses = responses_store.list_all(StudentResponse)
    student_responses = [r for r in all_responses if r.student_id in student_ids]
    response_ids = {r.response_id for r in student_responses}
    class_scores = [s for s in all_scores if s.response_id in response_ids]

    if not class_scores:
        st.info("No completed exercises yet. Scores will appear here once students submit responses.")
        return

    # Detection rate summary
    avg_precision = sum(s.precision for s in class_scores) / len(class_scores)
    avg_recall = sum(s.recall for s in class_scores) / len(class_scores)
    avg_f1 = sum(s.f1 for s in class_scores) / len(class_scores)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Responses", len(class_scores))
    col2.metric("Avg Precision", f"{avg_precision:.1%}")
    col3.metric("Avg Recall", f"{avg_recall:.1%}")
    col4.metric("Avg F1", f"{avg_f1:.1%}")

    # Per-student summary table
    st.subheader("Per-Student Performance")
    student_map = {s.student_id: s.display_name for s in students}
    response_student_map = {r.response_id: r.student_id for r in student_responses}

    per_student: dict[str, list] = {}
    for score in class_scores:
        sid = response_student_map.get(score.response_id, "")
        per_student.setdefault(sid, []).append(score)

    rows = []
    for sid, scores in per_student.items():
        name = student_map.get(sid, sid[:8])
        avg = sum(s.f1 for s in scores) / len(scores)
        rows.append({
            "Student": name,
            "Exercises": len(scores),
            "Avg F1": f"{avg:.1%}",
            "Best F1": f"{max(s.f1 for s in scores):.1%}",
            "Avg Precision": f"{sum(s.precision for s in scores) / len(scores):.1%}",
            "Avg Recall": f"{sum(s.recall for s in scores) / len(scores):.1%}",
        })
    st.dataframe(rows, width="stretch")

    # Skill profile bar chart (S1-S7 detection rates)
    st.subheader("Skill Profile (S1-S7 Detection Rates)")
    skill_labels = ["S1 Surface", "S2 Grammar", "S3 Meaning", "S4 Completeness",
                    "S5 Terminology", "S6 Pragmatic", "S7 Discourse"]

    # Aggregate per-skill from scoring details if available
    skill_data = {}
    for score in class_scores:
        if hasattr(score, "per_skill_detection") and score.per_skill_detection:
            for skill_id, rate in score.per_skill_detection.items():
                skill_data.setdefault(skill_id, []).append(rate)

    if skill_data:
        import plotly.graph_objects as go
        skills = []
        rates = []
        for i, label in enumerate(skill_labels):
            sid = f"S{i+1}"
            vals = skill_data.get(sid, [])
            skills.append(label)
            rates.append(sum(vals) / len(vals) if vals else 0)

        fig = go.Figure(go.Bar(x=skills, y=rates, marker_color="#3b82f6"))
        fig.update_layout(yaxis_title="Detection Rate", yaxis_range=[0, 1], height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Detailed per-skill data will appear once items with ToM-level annotations are completed.")


def _analytics_individual_student():
    """Individual student analytics with performance over time."""
    from tompe.schemas.scoring import ScoringResult
    from tompe.services.datastore import responses_store, feedback_store
    from tompe.schemas.response import StudentResponse

    classes = list_classes()
    if not classes:
        st.info("No classes yet.")
        return

    class_options = {c.class_name: c.class_id for c in classes}
    sel_class = st.selectbox("Class", list(class_options.keys()), key="analytics_student_class")
    class_id = class_options[sel_class]
    students = list_students(class_id)

    if not students:
        st.info("No students.")
        return

    student_options = {s.display_name: s.student_id for s in students}
    sel_student = st.selectbox("Student", list(student_options.keys()), key="analytics_student_sel")
    student_id = student_options[sel_student]

    all_responses = responses_store.list_all(StudentResponse)
    student_resps = [r for r in all_responses if r.student_id == student_id]

    if not student_resps:
        st.info(f"No responses yet for {sel_student}.")
        return

    all_scores = feedback_store.list_all(ScoringResult)
    resp_ids = {r.response_id for r in student_resps}
    student_scores = sorted(
        [s for s in all_scores if s.response_id in resp_ids],
        key=lambda s: s.response_id,
    )

    if not student_scores:
        st.info("No scored responses yet.")
        return

    col1, col2, col3 = st.columns(3)
    avg_f1 = sum(s.f1 for s in student_scores) / len(student_scores)
    col1.metric("Total Responses", len(student_scores))
    col2.metric("Avg F1", f"{avg_f1:.1%}")
    col3.metric("Latest F1", f"{student_scores[-1].f1:.1%}")

    # Performance over time
    st.subheader("Performance Over Time")
    f1_series = [s.f1 for s in student_scores]
    st.line_chart({"F1 Score": f1_series})

    # Wasserstein skill profile visualization
    st.subheader("Skill Profile — Wasserstein Transport")
    st.caption(
        "Shows current skill mastery vs. expert target. "
        "Arrows indicate optimal mastery redistribution (transport plan)."
    )
    try:
        import numpy as np
        import plotly.graph_objects as go
        from experiments.wasserstein.config import TARGET_PROFILE, SKILL_LABELS, SKILL_NAMES

        # Build student profile from per-skill data if available
        student_profile = {}
        for score in student_scores:
            if hasattr(score, "per_skill_detection") and score.per_skill_detection:
                for skill, rate in score.per_skill_detection.items():
                    student_profile.setdefault(skill, []).append(rate)

        if student_profile:
            current = {k: sum(v) / len(v) for k, v in student_profile.items()}
        else:
            # Approximate from overall F1
            current = {s: avg_f1 * TARGET_PROFILE[s] for s in SKILL_LABELS}

        target = TARGET_PROFILE

        labels = [f"{s} {SKILL_NAMES[s]}" for s in SKILL_LABELS]
        current_vals = [current.get(s, 0) for s in SKILL_LABELS]
        target_vals = [target[s] for s in SKILL_LABELS]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Current", x=labels, y=current_vals,
            marker_color="#3b82f6", opacity=0.8,
        ))
        fig.add_trace(go.Bar(
            name="Target", x=labels, y=target_vals,
            marker_color="#10b981", opacity=0.4,
        ))
        fig.update_layout(
            barmode="overlay",
            yaxis_title="Detection Rate",
            yaxis_range=[0, 1],
            height=350,
            legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Compute MasteryGap
        try:
            from experiments.wasserstein.metrics import w1_balanced
            from experiments.wasserstein.config import ADJACENCY, EDGE_WEIGHTS
            import numpy as np

            # Build cost matrix from graph
            cost = np.full((7, 7), 100.0)
            np.fill_diagonal(cost, 0.0)
            for (i, j), w in EDGE_WEIGHTS.items():
                cost[i][j] = w
                cost[j][i] = w
            # Floyd-Warshall for shortest paths
            for k in range(7):
                for i in range(7):
                    for j in range(7):
                        if cost[i][k] + cost[k][j] < cost[i][j]:
                            cost[i][j] = cost[i][k] + cost[k][j]

            gap = w1_balanced(current, target, cost)
            st.metric("MasteryGap (W₁)", f"{gap:.3f}",
                      help="Wasserstein-1 distance from current profile to expert target. Lower = closer to mastery.")
        except Exception:
            pass

    except ImportError:
        st.caption("Install `POT` (Python Optimal Transport) for Wasserstein visualization.")
    except Exception as e:
        st.caption(f"Wasserstein visualization unavailable: {e}")

    # Level progression recommendation
    st.subheader("Level Progression")
    student = next((s for s in students if s.student_id == student_id), None)
    if student:
        st.write(f"**Current level:** {student.current_level}")
        st.write(f"**Allowed levels:** {', '.join(student.allowed_levels)}")

        if avg_f1 >= 0.8 and len(student_scores) >= 3:
            level_order = [l.value for l in AnnotationLevel]
            current_idx = level_order.index(student.current_level) if student.current_level in level_order else 0
            if current_idx < len(level_order) - 1:
                next_level = level_order[current_idx + 1]
                st.success(
                    f"System recommends promoting to **{next_level}** "
                    f"(F1 >= 80% over {len(student_scores)} responses)"
                )
                if st.button(f"Approve promotion to {next_level}", type="primary", key="promote_btn"):
                    update_student_levels(
                        student_id,
                        current_level=AnnotationLevel(next_level),
                        allowed_levels=[AnnotationLevel(l) for l in level_order[:current_idx + 2]],
                    )
                    st.success(f"Promoted {sel_student} to {next_level}!")
                    st.rerun()
        elif avg_f1 < 0.5 and len(student_scores) >= 3:
            st.warning("Performance below 50%. Consider providing additional support.")


def _analytics_blindspot():
    """ToM Blind Spot Analysis — MQM x ToM heatmap."""
    from tompe.schemas.scoring import ScoringResult
    from tompe.services.datastore import feedback_store

    all_scores = feedback_store.list_all(ScoringResult)
    if not all_scores:
        st.info("No scoring data yet. Blind spot analysis requires completed exercises.")
        return

    st.subheader("MQM x ToM Heatmap")
    st.caption(
        "Cells show average detection rate. Red = systematic weakness (< 50%). "
        "Data populates as students complete exercises with ToM-annotated items."
    )

    # Build heatmap from per-error detection data if available
    mqm_cats = ["Accuracy", "Fluency", "Terminology", "Style"]
    tom_levels = ["L1 Surface", "L2 Grammar", "L3 Meaning", "L4 Complete", "L5 Term"]

    # Placeholder heatmap structure
    import plotly.graph_objects as go
    import numpy as np

    # Extract from scores if per-error data exists
    has_detail = any(
        hasattr(s, "per_error_results") and s.per_error_results
        for s in all_scores
    )

    if has_detail:
        matrix = np.zeros((len(mqm_cats), len(tom_levels)))
        counts = np.zeros((len(mqm_cats), len(tom_levels)))
        for score in all_scores:
            for err_result in getattr(score, "per_error_results", []):
                mqm_idx = min(err_result.get("mqm_idx", 0), len(mqm_cats) - 1)
                tom_idx = min(err_result.get("tom_idx", 0), len(tom_levels) - 1)
                matrix[mqm_idx][tom_idx] += err_result.get("detected", 0)
                counts[mqm_idx][tom_idx] += 1

        rates = np.divide(matrix, counts, where=counts > 0, out=np.zeros_like(matrix))
    else:
        rates = np.full((len(mqm_cats), len(tom_levels)), np.nan)
        st.caption("Detailed per-error ToM data not yet available. Showing empty heatmap.")

    fig = go.Figure(go.Heatmap(
        z=rates,
        x=tom_levels,
        y=mqm_cats,
        colorscale="RdYlGn",
        zmin=0, zmax=1,
        text=np.where(np.isnan(rates), "—", np.round(rates * 100).astype(int).astype(str) + "%"),
        texttemplate="%{text}",
        hovertemplate="MQM: %{y}<br>ToM: %{x}<br>Detection: %{z:.0%}<extra></extra>",
    ))
    fig.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig, use_container_width=True)


def _analytics_data_export():
    """Data export in CSV and JSON formats."""
    import csv
    import io
    from tompe.schemas.scoring import ScoringResult
    from tompe.schemas.response import StudentResponse
    from tompe.services.datastore import responses_store, feedback_store

    st.subheader("Export Student Data")

    classes = list_classes()
    if not classes:
        st.info("No classes yet.")
        return

    class_options = {c.class_name: c.class_id for c in classes}
    sel_class = st.selectbox("Class", list(class_options.keys()), key="export_class")
    class_id = class_options[sel_class]
    students = list_students(class_id)
    student_ids = {s.student_id for s in students}
    student_map = {s.student_id: s for s in students}

    all_responses = responses_store.list_all(StudentResponse)
    class_responses = [r for r in all_responses if r.student_id in student_ids]

    if not class_responses:
        st.info("No response data to export yet.")
        return

    all_scores = feedback_store.list_all(ScoringResult)
    score_map = {s.response_id: s for s in all_scores}

    st.write(f"**{len(class_responses)} responses** from **{len(student_ids)} students**")

    # CSV Long format
    st.subheader("CSV (Long Format)")
    st.caption("One row per response per student.")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "student_id", "display_name", "item_id", "mode",
        "time_spent_seconds", "precision", "recall", "f1",
        "true_positives", "false_positives", "false_negatives",
    ])
    for resp in class_responses:
        student = student_map.get(resp.student_id)
        score = score_map.get(resp.response_id)
        writer.writerow([
            resp.student_id,
            student.display_name if student else "",
            resp.item_id,
            resp.mode,
            resp.time_spent_seconds,
            score.precision if score else "",
            score.recall if score else "",
            score.f1 if score else "",
            score.true_positives if score else "",
            score.false_positives if score else "",
            score.false_negatives if score else "",
        ])

    st.download_button(
        "Download CSV (Long)",
        data=buf.getvalue(),
        file_name="tompe_responses_long.csv",
        mime="text/csv",
    )

    # JSON format
    st.subheader("JSON (Full Detail)")
    json_data = []
    for resp in class_responses:
        student = student_map.get(resp.student_id)
        score = score_map.get(resp.response_id)
        entry = resp.model_dump(mode="json")
        entry["display_name"] = student.display_name if student else ""
        if score:
            entry["scoring"] = score.model_dump(mode="json")
        json_data.append(entry)

    st.download_button(
        "Download JSON",
        data=json.dumps(json_data, indent=2, default=str),
        file_name="tompe_responses.json",
        mime="application/json",
    )


# ── Study Management ──────────────────────────────────────────────────────────


def _page_study_management():
    st.header("🔬 Study Management")

    tab_setup, tab_monitor, tab_export = st.tabs(["Setup", "Monitor", "Export"])

    with tab_setup:
        _study_setup()

    with tab_monitor:
        _study_monitor()

    with tab_export:
        _study_export()


def _study_setup():
    """Study setup: create/configure studies, upload segments, consent form."""
    st.subheader("Create Study")

    with st.form("create_study"):
        study_name = st.text_input("Study name", placeholder="e.g., ECTEL 2026 Evaluation Study")
        study_desc = st.text_area("Description", placeholder="Brief description of study goals...")

        col1, col2 = st.columns(2)
        with col1:
            n_segments = st.number_input("Segments per participant", value=20, min_value=1, max_value=100)
            counterbalance = st.checkbox("Enable counterbalancing (Form A/B)", value=True)
        with col2:
            warmup_items = st.number_input("Warm-up items", value=1, min_value=0, max_value=5)
            max_consecutive = st.number_input("Max consecutive same-condition items", value=2, min_value=1)

        st.markdown("**Published items for study:**")
        items = items_store.list_all(
            AssessmentItem, filter_fn=lambda i: i.item_status == "published"
        )
        if items:
            item_options = {
                f"{i.item_id[:8]} | {i.domain} | {len(i.errors)} errors": i.item_id
                for i in items
            }
            selected_items = st.multiselect("Select items", list(item_options.keys()))
        else:
            st.caption("No published items. Create and publish items first.")
            selected_items = []

        st.markdown("**Consent form:**")
        consent_path = DATA_DIR / "consent"
        consent_files = list(consent_path.glob("consent_v*.md")) if consent_path.exists() else []
        if consent_files:
            st.success(f"Found {len(consent_files)} consent form(s)")
        else:
            st.warning("No consent form found. Upload one to data/consent/.")

        st.markdown("**Post-task questionnaire:**")
        questionnaire_items = [
            "Language proficiency (Likert 1-5)",
            "Field of study (text)",
            "Study level (choice: undergrad/master/phd/professional)",
            "MT usage frequency (choice: never/rarely/sometimes/often/daily)",
            "Translation strategy description (textarea)",
            "Prior PE experience (yes/no + details)",
        ]
        for q in questionnaire_items:
            st.checkbox(q, value=True, key=f"q_{q[:10]}")

        if st.form_submit_button("Create Study", type="primary"):
            if study_name and selected_items:
                study_id = str(uuid4())
                study_config = {
                    "study_id": study_id,
                    "name": study_name,
                    "description": study_desc,
                    "n_segments": n_segments,
                    "counterbalance": counterbalance,
                    "warmup_items": warmup_items,
                    "max_consecutive": max_consecutive,
                    "item_ids": [item_options[s] for s in selected_items],
                    "status": "draft",
                }
                study_path = DATA_DIR / "studies"
                study_path.mkdir(parents=True, exist_ok=True)
                (study_path / f"{study_id}.json").write_text(
                    json.dumps(study_config, indent=2), encoding="utf-8"
                )
                st.success(f"Study '{study_name}' created! ID: {study_id[:8]}")
            else:
                st.warning("Please provide a study name and select items.")


def _study_monitor():
    """Monitor active studies: participation, completion rates."""
    study_path = DATA_DIR / "studies"
    if not study_path.exists():
        st.info("No studies created yet.")
        return

    studies = list(study_path.glob("*.json"))
    if not studies:
        st.info("No studies created yet.")
        return

    for sp in studies:
        config = json.loads(sp.read_text(encoding="utf-8"))
        with st.expander(f"{config['name']} ({config.get('status', 'draft')})"):
            st.write(f"**ID:** {config['study_id'][:12]}")
            st.write(f"**Items:** {len(config.get('item_ids', []))}")
            st.write(f"**Segments per participant:** {config.get('n_segments', '?')}")

            # Count participants
            resp_dir = DATA_DIR / "studies" / "responses" / config["study_id"]
            n_participants = 0
            n_completed = 0
            if resp_dir.exists():
                for rp in resp_dir.glob("*.json"):
                    n_participants += 1
                    rdata = json.loads(rp.read_text(encoding="utf-8"))
                    if rdata.get("completed"):
                        n_completed += 1

            col1, col2, col3 = st.columns(3)
            col1.metric("Participants", n_participants)
            col2.metric("Completed", n_completed)
            col3.metric("Completion Rate",
                        f"{n_completed / n_participants:.0%}" if n_participants else "—")


def _study_export():
    """Export study data in CSV/JSON."""
    study_path = DATA_DIR / "studies"
    if not study_path.exists():
        st.info("No studies to export.")
        return

    studies = list(study_path.glob("*.json"))
    if not studies:
        st.info("No studies to export.")
        return

    study_options = {}
    for sp in studies:
        config = json.loads(sp.read_text(encoding="utf-8"))
        study_options[config["name"]] = config

    sel_study = st.selectbox("Study", list(study_options.keys()), key="export_study")
    config = study_options[sel_study]

    resp_dir = DATA_DIR / "studies" / "responses" / config["study_id"]
    if not resp_dir.exists():
        st.info("No response data for this study.")
        return

    responses = []
    for rp in resp_dir.glob("*.json"):
        responses.append(json.loads(rp.read_text(encoding="utf-8")))

    if not responses:
        st.info("No responses to export.")
        return

    st.write(f"**{len(responses)} participant(s)**")

    # JSON download
    st.download_button(
        "Download JSON",
        data=json.dumps(responses, indent=2, default=str),
        file_name=f"study_{config['study_id'][:8]}.json",
        mime="application/json",
    )

    # CSV long format
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "participant_id", "form", "segment_id", "condition",
        "acceptable", "justification", "confidence", "time_seconds",
    ])
    for participant in responses:
        pid = participant.get("participant_id", "")
        form = participant.get("form", "")
        for seg_resp in participant.get("segment_responses", []):
            writer.writerow([
                pid, form,
                seg_resp.get("segment_id", ""),
                seg_resp.get("condition", ""),
                seg_resp.get("acceptable", ""),
                seg_resp.get("justification", ""),
                seg_resp.get("confidence", ""),
                seg_resp.get("time_seconds", ""),
            ])

    st.download_button(
        "Download CSV (Long)",
        data=buf.getvalue(),
        file_name=f"study_{config['study_id'][:8]}_long.csv",
        mime="text/csv",
    )


# ── Settings ─────────────────────────────────────────────────────────────────


def _page_settings():
    st.header("⚙️ Settings")

    tab_api, tab_mt, tab_system, tab_launch = st.tabs(
        ["API Credentials", "MT Systems", "System Configuration", "Launch Controls"]
    )

    with tab_api:
        _settings_api_credentials()

    with tab_mt:
        _settings_mt_systems()

    with tab_system:
        _settings_system_config()

    with tab_launch:
        _settings_launch_controls()


def _settings_launch_controls():
    """Launch and manage student app and API server."""
    import subprocess

    st.subheader("Student App")

    # Check if student app is running
    try:
        import httpx
        resp = httpx.get("http://127.0.0.1:7860/", timeout=2)
        student_running = resp.status_code == 200
    except Exception:
        student_running = False

    if student_running:
        st.success("Student app is running at http://localhost:7860")
    else:
        st.warning("Student app is not running")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Student App", type="primary"):
            try:
                subprocess.Popen(
                    ["uv", "run", "tompe-student"],
                    cwd=str(Path(__file__).resolve().parent.parent.parent.parent),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt" else 0,
                )
                st.success("Student app starting... Wait a few seconds then refresh.")
            except Exception as e:
                st.error(f"Failed to start: {e}")
    with col2:
        st.text_input("Student URL", value="http://localhost:7860", disabled=True)

    st.divider()
    st.subheader("API Server")

    try:
        import httpx
        resp = httpx.get("http://127.0.0.1:8000/docs", timeout=2)
        api_running = resp.status_code == 200
    except Exception:
        api_running = False

    if api_running:
        st.success("API server is running at http://localhost:8000")
    else:
        st.warning("API server is not running. Start it with: `uv run tompe-api`")

    st.divider()
    st.subheader("Share Link")
    st.caption(
        "To create a public URL for student access (useful for remote classes), "
        "restart the student app with `share=True` in the launch configuration."
    )


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
