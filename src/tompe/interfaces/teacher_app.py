"""Streamlit teacher interface.

Provides item generation/review pipeline, class management, exercise builder,
analytics dashboard, and ToM blind spot analysis view.
"""

import streamlit as st


def main():
    """Launch the teacher interface."""
    st.set_page_config(
        page_title="ToM-PE — Teacher Dashboard",
        page_icon="📋",
        layout="wide",
    )

    st.title("ToM-PE — Teacher Dashboard")
    st.caption("Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training")

    # ── Sidebar navigation ──────────────────────────────────────────────────
    page = st.sidebar.radio(
        "Navigation",
        [
            "📋 Item Management",
            "📚 Exercise Builder",
            "👥 Class Management",
            "📊 Analytics Dashboard",
            "⚙️ Configuration",
        ],
    )

    # ── Page routing ────────────────────────────────────────────────────────
    if page == "📋 Item Management":
        _page_item_management()
    elif page == "📚 Exercise Builder":
        _page_exercise_builder()
    elif page == "👥 Class Management":
        _page_class_management()
    elif page == "📊 Analytics Dashboard":
        _page_analytics()
    elif page == "⚙️ Configuration":
        _page_configuration()


def _page_item_management():
    st.header("Item Management")
    tab_generate, tab_review, tab_published = st.tabs(
        ["Generate Items", "Review Queue", "Published Items"]
    )
    with tab_generate:
        st.info("Item generation pipeline will be connected here.")
    with tab_review:
        st.info("Items pending teacher review will appear here.")
    with tab_published:
        st.info("Approved items ready for exercises will appear here.")


def _page_exercise_builder():
    st.header("Exercise Builder")
    st.info("Exercise creation and management will be implemented here.")


def _page_class_management():
    st.header("Class Management")
    st.info("Student roster and exercise assignments will be managed here.")


def _page_analytics():
    st.header("Analytics Dashboard")
    tab_class, tab_student, tab_blindspot = st.tabs(
        ["Class Overview", "Individual Students", "ToM Blind Spot Analysis"]
    )
    with tab_class:
        st.info("Aggregate class performance charts will appear here.")
    with tab_student:
        st.info("Individual student performance view will appear here.")
    with tab_blindspot:
        st.info(
            "ToM Blind Spot Analysis — systematic weaknesses by MQM × ToM level will appear here."
        )


def _page_configuration():
    st.header("Configuration")
    st.info("MT systems, error profiles, and difficulty settings will be configured here.")


if __name__ == "__main__":
    main()
