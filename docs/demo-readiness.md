# ToM-PE Demo Readiness Checklist

**Goal:** a *full* system demonstration — teacher dashboard, student training loop (L0→L3),
expert annotation tool, and (optionally) the research pipeline producing numbers.

**Why this doc exists:** per [implementation-audit.md](implementation-audit.md), nearly every
feature across sprints #1–#10 is marked *"Done (smoke-tested / unit-tested)"* but the
**manual end-to-end browser checkboxes are unchecked**. For a live demo those un-run
walkthroughs — not the research backlog — are the real risk surface. This checklist tiers the
work and inlines the runnable verification commands from the audit.

> **Scope note.** The heavy *research* bottlenecks (expert annotation run, xCOMET-XL on GPU,
> full codebook authoring) gate the **paper**, not the **running system**. The platform demos
> fine without them via taxonomy fallback. They live in the "Research pipeline" section below,
> clearly marked optional.

---

## Launch commands (reference)

| App | Framework | Command | Port |
|---|---|---|---|
| API backend | FastAPI | `uv run tompe-api` | (backend; student app depends on it) |
| Student UI | Gradio | `uv run tompe-student` / `python -m tompe.interfaces.student_app` | 7860 |
| Teacher dashboard | Streamlit | `uv run streamlit run src/tompe/interfaces/teacher_app.py` | (Streamlit default 8501) |
| Annotation tool | Gradio | `python -m tompe.interfaces.annotation_app` | 7861 |

> The student UI is an HTTP client to the API backend ([api_client.py](../src/tompe/interfaces/api_client.py));
> start `tompe-api` **before** the student app or logins will fail.

---

## P0 — Demo blockers (do first; each can break a live walkthrough)

