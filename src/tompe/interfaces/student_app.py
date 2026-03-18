"""Gradio student interface.

Provides evaluation mode, post-editing mode, navigator mode, comparison mode,
justification prompts, feedback display, and progress dashboard.
"""

import gradio as gr


def build_student_app() -> gr.Blocks:
    """Build the Gradio student interface."""
    with gr.Blocks(title="ToM-PE — Student", theme=gr.themes.Soft()) as app:
        gr.Markdown("# ToM-PE — MT Post-Editing Training")
        gr.Markdown("*Theory of Mind-Informed Platform for Scaffolded MT Post-Editing Training*")

        with gr.Tabs():
            # ── Exercise tab ────────────────────────────────────────────────
            with gr.TabItem("Exercise"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Source Text")
                        source_display = gr.HTML(label="Source")

                    with gr.Column(scale=1):
                        gr.Markdown("### MT Output")
                        mt_display = gr.HTML(label="MT Output")

                with gr.Row():
                    mode_selector = gr.Radio(
                        choices=["Navigator", "Evaluation", "Post-Editing", "Comparison"],
                        label="Exercise Mode",
                        value="Evaluation",
                    )

                # Justification area
                gr.Markdown("### Your Justification")
                justification_input = gr.Textbox(
                    label="Explain your reasoning",
                    lines=4,
                    placeholder="What did the MT system misunderstand? "
                    "What did the author mean? How would a reader misinterpret this?",
                )

                submit_btn = gr.Button("Submit", variant="primary")

                # Feedback area (hidden until submission)
                feedback_display = gr.HTML(label="Feedback", visible=False)

            # ── Progress tab ────────────────────────────────────────────────
            with gr.TabItem("Progress"):
                gr.Markdown("### Your Performance")
                gr.Markdown("*Progress charts will appear here after completing exercises.*")

    return app


def main():
    """Launch the student interface."""
    app = build_student_app()
    app.launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
