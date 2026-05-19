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
    update_student_class,
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
        "🔍 QE Validation",
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
    elif page == "🔍 QE Validation":
        _page_qe_validation()
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

            st.divider()
            if st.button("Delete this error", key=f"del_err_{iid}_{i}", type="secondary"):
                updated_errors = [e for j, e in enumerate(item.errors) if j != i]
                items_store.update(iid, AssessmentItem, {"errors": [e.model_dump() for e in updated_errors]})
                st.success(f"Error {i+1} deleted.")
                st.rerun()

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


# ── QE Validation ────────────────────────────────────────────────────────────


def _page_qe_validation():
    st.header("🔍 QE Validation (GEMBA-MQM)")
    st.caption(
        "Validate items using GEMBA-MQM: an LLM independently evaluates the translation "
        "and checks whether the injected errors are detectable. Items that pass validation "
        "have higher confidence in their error annotations."
    )

    # Show items that can be validated (draft or reviewed)
    items = items_store.list_all(
        AssessmentItem,
        filter_fn=lambda i: i.item_status in ("draft", "reviewed", "published"),
    )

    if not items:
        st.info("No items to validate. Generate items first.")
        return

    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("Status", ["All", "draft", "reviewed", "published"], key="qe_status")
    with col2:
        mt_config = _load_mt_config()

    if status_filter != "All":
        items = [i for i in items if i.item_status == status_filter]

    st.write(f"**{len(items)} items** available for validation")

    # Item selection
    item_options = {
        f"{i.item_id[:8]}... | {i.domain} | {len(i.errors)} errors | {i.item_status}": i.item_id
        for i in items
    }
    selected_items = st.multiselect("Select items to validate", list(item_options.keys()), key="qe_items")

    col_run, col_batch = st.columns(2)
    with col_run:
        run_single = st.button("Validate Selected", type="primary")
    with col_batch:
        run_all = st.button("Validate All Pending")

    items_to_validate = []
    if run_single and selected_items:
        items_to_validate = [items_store.get(item_options[s], AssessmentItem) for s in selected_items]
        items_to_validate = [i for i in items_to_validate if i is not None]
    elif run_all:
        items_to_validate = [i for i in items if i.item_status in ("draft", "reviewed")]

    if items_to_validate:
        _run_qe_validation(items_to_validate, mt_config)

    # Show previous validation results
    st.divider()
    st.subheader("Validation Results")
    _show_qe_results(items)


def _run_qe_validation(items_to_validate, mt_config):
    """Run GEMBA-MQM validation on selected items."""
    import asyncio
    from tompe.pipeline.qe_validator import validate_item_gemba

    injection_config = mt_config.get("injection_llm", {})
    if not injection_config:
        st.error("No injection LLM configured. Check config/mt_backends.yaml.")
        return

    loop = asyncio.new_event_loop()
    progress = st.progress(0)
    status = st.empty()
    results_container = st.container()

    for idx, item in enumerate(items_to_validate):
        progress.progress((idx + 1) / len(items_to_validate))
        status.info(f"Validating item {idx+1}/{len(items_to_validate)}: {item.item_id[:8]}...")

        try:
            result = loop.run_until_complete(
                validate_item_gemba(
                    source_text=item.source_text,
                    reference=item.reference_translation,
                    injected_text=item.presented_text,
                    injected_errors=item.errors,
                    llm_config=injection_config,
                    source_lang=item.source_lang,
                    target_lang=item.target_lang,
                )
            )

            # Store result as teacher_notes metadata
            qe_summary = (
                f"[QE] GEMBA: {result.overall_quality} ({result.overall_score}/100) | "
                f"Detected: {result.gemba_detected}/{result.total_injected} | "
                f"Extra: {result.gemba_extra} | "
                f"Status: {result.status}"
            )
            existing_notes = item.teacher_notes or ""
            # Replace previous QE note if exists
            lines = [l for l in existing_notes.split("\n") if not l.startswith("[QE]")]
            lines.insert(0, qe_summary)
            new_notes = "\n".join(lines).strip()
            items_store.update(item.item_id, AssessmentItem, {"teacher_notes": new_notes})

            with results_container:
                status_emoji = "✅" if result.passes_validation else "❌"
                st.write(
                    f"{status_emoji} **{item.item_id[:8]}** — "
                    f"Quality: {result.overall_quality} ({result.overall_score}/100) | "
                    f"Detected: {result.gemba_detected}/{result.total_injected} errors | "
                    f"Extra issues: {result.gemba_extra}"
                )

                if result.gemba_errors:
                    with st.expander("GEMBA-detected errors", expanded=False):
                        for g_err in result.gemba_errors:
                            sev_color = {"minor": "#f59e0b", "major": "#ef4444", "critical": "#7f1d1d"}.get(
                                g_err.severity, "#6b7280"
                            )
                            st.markdown(
                                f'<span style="color:{sev_color};font-weight:bold;">[{g_err.severity}]</span> '
                                f'**{g_err.category}** — "{g_err.span}" — {g_err.explanation}',
                                unsafe_allow_html=True,
                            )

                if result.score_degradation is not None:
                    st.caption(
                        f"Score degradation: {result.clean_score:.0f} (clean) → "
                        f"{result.overall_score:.0f} (injected) = "
                        f"Δ{result.score_degradation:.0f}"
                    )

        except Exception as e:
            with results_container:
                st.warning(f"❌ {item.item_id[:8]} — Validation failed: {e}")

    loop.close()
    progress.progress(1.0)
    status.success(f"Validation complete for {len(items_to_validate)} items.")