### P0-1 — Annotation tool `done_view.select` crash — ✅ FIXED
- **Was:** [annotation_app.py:1053](../src/tompe/interfaces/annotation_app.py#L1053) called `.select()` on a
  `gr.Column` (`done_view`), which does not exist in **Gradio 6.5.1** → `AttributeError` at Blocks-build
  time (the app crashed on launch). The completion summary was already populated by the
  `submit_expl_btn.click` handler below it, so the `.select` block was dead+crashing code.
- **Fix:** removed the `.select` block and its orphaned `_show_done` helper; kept the load + submit-driven
  populate path.
- **Verify:**
  ```bash
  PYTHONPATH=src python -c "from tompe.interfaces.annotation_app import build_annotation_app; build_annotation_app(); print('builds OK')"
  ```
  Expect `builds OK` with no `AttributeError`.
- **Residual (P2-1 below):** a Gradio-6 `UserWarning` says `theme`/`css` passed to the `Blocks`
  constructor are ignored (moved to `launch()`). Custom annotation styling may not render — fix if the
  annotation tool's look matters on stage.

### P0-2 — Student core loop, in the browser
Run the full student walkthrough end-to-end (only ever smoke-tested):
- [ ] `uv run tompe-api` then `uv run tompe-student`; log in as a fresh student.
- [ ] Confirm route order **login → consent → tutorial (3 steps) → main** (Sprint #10).
- [ ] L1/L2 item: span-select → classify (pill) → severity → **Justify gates Feedback** → 3-layer feedback cards.
- [ ] PE-mode item: edit translation → live diff updates ([_build_pe_diff_html], Sprint #6 B8) → Proceed
      advances (the old dead-button bug, Sprint #1 A1) → `edited_text` persisted in
      `data/sessions/responses/<id>.json` (not null).

### P0-3 — L0 Confirm/Dispute + Trap Detector
Newest, most-wired feature (Sprint #4); manual box unchecked:
- [ ] Teacher Exercise Builder → Level = **Navigator** → "False annotation source (L0)" select appears.
- [ ] **Default the picker to `rule`** for the demo unless you have done one real `llm`-mode call first
      (Sprint #4 follow-up: `llm` mode needs `injection_llm` in `mt_backends.yaml` + a live API key; the app
      falls back to rule-mode with a warning if missing).
- [ ] Student L0 view shows Confirm/Dispute cards (not the span panel); submitting without verifying every
      card warns; correct disputes accumulate.
- [ ] Dispute 10 false annotations correctly → **Trap Detector** badge appears in My Progress
      (`badges_visible=True`).
- **Note:** the audit's engineering backlog row B3 still lists this as "pending ~1–2 days" — that row is
  **stale**; Sprint #4 resolved it. Treat as done-but-verify.

### P0-4 — Seed demo data (prerequisite for analytics/radar/BKT)
A fresh student renders **empty** radar / BKT / Blind Spots / analytics — looks broken on stage.
- [ ] Have ≥1 student with **≥3 completed exercises** spanning the levels you'll show.
- [ ] Have **published** exercises at each level you'll demo (L0, L1/L2, and L3 if shown).
- [ ] Existing data is present: `data/students/`, `data/items/`, `data/exercises/` are non-empty —
      confirm the demo student actually has scored responses (`data/sessions/responses/`,
      `data/bkt/<id>.json`, `data/profiles/<id>.json`).

---

## P1 — Demo quality (visible, not crashing)

### P1-1 — Teacher analytics views (needs P0-4 data)
- [ ] Analytics → Individual Student: **Skill Mastery (BKT)** table shows 7 rows, non-zero p(mastery) for
      practised skills; **Blind Spots** table shows MQM×ToM cells <50% over ≥3 sessions with example item ids;
      **Level Progression** either offers a promotion (BKT rationale) or names blocking skills
      (e.g. `S3 (p=0.42, n=12)`). (Sprint #9)
- [ ] Exercise Builder → "AI-suggested items from a student's blind spots" → pick the student →
      "Compute suggestions" pre-fills the multiselect ([recommend_exercises], Sprint #9).

### P1-2 — L3 Comparison: populate `quality_score` before demoing τ
If you show L3 multi-MT comparison, the reveal panel displays **Kendall's τ vs expert ranking**. The teacher
pipeline currently leaves `MTOutput.quality_score=None`, so `derive_expert_ranking` falls back to **input
order** and τ is meaningless (Sprint #7 scope decision).
- [ ] Either wire COMET/GEMBA-MQM to populate `quality_score` in `_run_comparison_pipeline`, **or** hand-set
      `quality_score` on the demo comparison items so the expert ranking is real.
- [ ] Verify the reveal: student ranking vs expert ranking, τ line, and human-pick verdict all render
      ([_build_comparison_reveal_html]).

### P1-3 — Badges + XP path
- [ ] Clean Sheet fires on a perfect item (`item_results` plumbed, Sprint #1 A2).
- [ ] `badge_threshold_overrides` makes a tier fire earlier; `badges_visible=false` hides Badge Collection +
      XP card while tracking continues (Sprint #1 A3).

### P1-4 — Teacher utility buttons (if shown)
- [ ] API Credentials → **Test Connection**: real call now (Sprint #6 B10). Pre-set the API keys you'll demo;
      expect a green OK toast, "No API key configured" when unset.
- [ ] **Upload Corpus** (TMX/TSV): writes `data/corpora/{name}/segments_en_fr.jsonl` (Sprint #6 B11).
      Reminder: uploaded corpora are **not** auto-registered in `CORPORA` for batch runs.

### P1-5 — Test suite baseline (sanity gate before demo day)
```bash
PYTHONPATH=src pytest tests/ -q
```
Audit baseline was **37 passed, 3 skipped**. Investigate any new failures before the demo.

---

## P2 — Optional polish

- **P2-1 — Annotation app CSS/theme under Gradio 6.** Move `theme`/`css` from the `gr.Blocks(...)`
  constructor to `app.launch(...)` in [annotation_app.py](../src/tompe/interfaces/annotation_app.py) so the
  custom styling (timer display, completion screen, span highlights) actually applies. (Surfaced by the
  build warning during the P0-1 fix.)
- **Skill Radar hover tooltips** (BKT prob + n_obs per axis) — SVG has no `<title>` points yet (Sprint #5 follow-up).
- **L0 decoy-reveal panel** — "decoys you spotted/missed" is implicit in the per-error layout (Sprint #4 follow-up).
- **Tutorial reset** path for returning students (Sprint #10 follow-up).
- **PE diff polish** — char-level `difflib` can render messy on long edits (Sprint #6 follow-up).

---

## Full-demo walkthrough script (suggested order)

1. **Teacher**: browse corpus → generate translations → build exercises at L0 / L1-L2 / L3 (incl. one
   Comparison item with `quality_score` set, per P1-2). Assign to the demo student.
2. **Student**: login → consent → tutorial → run one item per level (L0 Confirm/Dispute, L1/L2
   annotate-justify-feedback, optional PE edit with live diff, L3 comparison ranking + "which is human?").
3. **Student**: My Progress → Skill Radar (non-zero), badges/XP, level unlocks.
4. **Teacher**: Analytics → Individual Student (BKT mastery, blind spots, progression rationale) →
   AI-suggested exercise from blind spots.
5. **Annotation tool** (optional): Phase A annotate → Phase B explanation ratings → completion summary
   (now that P0-1 is fixed).

---

## Research pipeline (OPTIONAL — only if demoing camera-ready numbers)

The running system does **not** need these. They gate the paper's validation section. Pull in only if the
demo is specifically "the pipeline producing results."

Unattended tooling (works today):
```bash
PYTHONPATH=src python -m experiments.pipeline_validation.generate_batch --single-error   # -> results/batch_200.jsonl
PYTHONPATH=src python -m experiments.pipeline_validation.run_all                          # Tracks A + B
PYTHONPATH=src python -m experiments.pipeline_validation.ablation_tagging --n-items 30    # Layer 1 metrics
PYTHONPATH=src python -m experiments.pipeline_validation.track_c.build_annotation_set     # annotation_set.json
PYTHONPATH=src python -m experiments.pipeline_validation.tables                           # table{1,2,3,4}.tex
```

Human/hardware bottlenecks (do **not** block a system demo — see audit §"what gates the paper"):
- **A3 expert annotation run** (1–3 experts) — gates all Track C numbers. No workaround.
- **A1 codebook authoring** — review 3 drafted seeds + fill the 34 scaffolded stubs in
  `data/codebook/error_codebook_fr_en.{drafts,stubs}.json`. System runs via taxonomy fallback meanwhile;
  only few-shot quality suffers. Backlog: `python scripts/scaffold_codebook_entries.py --list-missing`.
- **A4 xCOMET-XL on GPU** — deferred by design; GEMBA-MQM is the sole QE check until a CUDA host lands.
- **A7 real-MT authentic corpus** — keeps `ANNOTATION_AUTHENTIC=12` at 0; authentic-vs-controlled arm empty.

---

## Open questions for the demo owner

- Does the demo include the **annotation tool** and/or the **research pipeline**, or just teacher+student?
  (Affects whether P0-1/P2-1 and the research section matter.)
- Which **levels** (L0/L1/L2/L3) will actually be shown? (L3 pulls in P1-2.)