def _show_qe_results(items):
    """Show summary of QE validation results from teacher_notes."""
    passed = []
    failed = []
    pending = []

    for item in items:
        notes = item.teacher_notes or ""
        qe_line = next((l for l in notes.split("\n") if l.startswith("[QE]")), None)
        if qe_line:
            if "Status: passed" in qe_line:
                passed.append((item, qe_line))
            else:
                failed.append((item, qe_line))
        else:
            pending.append(item)

    col1, col2, col3 = st.columns(3)
    col1.metric("Passed", len(passed))
    col2.metric("Failed", len(failed))
    col3.metric("Pending", len(pending))

    if passed:
        with st.expander(f"✅ Passed ({len(passed)})", expanded=False):
            for item, note in passed:
                st.write(f"**{item.item_id[:8]}** | {item.domain} | {len(item.errors)} errors — {note}")

    if failed:
        with st.expander(f"❌ Failed ({len(failed)})", expanded=True):
            for item, note in failed:
                st.write(f"**{item.item_id[:8]}** | {item.domain} | {len(item.errors)} errors — {note}")
                if st.button("Review this item", key=f"qe_review_{item.item_id}"):
                    st.session_state["selected_review_item"] = item.item_id
                    st.session_state["nav_page"] = "📋 Review Queue"
                    st.rerun()

    if pending:
        with st.expander(f"⏳ Pending ({len(pending)})", expanded=False):
            for item in pending:
                st.write(f"**{item.item_id[:8]}** | {item.domain} | {len(item.errors)} errors | {item.item_status}")


# ── Published Items ──────────────────────────────────────────────────────────


def _page_published_items():
    st.header("📋 Published Items")

    items = items_store.list_all(
        AssessmentItem, filter_fn=lambda i: i.item_status == "published"
    )

    if not items:
        st.info("No published items yet. Approve items from the Review Queue.")
        return

    # Two-column layout like Review Queue
    col_list, col_detail = st.columns([1, 2])

    with col_list:
        st.subheader(f"Published ({len(items)})")
        for item in items:
            n_errors = len(item.errors)
            label = f"📄 {item.item_id[:8]}... | {item.domain} | {n_errors} errors"
            if st.button(label, key=f"pub_{item.item_id}", width="stretch"):
                st.session_state["selected_published_item"] = item.item_id

    with col_detail:
        item_id = st.session_state.get("selected_published_item")
        if item_id:
            item = items_store.get(item_id, AssessmentItem)
            if item:
                _render_published_detail(item)
        else:
            st.info("Select an item from the list to view or edit.")


def _render_published_detail(item: AssessmentItem):
    """Render detail panel for a published item with edit capabilities."""
    iid = item.item_id

    st.subheader(f"Item: {iid[:12]}...")
    st.markdown(
        f"**Status:** :green[published] | "
        f"**Domain:** {item.domain} | **Direction:** {item.source_lang}→{item.target_lang} | "
        f"**Difficulty:** {item.difficulty_level}/5 | **Errors:** {len(item.errors)} | "
        f"**MT System:** {item.mt_system}"
    )

    # Source + Translation
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Source Text**")
        st.text_area("Source", value=item.source_text, height=100, disabled=True, key=f"pub_src_{iid}")
    with col2:
        st.markdown("**Translation (with errors)**")
        new_presented = st.text_area(
            "Translation", value=item.presented_text, height=100, key=f"pub_tgt_{iid}"
        )

    st.markdown("**Reference Translation**")
    st.text(item.reference_translation)

    # Error manifest
    st.subheader("Error Manifest")
    for i, err in enumerate(item.errors):
        with st.expander(
            f"Error {i+1}: {TAG_LABELS.get(err.primary_tag, err.primary_tag)} "
            f"({err.severity}) — \"{err.injected_text if hasattr(err, 'injected_text') else ''}\"",
            expanded=False,
        ):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.selectbox(
                    "Category", [t.value for t in PrimaryTag],
                    index=[t.value for t in PrimaryTag].index(err.primary_tag)
                    if err.primary_tag in [t.value for t in PrimaryTag] else 0,
                    key=f"pub_cat_{iid}_{i}",
                )
            with col2:
                st.text_input("Error type", value=err.error_type, key=f"pub_type_{iid}_{i}")
            with col3:
                st.selectbox(
                    "Severity", [s.value for s in Severity],
                    index=[s.value for s in Severity].index(err.severity)
                    if err.severity in [s.value for s in Severity] else 0,
                    key=f"pub_sev_{iid}_{i}",
                )

            if hasattr(err, "injected_text"):
                st.text_input("Error text", value=err.injected_text, key=f"pub_errtxt_{iid}_{i}")
            st.text_input("Correct text", value=err.original_text, key=f"pub_orig_{iid}_{i}")

            if hasattr(err, "explanation") and err.explanation:
                st.markdown("**Layer 1 — Contrastive**")
                st.text_area(
                    "MT interpretation", value=err.explanation.mt_interpretation,
                    key=f"pub_l1mt_{iid}_{i}", height=60,
                )
                st.text_area(
                    "Actual meaning", value=err.explanation.actual_meaning,
                    key=f"pub_l1act_{iid}_{i}", height=60,
                )

            if hasattr(err, "system_behavior") and err.system_behavior:
                st.markdown("**Layer 2a — Conceptual**")
                st.text_area(
                    "Error mechanism", value=err.system_behavior.error_mechanism,
                    key=f"pub_l2a_{iid}_{i}", height=60,
                )

            st.divider()
            if st.button("Delete this error", key=f"pub_del_err_{iid}_{i}", type="secondary"):
                updated_errors = [e for j, e in enumerate(item.errors) if j != i]
                items_store.update(iid, AssessmentItem, {"errors": [e.model_dump() for e in updated_errors]})
                st.success(f"Error {i+1} deleted.")
                st.rerun()

    # Teacher notes
    st.subheader("Teacher Notes")
    notes = st.text_area("Internal notes", value=item.teacher_notes or "", key=f"pub_notes_{iid}")

    # Action buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Save Changes", type="primary", width="stretch", key=f"pub_save_{iid}"):
            items_store.update(iid, AssessmentItem, {
                "presented_text": new_presented,
                "teacher_notes": notes,
            })
            st.success("Changes saved!")
            st.rerun()
    with col2:
        if st.button("Unpublish (back to draft)", width="stretch", key=f"pub_unpub_{iid}"):
            items_store.update(iid, AssessmentItem, {"item_status": "draft"})
            st.warning("Item moved back to draft.")
            st.session_state.pop("selected_published_item", None)
            st.rerun()
    with col3:
        if st.button("Retire Item", width="stretch", key=f"pub_retire_{iid}"):
            items_store.update(iid, AssessmentItem, {"item_status": "retired"})
            st.warning("Item retired.")
            st.session_state.pop("selected_published_item", None)
            st.rerun()


# ── Exercise Builder ─────────────────────────────────────────────────────────


def _populate_false_annotations(
    exercise: Exercise,
    item_ids: list[str],
    mode: str,
    n_per_item: int,
) -> None:
    """Run the L0 false-annotation generator for each item and attach to exercise.

    Mutates `exercise.false_annotations` in place. Errors per item are caught and
    logged via Streamlit warnings; one bad item doesn't fail the whole exercise.
    """
    import asyncio

    from tompe.pipeline.false_annotation_generator import generate_false_annotations
    from tompe.pipeline.llm_client import make_client_from_config

    llm_client = None
    if mode == "llm":
        mt_config = _load_mt_config()
        injection_cfg = mt_config.get("injection_llm", {})
        if not injection_cfg.get("provider") or not injection_cfg.get("model"):
            st.warning(
                "LLM mode selected but `injection_llm` is missing/incomplete in "
                "config/mt_backends.yaml — falling back to rule-based decoys."
            )
            mode = "rule"
        else:
            try:
                llm_client = make_client_from_config(injection_cfg)
            except Exception as exc:
                st.warning(f"Could not build LLM client ({exc}); falling back to rule-based.")
                mode = "rule"
                llm_client = None

    loop = asyncio.new_event_loop()
    try:
        for iid in item_ids:
            item = items_store.get(iid, AssessmentItem)
            if not item:
                continue
            excluded = [(int(e.span_start), int(e.span_end)) for e in item.errors]
            try:
                decoys = loop.run_until_complete(
                    generate_false_annotations(
                        mode=mode,
                        source_text=item.source_text,
                        translation=item.presented_text,
                        excluded_ranges=excluded,
                        n=n_per_item,
                        llm_client=llm_client,
                    )
                )
            except Exception as exc:
                st.warning(f"False-annotation generation failed for item {iid[:8]}: {exc}")
                decoys = []
            if decoys:
                exercise.false_annotations[iid] = decoys
    finally:
        loop.close()


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
        ex_just = st.selectbox(
            "Justification type",
            ["per_error_short", "per_error_structured", "global_free_text", "none"],
            format_func=lambda x: {
                "per_error_short": "Per error — short (adaptive prompt)",
                "per_error_structured": "Per error — structured (3 ToM fields)",
                "global_free_text": "Global free text (one box per item)",
                "none": "None (skip justification)",
            }[x],
        )
        ex_order = st.selectbox("Item ordering", ["manual", "difficulty", "random"])
        ex_domain = st.text_input("Domain label", placeholder="e.g., Parliamentary")
        ex_direction = st.text_input("Direction", placeholder="e.g., FR→EN")

    # Level-specific options
    if ex_level == "navigator":
        false_ratio = st.slider("False annotation ratio (L0)", 0.0, 0.5, 0.25, 0.05)
        col_fmode, col_fcount = st.columns(2)
        with col_fmode:
            false_mode = st.selectbox(
                "False annotation source (L0)",
                ["llm", "rule", "manual", "none"],
                format_func=lambda x: {
                    "llm": "LLM-generated (recommended)",
                    "rule": "Rule-based (cheap, weak distractors)",
                    "manual": "Teacher-authored via review queue",
                    "none": "Disabled — no false annotations",
                }[x],
                help=(
                    "Determines how plausible-but-wrong annotations are added to "
                    "each L0 item so students can practice Confirm/Dispute. "
                    "LLM mode requires `injection_llm` in mt_backends.yaml."
                ),
            )
        with col_fcount:
            false_count = st.number_input(
                "False annotations per item",
                min_value=0, max_value=5, value=2, step=1,
                help="Target count per item (the generator may return fewer).",
            )
    else:
        false_ratio = 0.0
        false_mode = "none"
        false_count = 0

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
            false_annotation_mode=false_mode,
            false_annotation_count=int(false_count),
            clean_segment_ratio=clean_ratio,
        )

        # L0: run the false-annotation generator on each item so verification mode
        # has decoys to dispute. "manual"/"none" leave exercise.false_annotations empty.
        if ex_level == "navigator" and false_mode in ("llm", "rule") and int(false_count) > 0:
            _populate_false_annotations(exercise, selected_ids, false_mode, int(false_count))

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


def _assign_class_exercises_to_student(student_id: str, class_id: str):
    """Auto-assign all exercises for a class to a new student."""
    exercises = exercises_store.list_all(
        Exercise,
        filter_fn=lambda ex: getattr(ex, "assigned_to_class", None) == class_id,
    )
    for ex in exercises:
        # Check if assignment already exists
        existing = assignments_store.list_all(
            ExerciseAssignment,
            filter_fn=lambda a, eid=ex.exercise_id, sid=student_id: (
                a.exercise_id == eid and a.student_id == sid
            ),
        )
        if not existing:
            assignment = ExerciseAssignment(
                assignment_id=str(uuid4()),
                exercise_id=ex.exercise_id,
                student_id=student_id,
            )
            assignments_store.save(assignment)
            if student_id not in ex.assigned_to_students:
                ex.assigned_to_students.append(student_id)
                exercises_store.save(ex)


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
                    acct = create_account(
                        username=row["username"].strip(),
                        display_name=row["display_name"].strip(),
                        password=row["password"].strip(),
                        class_id=class_id,
                    )
                    _assign_class_exercises_to_student(acct.student_id, class_id)
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
                        acct = create_account(new_username, new_display, new_password, class_id)
                        _assign_class_exercises_to_student(acct.student_id, class_id)
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
    all_classes = list_classes()
    class_name_map = {c.class_id: c.class_name for c in all_classes}
    class_id_list = [c.class_id for c in all_classes]
    class_name_list = [c.class_name for c in all_classes]

    # Table header
    hcol1, hcol2, hcol3, hcol4, hcol5, hcol6 = st.columns([2, 2, 1, 1, 1, 1])
    with hcol1:
        st.markdown("**Username**")
    with hcol2:
        st.markdown("**Name**")
    with hcol3:
        st.markdown("**Level**")
    with hcol4:
        st.markdown("**Class**")
    with hcol5:
        st.markdown("**Consent**")
    with hcol6:
        st.markdown("**Active**")

    for student in students:
        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1, 1, 1, 1])
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
            current_class_idx = class_id_list.index(student.class_id) if student.class_id in class_id_list else 0
            new_class_name = st.selectbox(
                "Class",
                class_name_list,
                index=current_class_idx,
                key=f"class_{student.student_id}",
                label_visibility="collapsed",
            )
            new_class_id = class_id_list[class_name_list.index(new_class_name)]
            if new_class_id != student.class_id:
                update_student_class(student.student_id, new_class_id)
                _assign_class_exercises_to_student(student.student_id, new_class_id)
                st.rerun()
        with col5:
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
        with col6:
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
                try:
                    create_class(name, [AnnotationLevel(l) for l in levels])
                    st.success(f"Class '{name}' created!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ── Analytics Dashboard ──────────────────────────────────────────────────────


def _page_analytics():
    st.header("📊 Analytics Dashboard")

    tab_class, tab_student, tab_blindspot, tab_badges, tab_export = st.tabs(
        ["Class Overview", "Individual Students", "ToM Blind Spot Analysis", "Badge Analytics", "Data Export"]
    )

    with tab_class:
        _analytics_class_overview()

    with tab_student:
        _analytics_individual_student()

    with tab_blindspot:
        _analytics_blindspot()

    with tab_badges:
        _analytics_badges()

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

    active_student_ids = {r.student_id for r in student_responses}

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Students", len(active_student_ids))
    col2.metric("Items Evaluated", len(class_scores))
    col3.metric("Avg Precision", f"{avg_precision:.1%}")
    col4.metric("Avg Recall", f"{avg_recall:.1%}")
    col5.metric("Avg F1", f"{avg_f1:.1%}")

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

    # Detection breakdown charts
    import plotly.graph_objects as go

    # Aggregate per-skill from detection_by_skill breakdown
    skill_detected: dict[str, int] = {}
    skill_total: dict[str, int] = {}
    for score in class_scores:
        for skill_id, cat_score in getattr(score, "detection_by_skill", {}).items():
            sid = skill_id if isinstance(skill_id, str) else skill_id.value
            skill_detected[sid] = skill_detected.get(sid, 0) + cat_score.detected
            skill_total[sid] = skill_total.get(sid, 0) + cat_score.total

    if skill_total:
        st.subheader("Skill Profile (S1-S7 Detection Rates)")
        skill_labels = ["S1 Surface", "S2 Grammar", "S3 Meaning", "S4 Completeness",
                        "S5 Terminology", "S6 Pragmatic", "S7 Discourse"]
        skills = []
        rates = []
        for i, label in enumerate(skill_labels):
            sid = f"S{i+1}"
            total = skill_total.get(sid, 0)
            skills.append(label)
            rates.append(skill_detected.get(sid, 0) / total if total > 0 else 0)

        fig = go.Figure(go.Bar(x=skills, y=rates, marker_color="#3b82f6"))
        fig.update_layout(yaxis_title="Detection Rate", yaxis_range=[0, 1], height=350)
        st.plotly_chart(fig, use_container_width=True, key="class_skill_profile")
    else:
        # Show MQM and ToM breakdowns from existing scoring data
        st.subheader("Detection by Category")

        mqm_detected: dict[str, int] = {}
        mqm_total: dict[str, int] = {}
        tom_detected: dict[str, int] = {}
        tom_total: dict[str, int] = {}
        for score in class_scores:
            for mqm, cat_score in score.detection_by_mqm.items():
                key = mqm if isinstance(mqm, str) else mqm.value
                mqm_detected[key] = mqm_detected.get(key, 0) + cat_score.detected
                mqm_total[key] = mqm_total.get(key, 0) + cat_score.total
            for tom, cat_score in score.detection_by_tom.items():
                key = tom if isinstance(tom, str) else tom.value
                tom_detected[key] = tom_detected.get(key, 0) + cat_score.detected
                tom_total[key] = tom_total.get(key, 0) + cat_score.total

        TOM_DISPLAY = {
            "1st_machine": "1st Order (Machine)",
            "1st_author": "1st Order (Author)",
            "2nd_reader": "2nd Order (Reader)",
            "recursive": "Recursive (Multi-agent)",
        }

        col_mqm, col_tom = st.columns(2)

        with col_mqm:
            st.markdown("**By MQM Category**")
            if mqm_total:
                cats = list(mqm_total.keys())
                rates = [mqm_detected.get(c, 0) / mqm_total[c] for c in cats]
                labels = [f"{c.title()} ({mqm_detected.get(c, 0)}/{mqm_total[c]})" for c in cats]
                fig = go.Figure(go.Bar(
                    x=rates, y=labels, orientation="h",
                    marker_color="#3b82f6",
                    text=[f"{r:.0%}" for r in rates], textposition="auto",
                ))
                fig.update_layout(
                    xaxis_title="Detection Rate", xaxis_range=[0, 1],
                    height=max(200, len(cats) * 50), margin=dict(l=0, r=0, t=10, b=0),
                )
                st.plotly_chart(fig, use_container_width=True, key="class_mqm")
            else:
                st.caption("No MQM data yet.")

        with col_tom:
            st.markdown("**By ToM Level**")
            if tom_total:
                levels = list(tom_total.keys())
                rates = [tom_detected.get(l, 0) / tom_total[l] for l in levels]
                labels = [
                    f"{TOM_DISPLAY.get(l, l)} ({tom_detected.get(l, 0)}/{tom_total[l]})"
                    for l in levels
                ]
                fig = go.Figure(go.Bar(
                    x=rates, y=labels, orientation="h",
                    marker_color="#8b5cf6",
                    text=[f"{r:.0%}" for r in rates], textposition="auto",
                ))
                fig.update_layout(
                    xaxis_title="Detection Rate", xaxis_range=[0, 1],
                    height=max(200, len(levels) * 50), margin=dict(l=0, r=0, t=10, b=0),
                )
                st.plotly_chart(fig, use_container_width=True, key="class_tom")
            else:
                st.caption("No ToM data yet.")


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
    col1.metric("Items Evaluated", len(student_scores))
    col2.metric("Avg F1", f"{avg_f1:.1%}")
    col3.metric("Latest F1", f"{student_scores[-1].f1:.1%}")

    # Performance over time
    st.subheader("Performance Over Time")
    f1_series = [s.f1 for s in student_scores]
    st.line_chart({"F1 Score": f1_series})

    # Build per-skill data from detection_by_skill breakdown
    import plotly.graph_objects as go
    skill_detected: dict[str, int] = {}
    skill_total: dict[str, int] = {}
    for score in student_scores:
        for skill_id, cat_score in getattr(score, "detection_by_skill", {}).items():
            sid = skill_id if isinstance(skill_id, str) else skill_id.value
            skill_detected[sid] = skill_detected.get(sid, 0) + cat_score.detected
            skill_total[sid] = skill_total.get(sid, 0) + cat_score.total

    has_skill_data = len(skill_total) >= 3  # need at least 3 skills observed

    if has_skill_data:
        # Wasserstein skill profile with transport arrows
        st.subheader("Skill Profile — Wasserstein Transport")
        st.caption(
            "Shows current skill mastery vs. expert target. "
            "Arrows indicate optimal mastery redistribution (transport plan)."
        )
        try:
            import sys
            import numpy as np
            _project_root = str(Path(__file__).resolve().parents[3])
            if _project_root not in sys.path:
                sys.path.insert(0, _project_root)
            from experiments.wasserstein.config import TARGET_PROFILE, SKILL_LABELS, SKILL_NAMES
            from experiments.wasserstein.ground_metrics import build_weighted_graph
            from experiments.wasserstein.dashboard_visualizations import (
                plot_student_profile_with_transport,
                _generate_interpretation,
                SKILL_DISPLAY,
            )

            current = {
                s: skill_detected.get(s, 0) / skill_total[s] if skill_total.get(s, 0) > 0 else 0
                for s in SKILL_LABELS
            }

            student_arr = np.array([current[s] for s in SKILL_LABELS])
            target_arr = np.array([TARGET_PROFILE[s] for s in SKILL_LABELS])
            cost_matrix = build_weighted_graph()

            fig_mpl, gap, plan = plot_student_profile_with_transport(
                student_profile=student_arr,
                target_profile=target_arr,
                ground_metric=cost_matrix,
                skill_names=SKILL_DISPLAY,
                student_name=sel_student,
            )
            fig_mpl.set_size_inches(7, 3.5)
            fig_mpl.set_dpi(100)
            fig_mpl.tight_layout()
            st.pyplot(fig_mpl, use_container_width=False)

            interpretation = _generate_interpretation(
                student_arr, target_arr, plan, [SKILL_NAMES[s] for s in SKILL_LABELS],
            )
            col_gap, col_interp = st.columns([1, 3])
            col_gap.metric(
                "MasteryGap (W₁)", f"{gap:.3f}",
                help="Wasserstein-1 distance from current profile to expert target. Lower = closer to mastery.",
            )
            col_interp.info(interpretation)

        except ImportError as e:
            st.caption(f"Install `POT` (Python Optimal Transport) for Wasserstein visualization. ({e})")
        except Exception as e:
            st.caption(f"Wasserstein visualization unavailable: {e}")
    else:
        # Not enough skill data — show MQM and ToM breakdowns we do have
        st.subheader("Detection by Error Category")

        # Aggregate detection_by_mqm across all scores
        mqm_detected: dict[str, int] = {}
        mqm_total: dict[str, int] = {}
        for score in student_scores:
            for mqm, cat_score in score.detection_by_mqm.items():
                key = mqm if isinstance(mqm, str) else mqm.value
                mqm_detected[key] = mqm_detected.get(key, 0) + cat_score.detected
                mqm_total[key] = mqm_total.get(key, 0) + cat_score.total

        # Aggregate detection_by_tom across all scores
        tom_detected: dict[str, int] = {}
        tom_total: dict[str, int] = {}
        for score in student_scores:
            for tom, cat_score in score.detection_by_tom.items():
                key = tom if isinstance(tom, str) else tom.value
                tom_detected[key] = tom_detected.get(key, 0) + cat_score.detected
                tom_total[key] = tom_total.get(key, 0) + cat_score.total

        col_mqm, col_tom = st.columns(2)

        with col_mqm:
            st.markdown("**By MQM Category**")
            if mqm_total:
                cats = list(mqm_total.keys())
                rates = [mqm_detected.get(c, 0) / mqm_total[c] for c in cats]
                labels = [f"{c.title()} ({mqm_detected.get(c, 0)}/{mqm_total[c]})" for c in cats]
                fig = go.Figure(go.Bar(
                    x=rates, y=labels, orientation="h",
                    marker_color="#3b82f6",
                    text=[f"{r:.0%}" for r in rates], textposition="auto",
                ))
                fig.update_layout(
                    xaxis_title="Detection Rate", xaxis_range=[0, 1],
                    height=max(200, len(cats) * 50), margin=dict(l=0, r=0, t=10, b=0),
                )
                st.plotly_chart(fig, use_container_width=True, key="student_mqm")
            else:
                st.caption("No MQM data yet.")

        TOM_DISPLAY = {
            "1st_machine": "1st Order (Machine)",
            "1st_author": "1st Order (Author)",
            "2nd_reader": "2nd Order (Reader)",
            "recursive": "Recursive (Multi-agent)",
        }
        with col_tom:
            st.markdown("**By ToM Level**")
            if tom_total:
                levels = list(tom_total.keys())
                rates = [tom_detected.get(l, 0) / tom_total[l] for l in levels]
                labels = [
                    f"{TOM_DISPLAY.get(l, l)} ({tom_detected.get(l, 0)}/{tom_total[l]})"
                    for l in levels
                ]
                fig = go.Figure(go.Bar(
                    x=rates, y=labels, orientation="h",
                    marker_color="#8b5cf6",
                    text=[f"{r:.0%}" for r in rates], textposition="auto",
                ))
                fig.update_layout(
                    xaxis_title="Detection Rate", xaxis_range=[0, 1],
                    height=max(200, len(levels) * 50), margin=dict(l=0, r=0, t=10, b=0),
                )
                st.plotly_chart(fig, use_container_width=True, key="student_tom")
            else:
                st.caption("No ToM data yet.")

        n_skills_observed = len(skill_total)
        st.info(
            f"Skill profile requires data on at least 3 of 7 skills (currently {n_skills_observed}). "
            "Wasserstein transport visualization will appear as the student completes more exercises."
        )

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
    """ToM Blind Spot Analysis — MQM x ToM heatmap + bar charts."""
    import numpy as np
    import plotly.graph_objects as go
    from tompe.schemas.item import AssessmentItem
    from tompe.schemas.response import StudentResponse
    from tompe.schemas.scoring import ScoringResult
    from tompe.services.datastore import feedback_store, responses_store
    from tompe.services.scoring import _TAG_TO_MQM, compute_span_iou, _text_overlap

    all_scores = feedback_store.list_all(ScoringResult)
    if not all_scores:
        st.info("No scoring data yet. Blind spot analysis requires completed exercises.")
        return

    # ── MQM x ToM Heatmap ──────────────────────────────────────────────────
    # Build from per-error ground truth by re-matching student responses to items
    MQM_LABELS = ["accuracy", "fluency", "terminology", "style", "locale"]
    MQM_DISPLAY = ["Accuracy", "Fluency", "Terminology", "Style", "Locale"]
    TOM_LABELS = ["1st_machine", "1st_author", "2nd_reader", "recursive"]
    TOM_DISPLAY = {
        "1st_machine": "1st Machine",
        "1st_author": "1st Author",
        "2nd_reader": "2nd Reader",
        "recursive": "Recursive",
    }

    # Load items and responses for cross-referencing
    matrix_detected = np.zeros((len(MQM_LABELS), len(TOM_LABELS)))
    matrix_total = np.zeros((len(MQM_LABELS), len(TOM_LABELS)))

    for score in all_scores:
        item = items_store.get(score.item_id, AssessmentItem)
        resp = responses_store.get(score.response_id, StudentResponse)
        if not item or not resp:
            continue

        ground_truth = item.errors
        student_errors = resp.identified_errors or []

        # Re-run greedy matching (same logic as scoring.py)
        gt_matched = [False] * len(ground_truth)
        for s_err in student_errors:
            best_iou = 0.0
            best_gt_idx = -1
            for gt_idx, gt_err in enumerate(ground_truth):
                if gt_matched[gt_idx]:
                    continue
                iou = compute_span_iou(
                    (s_err.span_start, s_err.span_end),
                    (gt_err.span_start, gt_err.span_end),
                )
                if iou < 0.3:
                    if _text_overlap(s_err.span_start, s_err.span_end, gt_err, item.presented_text):
                        iou = max(iou, 0.3)
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = gt_idx
            if best_iou >= 0.3 and best_gt_idx >= 0:
                gt_matched[best_gt_idx] = True

        # Accumulate per-error MQM x ToM counts
        for gt_idx, gt_err in enumerate(ground_truth):
            mqm_key = _TAG_TO_MQM.get(gt_err.primary_tag, "accuracy")
            tom_key = gt_err.tom_level if isinstance(gt_err.tom_level, str) else gt_err.tom_level.value
            mqm_idx = MQM_LABELS.index(mqm_key) if mqm_key in MQM_LABELS else 0
            tom_idx = TOM_LABELS.index(tom_key) if tom_key in TOM_LABELS else 0
            matrix_total[mqm_idx][tom_idx] += 1
            if gt_matched[gt_idx]:
                matrix_detected[mqm_idx][tom_idx] += 1

    # Compute rates, NaN where no data
    with np.errstate(divide="ignore", invalid="ignore"):
        rates = np.where(matrix_total > 0, matrix_detected / matrix_total, np.nan)

    has_data = np.any(matrix_total > 0)

    st.subheader("MQM x ToM Heatmap")
    st.caption(
        "Detection rate by MQM category and ToM level. "
        "Red cells (< 50%) indicate systematic blind spots."
    )

    if has_data:
        # Build text annotations showing rate + counts
        text_matrix = []
        for i in range(len(MQM_LABELS)):
            row = []
            for j in range(len(TOM_LABELS)):
                if matrix_total[i][j] > 0:
                    pct = int(round(rates[i][j] * 100))
                    row.append(f"{pct}%\n({int(matrix_detected[i][j])}/{int(matrix_total[i][j])})")
                else:
                    row.append("—")
            text_matrix.append(row)

        tom_display = [TOM_DISPLAY.get(t, t) for t in TOM_LABELS]
        fig = go.Figure(go.Heatmap(
            z=rates,
            x=tom_display,
            y=MQM_DISPLAY,
            colorscale="RdYlGn",
            zmin=0, zmax=1,
            text=text_matrix,
            texttemplate="%{text}",
            hovertemplate="MQM: %{y}<br>ToM: %{x}<br>Detection: %{z:.0%}<extra></extra>",
        ))
        fig.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True, key="blindspot_heatmap")
    else:
        st.caption("No per-error data available yet for the heatmap.")

    # ── Marginal bar charts ────────────────────────────────────────────────
    col_mqm, col_tom = st.columns(2)

    with col_mqm:
        st.markdown("**By MQM Category**")
        mqm_detected_m = {}
        mqm_total_m = {}
        for score in all_scores:
            for mqm, cat_score in score.detection_by_mqm.items():
                key = mqm if isinstance(mqm, str) else mqm.value
                mqm_detected_m[key] = mqm_detected_m.get(key, 0) + cat_score.detected
                mqm_total_m[key] = mqm_total_m.get(key, 0) + cat_score.total
        if mqm_total_m:
            cats = list(mqm_total_m.keys())
            rates_m = [mqm_detected_m.get(c, 0) / mqm_total_m[c] for c in cats]
            labels = [f"{c.title()} ({mqm_detected_m.get(c, 0)}/{mqm_total_m[c]})" for c in cats]
            colors = ["#ef4444" if r < 0.5 else "#22c55e" for r in rates_m]
            fig = go.Figure(go.Bar(
                x=rates_m, y=labels, orientation="h",
                marker_color=colors,
                text=[f"{r:.0%}" for r in rates_m], textposition="auto",
            ))
            fig.update_layout(
                xaxis_title="Detection Rate", xaxis_range=[0, 1],
                height=max(200, len(cats) * 60), margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig, use_container_width=True, key="blindspot_mqm")

    with col_tom:
        st.markdown("**By ToM Level**")
        tom_detected_m = {}
        tom_total_m = {}
        for score in all_scores:
            for tom, cat_score in score.detection_by_tom.items():
                key = tom if isinstance(tom, str) else tom.value
                tom_detected_m[key] = tom_detected_m.get(key, 0) + cat_score.detected
                tom_total_m[key] = tom_total_m.get(key, 0) + cat_score.total
        if tom_total_m:
            levels = list(tom_total_m.keys())
            rates_t = [tom_detected_m.get(l, 0) / tom_total_m[l] for l in levels]
            labels = [
                f"{TOM_DISPLAY.get(l, l)} ({tom_detected_m.get(l, 0)}/{tom_total_m[l]})"
                for l in levels
            ]
            colors = ["#ef4444" if r < 0.5 else "#22c55e" for r in rates_t]
            fig = go.Figure(go.Bar(
                x=rates_t, y=labels, orientation="h",
                marker_color=colors,
                text=[f"{r:.0%}" for r in rates_t], textposition="auto",
            ))
            fig.update_layout(
                xaxis_title="Detection Rate", xaxis_range=[0, 1],
                height=max(200, len(levels) * 60), margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig, use_container_width=True, key="blindspot_tom")


def _analytics_badges():
    """Badge Analytics — distribution heatmap, visibility toggle, threshold overrides."""
    import numpy as np
    import plotly.graph_objects as go
    from tompe.schemas.badges import (
        CATEGORY_BADGE_NAMES,
        CATEGORY_DISPLAY_NAMES,
        CATEGORY_THRESHOLDS,
        PROGRESSION_BADGES,
        StudentBadges,
    )
    from tompe.services.badges import get_badge_summary
    from tompe.services.datastore import badges_store

    classes = list_classes()
    if not classes:
        st.info("No classes yet.")
        return

    class_options = {c.class_name: c.class_id for c in classes}
    sel_class = st.selectbox("Class", list(class_options.keys()), key="badge_class")
    class_id = class_options[sel_class]
    class_obj = get_class(class_id)
    students = list_students(class_id)

    if not students:
        st.info("No students in this class.")
        return

    # ── Badge Distribution Heatmap ──────────────────────────────────────
    st.subheader("Badge Distribution")
    st.caption(
        "Rows = students, columns = specialisation badges. "
        "Cells show highest tier earned (0 = none, 1 = Bronze, 2 = Silver, 3 = Gold). "
        "Empty columns suggest underrepresented error categories in your item pool."
    )

    badge_categories = list(CATEGORY_BADGE_NAMES.keys())
    badge_display = [CATEGORY_DISPLAY_NAMES[c] for c in badge_categories]
    badge_ids = [CATEGORY_BADGE_NAMES[c] for c in badge_categories]

    tier_map = {"none": 0, "bronze": 1, "silver": 2, "gold": 3}
    student_names = []
    matrix = []

    for student in students:
        student_names.append(student.display_name)
        try:
            summary = get_badge_summary(student.student_id)
        except Exception:
            matrix.append([0] * len(badge_categories))
            continue

        row = []
        for spec_badge in summary.get("specialisation", []):
            highest = spec_badge.get("highest_tier", "none") or "none"
            row.append(tier_map.get(highest, 0))

        if len(row) == len(badge_categories):
            matrix.append(row)
        else:
            # Fallback: build from earned badges directly
            record = badges_store.get(student.student_id, StudentBadges)
            row = []
            for bid in badge_ids:
                tier = record.get_highest_tier(bid) if record else None
                row.append(tier_map.get(tier, 0) if tier else 0)
            matrix.append(row)

    matrix_np = np.array(matrix)

    # Custom colorscale: 0=grey, 1=copper, 2=silver, 3=gold
    colorscale = [
        [0.0, "#e5e7eb"],    # none — light grey
        [0.33, "#B87333"],   # bronze — copper
        [0.66, "#C0C0C0"],   # silver — steel
        [1.0, "#D4AF37"],    # gold
    ]

    # Text matrix for hover
    tier_labels = ["—", "Bronze", "Silver", "Gold"]
    text_matrix = [[tier_labels[v] for v in row] for row in matrix]

    fig = go.Figure(go.Heatmap(
        z=matrix_np,
        x=badge_display,
        y=student_names,
        colorscale=colorscale,
        zmin=0, zmax=3,
        text=text_matrix,
        texttemplate="%{text}",
        hovertemplate="Student: %{y}<br>Badge: %{x}<br>Tier: %{text}<extra></extra>",
        showscale=False,
    ))
    fig.update_layout(
        height=max(250, len(students) * 40 + 80),
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(side="top"),
    )
    st.plotly_chart(fig, use_container_width=True, key="badge_heatmap")

    # Summary: categories with no badges earned
    col_totals = matrix_np.sum(axis=0)
    empty_cats = [badge_display[i] for i in range(len(badge_display)) if col_totals[i] == 0]
    if empty_cats:
        st.warning(
            f"No students have earned badges for: **{', '.join(empty_cats)}**. "
            "Consider adding more items with these error categories to your exercises."
        )

    # ── Progression Badge Summary ───────────────────────────────────────
    st.subheader("Progression Badges")
    prog_data = []
    for student in students:
        try:
            summary = get_badge_summary(student.student_id)
            earned = [b["display_name"] for b in summary.get("progression", []) if b.get("earned")]
            prog_data.append({"Student": student.display_name, "Earned": ", ".join(earned) or "—"})
        except Exception:
            prog_data.append({"Student": student.display_name, "Earned": "—"})
    st.dataframe(prog_data, use_container_width=True)

    # ── XP Summary ──────────────────────────────────────────────────────
    st.subheader("XP Leaderboard")
    xp_data = []
    for student in students:
        record = badges_store.get(student.student_id, StudentBadges)
        xp = record.total_xp if record else 0
        n_badges = len(record.earned_badges) if record else 0
        xp_data.append({
            "Student": student.display_name,
            "Total XP": xp,
            "Badges Earned": n_badges,
        })
    xp_data.sort(key=lambda x: x["Total XP"], reverse=True)
    st.dataframe(xp_data, use_container_width=True)

    # ── Badge Settings ──────────────────────────────────────────────────
    st.subheader("Badge Settings")

    # Visibility toggle
    current_visible = class_obj.badges_visible if class_obj else True
    new_visible = st.toggle(
        "Show badges to students",
        value=current_visible,
        help="When disabled, students won't see the badge collection in their progress tab. Badge tracking continues internally.",
        key="badge_visibility_toggle",
    )
    if new_visible != current_visible and class_obj:
        from tompe.services.datastore import classes_store as _classes_store
        _classes_store.update(class_id, type(class_obj), {"badges_visible": new_visible})
        st.success(f"Badge visibility {'enabled' if new_visible else 'disabled'} for this class.")

    # Threshold overrides
    st.markdown("**Specialisation Badge Thresholds**")
    st.caption(
        "Override the default detection count thresholds for earning Bronze/Silver/Gold badges. "
        "Leave at default (0) to use the system defaults. Changes apply prospectively only."
    )
    current_overrides = class_obj.badge_threshold_overrides if class_obj else {}

    changed = False
    new_overrides = {}
    cols_header = st.columns([2, 1, 1, 1, 2])
    cols_header[0].markdown("**Category**")
    cols_header[1].markdown("**Bronze**")
    cols_header[2].markdown("**Silver**")
    cols_header[3].markdown("**Gold**")
    cols_header[4].markdown("**Default**")

    for cat in badge_categories:
        display = CATEGORY_DISPLAY_NAMES[cat]
        defaults = CATEGORY_THRESHOLDS[cat]
        override = current_overrides.get(cat, [0, 0, 0])

        cols = st.columns([2, 1, 1, 1, 2])
        cols[0].write(display)
        b = cols[1].number_input("B", value=override[0] if override[0] else 0, min_value=0, step=1, key=f"thr_b_{cat}", label_visibility="collapsed")
        s = cols[2].number_input("S", value=override[1] if len(override) > 1 and override[1] else 0, min_value=0, step=1, key=f"thr_s_{cat}", label_visibility="collapsed")
        g = cols[3].number_input("G", value=override[2] if len(override) > 2 and override[2] else 0, min_value=0, step=1, key=f"thr_g_{cat}", label_visibility="collapsed")
        cols[4].caption(f"{defaults[0]} / {defaults[1]} / {defaults[2]}")

        if b > 0 or s > 0 or g > 0:
            new_overrides[cat] = [b, s, g]

    if st.button("Save Threshold Overrides", key="save_thresholds"):
        if class_obj:
            from tompe.services.datastore import classes_store as _classes_store
            _classes_store.update(class_id, type(class_obj), {"badge_threshold_overrides": new_overrides})
            st.success("Threshold overrides saved. Changes apply to future badge awards only.")


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

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Start (local)", type="primary", disabled=student_running):
            try:
                subprocess.Popen(
                    ["uv", "run", "tompe-student"],
                    cwd=str(Path(__file__).resolve().parent.parent.parent.parent),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt" else 0,
                )
                import time as _time
                st.success("Student app starting...")
                _time.sleep(5)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start: {e}")
    with col2:
        if st.button("Start (share link)", disabled=student_running):
            try:
                subprocess.Popen(
                    ["uv", "run", "tompe-student", "--share"],
                    cwd=str(Path(__file__).resolve().parent.parent.parent.parent),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt" else 0,
                )
                import time as _time
                st.success("Student app starting with share link...")
                _time.sleep(5)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start: {e}")
    with col3:
        if st.button("Stop Student App", disabled=not student_running):
            try:
                import signal
                # Find the process on port 7860 and kill it
                if os.name == "nt":
                    result = subprocess.run(
                        ["netstat", "-ano"],
                        capture_output=True, text=True,
                    )
                    for line in result.stdout.splitlines():
                        if ":7860" in line and "LISTENING" in line:
                            pid = line.strip().split()[-1]
                            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                            st.success(f"Student app stopped (PID {pid}).")
                            break
                    else:
                        st.warning("Could not find student app process.")
                else:
                    subprocess.run(["fuser", "-k", "7860/tcp"], capture_output=True)
                    st.success("Student app stopped.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to stop: {e}")
    with col4:
        st.text_input("Local URL", value="http://localhost:7860", disabled=True)

    # Show share link if available
    share_link = st.session_state.get("share_link")
    if share_link:
        st.success(f"Share link: **{share_link}**")
        st.code(share_link, language=None)

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
