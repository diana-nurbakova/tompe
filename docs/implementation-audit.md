# ToM-PE Implementation Audit

**Date:** 2026-05-09 (audit) · 2026-05-10 (sprint #1 + sprint #2 updates)
**Scope:** Spec-vs-code audit covering 8 specs in three groups
**Method:** Each spec read in full; every claim backed by `path:line` evidence verified by reading the cited line.

---

## How to read this document

Each spec gets its own section with:

1. A **gap table** with columns:
   - **Section** — spec section/heading.
   - **Feature** — short feature name.
   - **Status** — one of:
     - **Implemented** — runtime path exists, wired end-to-end.
     - **Partial** — schema/config/trigger exists but at least one consumer is missing; the note specifies what fraction is done.
     - **Missing** — no code path; spec'd but not built.
     - **N/A** — explicitly out of scope, deferred, or superseded.
   - **Evidence** — `path/to/file.ext:NN` references. `—` for Missing rows.
   - **Note** — ≤15-word summary.
2. A **Top 5 gaps** list — highest-leverage missing pieces in priority order.

The cross-spec synthesis at the top consolidates the most blocking gaps across all eight specs.

---

## Implementation sprint #1 — Tier A

**Date range:** 2026-05-09 → 2026-05-10
**Theme:** Wiring fixes + start of L0 Confirm/Dispute feature

### What landed

| ID | Item | Status | Files touched |
|---|---|---|---|
| A4 | Validation severity YAML knob (`validation_severity_distribution`) | Done | [config/settings.yaml](../config/settings.yaml), [experiments/pipeline_validation/config.py](../experiments/pipeline_validation/config.py), [experiments/pipeline_validation/generate_batch.py](../experiments/pipeline_validation/generate_batch.py) |
| A1 | PE submission flow — `pe_proceed_btn` event handler + `edited_text` plumbing | Done (static) | [src/tompe/interfaces/student_app.py](../src/tompe/interfaces/student_app.py) |
| A3 | `badges_visible` + `badge_threshold_overrides` plumbed through API + UI | Done (static) | [src/tompe/services/badges.py](../src/tompe/services/badges.py), [src/tompe/services/api.py](../src/tompe/services/api.py) |
| A2 | `item_results` plumbed for Clean Sheet badge | Done (static) | [src/tompe/services/api.py](../src/tompe/services/api.py) |
| A5a | False annotation generator core (LLM + rule + manual/none) | Done (unit-tested) | [src/tompe/pipeline/_false_annotation_prompts.py](../src/tompe/pipeline/_false_annotation_prompts.py), [src/tompe/pipeline/false_annotation_generator.py](../src/tompe/pipeline/false_annotation_generator.py), [src/tompe/schemas/session.py:90-102](../src/tompe/schemas/session.py#L90-L102) |

"Done (static)" = code changes verified by import / smoke test only; needs the manual checks below.
"Done (unit-tested)" = a small in-process unit test was run; integration with teacher/student UIs not yet wired.

### Still pending (A5 sub-pieces)

| ID | Item |
|---|---|
| A5a-wiring | Teacher exercise-builder mode picker + run generator on save |
| A5b | L0 Confirm/Dispute buttons + state in student app |
| A5c | Scoring logic that distinguishes correct/incorrect dispute and confirm |
| A5d | `correct_disputes` counter into `process_badges_and_xp` so Trap Detector fires |

---

## Verification checklist for sprint #1

Static smoke tests passed for everything in "What landed", but each item needs manual end-to-end confirmation before relying on it. Treat the boxes below as a punch list.

### A4 — validation severity YAML knob

- [ ] **Dry-run validation batch reads from YAML.** Run:

  ```bash
  python -m experiments.pipeline_validation.generate_batch --dry-run
  ```

  Expect log lines confirming 1 major error per injected item; nothing should mention `{minor: 1, major: 2, critical: 0}`.
- [ ] **Toggle is config-driven, not code-driven.** Edit `config/settings.yaml` → `error_injection.validation_severity_distribution` to `{minor: 2}`, re-run dry-run. Confirm the new value flows through (each item now plans 2 minor errors).
- [ ] **Production default unchanged.** Run `_build_error_profile(..., single_error=False)` (or any non-validation code path) and confirm it still picks up `default_severity_distribution {minor: 1, major: 2, critical: 0}`.

**What this confirms:** the validation/production toggle is finally a real config knob (Pipeline remediation §2.3, Validation §2.1).

### A1 — PE submission flow

- [ ] **Launch student app:** `python -m tompe.interfaces.student_app` and log in.
- [ ] **Start a PE exercise** (mode = `postediting` or `both`). The translation appears in `pe_textbox`.
- [ ] **Edit the translation** in the textbox, then click **"Proceed to Justification →"**. Confirm the button now advances (was previously dead).
- [ ] **For `justification_type=none` exercises:** confirm Proceed jumps directly to Feedback panel and HTER-based scoring renders.
- [ ] **For other justification modes:** confirm Justify panel opens; submitting Justify → Feedback shows and the response is saved.
- [ ] **Check the persisted response** at `data/sessions/responses/<response_id>.json` — `edited_text` must be the post-edited string, not null.
- [ ] **Edge case:** submit with empty edited text — confirm no crash, scoring handles empty PE.

**What this confirms:** the dead-button bug from UI Spec §3.4 is fixed end-to-end.

### A3 — badges visibility + threshold overrides

- [ ] **Teacher: toggle visibility off.** In teacher app, open a class, set `badges_visible = false`, save.
- [ ] **Student in that class:** log in, open My Progress. The Badge Collection panel and the XP card should both disappear.
- [ ] **Toggle back on:** student re-loads My Progress → both panels return.
- [ ] **Internal tracking unaffected:** during the "off" period, complete one exercise. Toggle back on. Confirm any badges earned during the off period now show up — i.e. tracking continued, only the response was masked (spec §8.3).
- [ ] **Threshold override:** in teacher app, set `badge_threshold_overrides["MISTRANSLATION"] = [5, 10, 20]`. As a student in that class, accumulate 5 correct mistranslation detections at L1+. Bronze should fire (vs the default threshold of 10).
- [ ] **Other classes unaffected:** a student in a class with no overrides should still see the default thresholds.
- [ ] **Notification toast respects visibility:** while badges are off, complete an exercise that would normally fire a badge. Confirm no toast appears in feedback.

**What this confirms:** Fluency Trap §8.3 (visibility + threshold override) is no longer "saved but ignored".

### A2 — Clean Sheet behaviour badge

- [ ] **Run a perfect item.** Pick an item with at least one true error. As a student at L2 or L3, identify all true errors with correct MQM category, zero false positives.
- [ ] **Submit and check feedback.** The badge notification toast should show "Clean Sheet" with count = 1.
- [ ] **My Progress** should now show Clean Sheet earned.
- [ ] **Repeatability:** complete a second perfect item. Confirm Clean Sheet count increments to 2 (visible as ×2 marker per spec §4.1).
- [ ] **Imperfect items don't trigger:** miss one error or add one false positive on a different item — confirm Clean Sheet does *not* fire.

**What this confirms:** Fluency Trap §4.1 Clean Sheet now fires (badge logic was complete but `item_results` was never passed).

> **Note — Trap Detector still inert.** The third behaviour badge (Trap Detector, ≥10 correct disputes at L0) requires the L0 Confirm/Dispute UI from A5b, which has not landed. `correct_disputes=0` is currently hardcoded in [api.py](../src/tompe/services/api.py).

### A5a — false annotation generator (inert until wired)

- [ ] **Import check.** From a Python shell:

  ```python
  from tompe.pipeline.false_annotation_generator import generate_false_annotations
  ```

  Should import without exception.

- [ ] **Rule-mode unit test.** Already run during sprint:

  ```python
  from tompe.pipeline.false_annotation_generator import generate_rule_false_annotations
  decoys = generate_rule_false_annotations(translation="...", excluded_ranges=[(20, 35)], n=2, seed=42)
  ```

  Returned 2 word-boundary-snapped non-overlapping decoys clear of the excluded range. ✓
- [ ] **LLM-mode test (manual, optional).** Requires API key + an `LLMClient`. Not run in sprint #1; blocked on A5a-wiring providing a real call site.

**What this does NOT yet confirm:** no exercise produces false annotations end-to-end. The generator is dead code until A5a-wiring lands.

### Cross-cutting smoke test (recommended after individual checks)

A single end-to-end student walkthrough that exercises A1 + A2 + A3:

- [ ] Log in as a student whose class has badges visible and one threshold override.
- [ ] Complete an L2 evaluation item perfectly → confirm Clean Sheet fires + threshold-override Bronze fires earlier than default.
- [ ] Switch to a PE exercise → confirm flow advances Annotate → Justify → Feedback with `edited_text` saved.
- [ ] My Progress reflects new badges, new XP, and override thresholds appear in the "next tier" tooltips.

---

## Implementation sprint #2 — Tier B (Group 3 quick wins + medium fixes)

**Date range:** 2026-05-10
**Theme:** Pipeline + error-injection wiring fixes; annotation-tool polish; spec-compliance plumbing for Group 3 specs.

### What landed

| ID | Item | Status | Files touched |
|---|---|---|---|
| B0 | YAML sourcing for severity distributions + CLI `--single-error` / `--production` flags (completes A4) | Done (smoke-tested) | [config.py](../experiments/pipeline_validation/config.py), [generate_batch.py](../experiments/pipeline_validation/generate_batch.py) |
| B1 | IoU threshold unified to 0.5 in `qe_validator._match_gemba_to_injected` (was 0.3) | Done (smoke-tested) | [src/tompe/pipeline/qe_validator.py](../src/tompe/pipeline/qe_validator.py) |
| B2 | UNPC dropped from `CORPORA` (data deleted, never re-ingested) | Done (smoke-tested) | [config.py:31-34](../experiments/pipeline_validation/config.py#L31-L34) |
| B3 | Animated annotation-tool timer (`.timer-display` ticks; resets on per-item buttons) | Done (smoke-tested) | [src/tompe/interfaces/annotation_app.py](../src/tompe/interfaces/annotation_app.py) |
| B4 | `is_likely_boundary` heuristic — header regex + short-s1 + content-word overlap | Done (unit-tested) | [src/tompe/pipeline/segment_selector.py](../src/tompe/pipeline/segment_selector.py) |
| B5 | `select_segments(tom_level=…)` + L3 helpers moved into `segment_selector` | Done (smoke-tested) | [src/tompe/pipeline/segment_selector.py](../src/tompe/pipeline/segment_selector.py), [generate_batch.py](../experiments/pipeline_validation/generate_batch.py) |
| B6 | Layer 2a / 2b explanation cache files committed; cache-first lookup wired into generators | Done (unit-tested) | [data/codebook/layer2a_explanations.json](../data/codebook/layer2a_explanations.json), [data/codebook/layer2b_explanations.json](../data/codebook/layer2b_explanations.json), [src/tompe/pipeline/explanation_generator.py](../src/tompe/pipeline/explanation_generator.py) |
| B7 | `track_c/build_annotation_set.py` end-to-end runner (batch → ablation → annotation_set.json) | Done (import-tested) | [experiments/pipeline_validation/track_c/build_annotation_set.py](../experiments/pipeline_validation/track_c/build_annotation_set.py) |
| B8 | Baseline segment reuse enforced (`forced_segment_ids` in `_baseline_sample`; B0 picks → B1/B2 reuse) | Done (unit-tested) | [experiments/pipeline_validation/track_c/prepare_annotation_set.py](../experiments/pipeline_validation/track_c/prepare_annotation_set.py) |
| B9 | Opt-in GEMBA gating (`verify_gemba=True` in `inject_errors_reference_based`); raises on detection<threshold | Done (signature-tested) | [src/tompe/pipeline/error_injector.py](../src/tompe/pipeline/error_injector.py) |

"Done (smoke-tested)" = imports + a smoke check passed. "Done (unit-tested)" = a small in-process test exercised the new behaviour. "Done (signature-tested)" = the new parameter exists; the QE-detection branch needs a real LLM run to verify.

### Resolved-stale audit claims (no work needed; verification only)

These appeared as gaps in the original 2026-05-09 audit but had already been addressed by prior work; sprint #2 confirmed them by reading the cited code:

- **`validation_severity_distribution` was already in YAML** ([settings.yaml:42-43](../config/settings.yaml#L42-L43)). The remaining gap was the Python constants not sourcing from it — closed by B0.
- **Tables 1–3 v3 explanation columns already emit** factual_accuracy / clarity / completeness ([tables.py:243](../experiments/pipeline_validation/tables.py#L243)). The audit's "needs spot-check" note is now resolved.

### Still pending — Phase 3 (research-scale)

Tracked separately. See "Phase 3 implementation plan" handoff: codebook coverage 8 → ~30 entries, `authentic_detector` implementation, `item_builder` orchestration, C1–C4 tagging ablation, Strategy 3 LLM context generation, false-positive analysis script.

---

## Verification checklist for sprint #2

Each item below maps to a Sprint #2 row. Run the listed command(s); for items that need a real LLM run, the manual step is called out.

### B0 — single-error YAML toggle + CLI flag

- [ ] **Constants source from YAML.** From the project root:
  ```bash
  PYTHONPATH=src python -c "from experiments.pipeline_validation.config import SEVERITY_DISTRIBUTION, VALIDATION_SEVERITY_DISTRIBUTION; print(SEVERITY_DISTRIBUTION); print(VALIDATION_SEVERITY_DISTRIBUTION)"
  ```
  Expect `{'minor': 1, 'major': 2, 'critical': 0}` and `{'major': 1}`.
- [ ] **YAML override is live.** Edit `config/settings.yaml` → `error_injection.validation_severity_distribution` to `{minor: 2}`, re-run the command above. The Python constant must reflect the change. Revert when done.
- [ ] **CLI flags are exposed.**
  ```bash
  PYTHONPATH=src python -m experiments.pipeline_validation.generate_batch --help
  ```
  Expect `--single-error` and `--production` (mutually exclusive) in the output.
- [ ] **Toggle propagates.** Run a small dry-run with `--limit 4 --production --dry-run`; logs should mention `n_errors > 1` somewhere (or the multi-error config); same with `--single-error --dry-run` should show 1 major.

**What this confirms:** Pipeline-validation §2.1 + Pipeline-remediation §2.3 — the validation-vs-production knob is now config-driven AND CLI-overridable.

### B1 — IoU threshold unified to 0.5

- [ ] **Module constant exists.**
  ```bash
  PYTHONPATH=src python -c "from tompe.pipeline.qe_validator import _GEMBA_IOU_THRESHOLD; print(_GEMBA_IOU_THRESHOLD)"
  ```
  Expect `0.5`.
- [ ] **No stray 0.3 in qe_validator.** `grep -n "0\.3" src/tompe/pipeline/qe_validator.py` should return no hits.
- [ ] **Note: scoring/feedback IoU is intentionally 0.3** (lenient student grading, separate design). Don't "fix" those.

**What this confirms:** Pipeline-validation §3 A2 — qe_validator now agrees with `IOU_THRESHOLD = 0.5` in `experiments/pipeline_validation/config.py` and Track A2's matcher.

### B2 — UNPC dropped from CORPORA

- [ ] **Config no longer lists UNPC.**
  ```bash
  PYTHONPATH=src python -c "from experiments.pipeline_validation.config import CORPORA; print(CORPORA)"
  ```
  Expect `['europarl', 'dgt_tm', 'eurlex']`.
- [ ] **No segment-loader regression.** Run the dry-run pipeline and confirm `Total segments loaded: ~29900` (3 corpora × ~10K each):
  ```bash
  PYTHONPATH=src python -m experiments.pipeline_validation.generate_batch --dry-run --limit 50
  ```

**What this confirms:** Remediation §6 Option B — UNPC removed pending re-ingestion. The empty `data/corpora/unpc/` directory is preserved as a placeholder.

### B3 — animated annotation timer

**This one needs a browser.**

- [ ] **Launch the annotation tool.**
  ```bash
  PYTHONPATH=src python -m tompe.interfaces.annotation_app
  ```
  (Note: there's a pre-existing `Column.select` AttributeError under Gradio 6 — unrelated to B3, tracked under annotation §2.7. Workaround: comment out the `done_view.select(...)` line if you hit it in this session.)
- [ ] **Phase A timer ticks.** Open `http://localhost:7861`, log in, start Phase A. The top-right timer should advance from `00:00` upward in real time.
- [ ] **Per-item reset.** Click "Submit & Next" — the timer resets to `00:00` and starts ticking again for the new item.
- [ ] **"No Errors Found" also resets.** Same expectation.
- [ ] **Phase B timer ticks too.** Complete Phase A → reach Phase B → confirm `00:00` → ticks → resets on submit.
- [ ] **Server-side timestamps unaffected.** Inspect a saved annotation JSON — `timestamp_start`, `timestamp_end`, `duration_seconds` should be present and match the wall-clock duration.

**What this confirms:** Annotation §2.4 — the visible timer no longer lies.

### B4 — `is_likely_boundary` heuristic

- [ ] **Unit-test the heuristic.**
  ```bash
  PYTHONPATH=src python -c "
  from tompe.pipeline.segment_selector import _is_likely_boundary
  assert _is_likely_boundary('ANNEX I', 'The Commission shall regulate.')
  assert _is_likely_boundary('Yes.', 'The full second sentence elaborates.')
  assert _is_likely_boundary('Heavy machinery requires lubrication.', 'Concerts attract enthusiastic audiences nightly.')
  assert not _is_likely_boundary('The new regulation introduces stricter limits.', 'This regulation shall apply to all member states.')
  print('OK')
  "
  ```
  Expect `OK`.
- [ ] **Reject-rate visible in logs.** Run `--dry-run --limit 100`; the L3 Strategy 2 log line should now include `rejected N for header/short/no-overlap` with N>0.

**What this confirms:** Remediation §1.4 Strategy 2 — header / short / no-overlap rejection is live; spaCy was avoided in favour of a stopword-filtered content-word heuristic.

### B5 — `select_segments(tom_level=…)`

- [ ] **Token window relaxes for L3.**
  ```bash
  PYTHONPATH=src python -c "
  from tompe.pipeline.segment_selector import select_segments
  from tompe.schemas.enums import TOMLevel
  default = select_segments(n_segments=20)
  l3 = select_segments(n_segments=20, tom_level=TOMLevel.RECURSIVE_MULTI)
  print('default tok lengths:', sorted(len(s.source_text.split()) for s in default))
  print('L3 tok lengths:', sorted(len(s.source_text.split()) for s in l3))
  "
  ```
  Default should stay in the 10–50 window; L3 should sit in 30–150.
- [ ] **L3 helpers importable from `segment_selector` (not generate_batch).**
  ```bash
  PYTHONPATH=src python -c "from tompe.pipeline.segment_selector import select_l3_long_segments, select_l3_adjacent_pairs; print('OK')"
  ```
- [ ] **`document_id` / `position_in_doc` preserved through `select_segments`.** Inspect any returned `CorpusSegment` — those fields should be populated when present in the source JSONL.

**What this confirms:** Remediation §1.4 — L3 selection is in the pipeline package, not the experiments folder; token windows are tom-level-aware.

### B6 — Layer 2a / 2b explanation cache

- [ ] **Cache files exist and parse.**
  ```bash
  PYTHONPATH=src python -c "
  from tompe.pipeline.explanation_generator import _load_explanation_cache, _LAYER2A_CACHE_PATH, _LAYER2B_CACHE_PATH
  print('2a entries:', len(_load_explanation_cache(str(_LAYER2A_CACHE_PATH))))
  print('2b entries:', len(_load_explanation_cache(str(_LAYER2B_CACHE_PATH))))
  "
  ```
  Each should report ≥2 (the seed entries: `false_cognate`, `agreement_gender`).
- [ ] **Cache-hit skips LLM.** Run the per-error generator with a known cached `(primary_tag, error_type)` and an obviously-broken `llm_config`. The function should still return without raising:
  ```bash
  PYTHONPATH=src python -c "
  import asyncio
  from tompe.schemas.error import InjectedError, ContrastiveExplanation
  from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel, SkillID
  from tompe.pipeline.explanation_generator import generate_layer2a_explanation
  err = InjectedError(error_id='t', primary_tag=PrimaryTag.MISTRANSLATION, error_type='false_cognate', severity=Severity.MAJOR, tom_level=TOMLevel.FIRST_ORDER_MACHINE, primary_skill=SkillID.S1, secondary_skills=[], direction='en_fr', original_text='actually', injected_text='actuellement', span_start=0, span_end=10, explanation=ContrastiveExplanation(mt_interpretation='x', actual_meaning='y', reader_impact='z', correction_rationale='w'), brief_explanation='t')
  out = asyncio.run(generate_layer2a_explanation(err, 'google_translate', {'provider':'broken','model':'x'}))
  print('Layer2a cache hit OK:', out.error_mechanism[:60])
  "
  ```
- [ ] **Cache-miss falls back to LLM (manual, optional).** Replace `error_type='false_cognate'` with a non-cached value (e.g. `'word_sense'`) and re-run with a real LLM config. Should produce a fresh LLM-generated `SystemBehaviorExplanation`.

**What this confirms:** Error-injection §5.4 — Layer 2a/2b template reuse is now a real feature, not "regenerated each time".

### B7 — `build_annotation_set.py` runner

- [ ] **Module imports + CLI exposed.**
  ```bash
  PYTHONPATH=src python -m experiments.pipeline_validation.track_c.build_annotation_set --help
  ```
  Expect `--skip-baselines` and `--seed` flags.
- [ ] **Skip-baselines path works without LLM.** This requires `experiments/pipeline_validation/results/batch_200.jsonl` to exist:
  ```bash
  PYTHONPATH=src python -m experiments.pipeline_validation.track_c.build_annotation_set --skip-baselines
  ```
  Expect `data/annotations/annotation_set.json` to be written. (Will not include baseline conditions.)
- [ ] **Full path with baselines (manual, costs LLM credits).** Drop `--skip-baselines`; this runs B1/B2 on 60 segments. Confirms the full B0/B1/B2 + clean partition lands in the annotation set.

**What this confirms:** Annotation §4.1 — there is now a "generate → prepare → load" path; teachers no longer need to assemble inputs by hand. The actual `data/annotations/annotation_set.json` is generated, not committed.

### B8 — segment reuse across baselines

- [ ] **`forced_segment_ids` is honoured.**
  ```bash
  PYTHONPATH=src python -c "
  import random
  from types import SimpleNamespace
  from tompe.schemas.enums import TOMLevel
  from experiments.pipeline_validation.track_c.prepare_annotation_set import _baseline_sample
  def m(seg, tom, iid): return SimpleNamespace(item_id=iid, segment_id=seg, metadata=SimpleNamespace(tom_profile={tom:1}))
  pool = [m(f'seg_{i}', TOMLevel.FIRST_ORDER_MACHINE, f'b1_{i}') for i in range(10)]
  forced = [f'seg_{i}' for i in range(6)]
  out = _baseline_sample(pool, random.Random(42), forced_segment_ids=forced)
  assert [it.segment_id for it in out] == forced, [it.segment_id for it in out]
  print('OK')
  "
  ```
  Expect `OK`. The B1/B2 picks line up with B0's segment_ids.
- [ ] **Missing-segment fallback warns.** Use a partial pool (only some forced ids present); confirm the WARNING log line `Baseline reuse: N/M forced segment IDs missing in pool` and that the function returns a best-effort selection.
- [ ] **End-to-end (after B7).** After running `build_annotation_set.py` end-to-end, inspect the resulting `annotation_set.json`:
  ```bash
  jq '[.[] | select(.condition | startswith("baseline_"))] | group_by(.segment_id // (.item_id|sub("^[BR]\\d_"; ""))) | map({k: .[0].item_id, n: length})' data/annotations/annotation_set.json
  ```
  Each group should have count 3 (B0+B1+B2 sharing one source segment).

**What this confirms:** Annotation §4.2 — within-segment comparison across baseline conditions is finally possible.

### B9 — opt-in GEMBA gating

- [ ] **Signature exposes the new params.**
  ```bash
  PYTHONPATH=src python -c "
  import inspect
  from tompe.pipeline.error_injector import inject_errors_reference_based
  sig = inspect.signature(inject_errors_reference_based)
  for p in ('verify_gemba', 'gemba_llm_config', 'gemba_min_detection_rate'):
      assert p in sig.parameters, p
  print('OK; defaults:', sig.parameters['verify_gemba'].default, sig.parameters['gemba_min_detection_rate'].default)
  "
  ```
  Expect `OK; defaults: False 0.5`.
- [ ] **Default behaviour unchanged.** A `--limit 4` run without any extra args should produce the same items as before B9 (`verify_gemba=False`).
- [ ] **Opt-in gating triggers (manual, costs LLM credits).** Programmatically call `inject_errors_reference_based(..., verify_gemba=True, gemba_min_detection_rate=0.99)` on a known-injection-prone segment. Expect either a successful return or a `ValueError: GEMBA-MQM gating failed for segment <id>: detection_rate=…`.
- [ ] **Failed-gate path retried by caller.** With `verify_gemba=True`, the existing `try/except` in `generate_batch._generate_one_item` should drop the failing item rather than crash the batch. Confirm by running `--limit 20 --single-error` (after wiring `verify_gemba=True` in the call site if you want to test gating on a real batch).

**What this confirms:** Error-injection §2.4 — GEMBA detection is now a real gate (opt-in), not just a separate post-hoc batch pass.

### Cross-cutting smoke test for sprint #2

A single command exercising B0 + B2 + B4 + B5:

```bash
PYTHONPATH=src python -m experiments.pipeline_validation.generate_batch --dry-run --limit 60 --single-error
```

Expect:
- Total segments loaded ≈ 29 900 (B2 — UNPC excluded)
- L3 Strategy 1 picks long segments (30–150 tokens)
- L3 Strategy 2 logs `rejected N for header/short/no-overlap` (B4)
- Severity distribution: 1 major / item (B0)
- No tracebacks; the same items would be produced without `--dry-run`.

---

## Deliberate scope decisions (not gaps)

The following items might look like gaps in the per-spec tables but are **intentional design choices**. Do not address as part of "fix the gaps":

- **xCOMET-XL deferred (GPU requirement).** The pipeline uses GEMBA-MQM as the sole QE check. The Track A xCOMET module exists but is not invoked by default; `XCOMET_MODEL` in `experiments/pipeline_validation/config.py` deliberately points at `Unbabel/wmt22-comet-da`. Revisit only if a GPU host becomes available. Affected rows: System §4.6, Validation §3 A3, Error Injection §2.4.
- **Two study managers, by design.** `teacher_app.py` study tab targets **translation-student studies** (the main pedagogical-platform audience). `study/study_manager.py` targets **broader-public studies** with simpler enrollment and no L0–L3 progression. Different config schemas are correct. Affected row: Study Interface §4.

## Cross-spec synthesis

### Most blocking gaps (across all specs)

Ordered by impact × leverage. Each item references the per-spec entries that surfaced it.

1. ~~**Post-editing flow is broken end-to-end.**~~ **RESOLVED — Sprint #1 (A1).** `pe_proceed_btn` now wired; `edited_text` flows to scoring. Diff visualization is a separate, lower-priority gap.
2. **Comparison mode (L3 multi-MT, ranking, human-vs-MT) is schema-only.** `comparison_outputs`, `ComparisonType`, `ItemPathway` exist but no pipeline writes them, no UI reads them, no scoring evaluates them. The single biggest scope gap; spans System §3.6/§5/§7.4 + UI §3.5.
3. **Skill Radar is rendered but inert.** The student UI draws the heptagonal SVG and the teacher heatmap exists, but [`api_get_progress`](../src/tompe/services/api.py#L780) never returns `skill_profile`, so every student sees zeros. Highest "looks done but isn't" risk for an EC-TEL demo. *(Fluency Trap §6.2 + System §3.9)* — **Tier B target.**
4. **Authentic pathway is a stub.** [`authentic_detector.detect_authentic_errors`](../src/tompe/pipeline/authentic_detector.py#L11) raises `NotImplementedError`. This invalidates the controlled-vs-authentic narrative the paper needs. Cascades into Study spec authentic items, Error Injection §7.2, validation Track C naturalness. *(System §4.5 + Error Injection §7.2 + annotation-tool §4.3)* — **Tier C3.**
5. **Longitudinal analytics are all `NotImplementedError`.** [`analytics.py`](../src/tompe/services/analytics.py#L6) — `update_student_profile`, `detect_blind_spots`, `compute_class_analytics` — are stubs. The teacher blind-spot view recomputes ad hoc; there's no persistent learner profile for the BKT story. *(System §3.9)* — **Tier C2.**
6. **BKT mastery + teacher-gated progression is unwired.** [`progression.py:20`](../src/tompe/services/progression.py#L20) is a stub; Scout / Analyst / Expert badges fire on level-int, not on p≥0.98. Spec promises adaptive progression; runtime delivers manual promotion. *(Fluency Trap §2.2 + System §8.3)* — **Tier C1.**
7. ~~**Single-error validation toggle is not config-driven.**~~ **RESOLVED — Sprint #1 (A4).** `validation_severity_distribution` lives in `settings.yaml`; user/linter further refactored to load from YAML at module-import time.
8. **Behaviour badges never fire.** *Partially resolved — Sprint #1 (A2):* Clean Sheet now fires (per-item `item_results` plumbed). **Trap Detector still inert** until L0 Confirm/Dispute UI lands (A5b/c/d in progress).

### Patterns

- **Schemas land before runtime.** Pydantic models exist for many features whose consumers do not: `comparison_outputs`, `BlindSpot`, `StudentProfile`, `JustificationScore`, `clean_spans`, `include_multi_system`, `badge_threshold_overrides`, `badges_visible`, `is_practice`, `correct_disputes`, `ANNOTATION_AUTHENTIC` slot. The data model is more mature than the runtime path — typical mid-build state, but means "field exists" ≠ "feature works".
- **Teacher analytics ahead of student analytics.** Teacher dashboard has heatmap, individual student, blind-spot views; student dashboard is missing XP timeline, badge timeline, and the radar has no data source. Mirror the teacher view back to the student.
- **v3 specs partially adopted in code.** Codebook adds R1–R5 (good), but `config.SEVERITY_DISTRIBUTION` and `settings.yaml` still encode v2 numbers; xCOMET model name is wrong; IoU threshold drifts between modules (0.3 vs 0.5).
- **Pedagogical flourish missing while core flow works.** Tooltips with date earned, animated timer, locked-silhouette PNGs, first-session tutorial, "Show all" toggle — these are demo polish that won't block submission but will hurt the demo.
- **Stub modules are well-named.** `authentic_detector.py`, `item_builder.py`, `analytics.py`, `progression.py` are all `NotImplementedError`. They are explicit promissory notes; the question is which ones the paper actually needs filled.
- **Two-app duplication is creeping in.** Study management exists in both teacher_app and standalone study_manager; annotation_set composition lives in `prepare_annotation_set.py` but the consumed file is uncommitted; level scaffolding lives in `student_app.py` but the spec also implies a `Level Configuration` page.

### What's most solid

- **Error injection pipeline.** Two-step LLM (plan → execute), full XML verification with parse / diff / tag / sev / tom / explanation checks, retry queue at 3 attempts. Matches Error Injection Spec §1–2 closely. *(See [pipeline/error_injector.py](../src/tompe/pipeline/error_injector.py))*
- **Three-track validation suite.** Tracks A (structural + GEMBA + xCOMET), B (B0 / B1 / B2 baselines), C (3-way agreement + Cochran-Armitage trend + naturalness + explanation quality) — all wired with stats. Track C even has the v3 explanation-quality module. *(See [experiments/pipeline_validation/run_all.py](../experiments/pipeline_validation/run_all.py))*
- **Student core loop.** Annotate → Justify → Feedback with cognitive forcing (Justify gates Feedback) is implemented for L0 / L1 / L2. Span selector, pill-button classification, severity radio, three-layer feedback cards all work. *(See [interfaces/student_app.py:824](../src/tompe/interfaces/student_app.py#L824))*
- **Teacher review queue + class analytics.** Approve / Reject / Save-Reviewed flow, per-error editing, MQM × ToM heatmap, individual + class views. *(See [interfaces/teacher_app.py:592](../src/tompe/interfaces/teacher_app.py#L592))*
- **Annotation tool (expert MQM).** Two phases, ten MQM categories, severity, "no errors" path, confidence rating, Phase A → B transition, factual / clarity / completeness ratings, per-item JSON persistence. *(See [interfaces/annotation_app.py](../src/tompe/interfaces/annotation_app.py))*
- **Codebook L3 remediation.** R1–R5 entries (anaphora, discourse connective, tense sequence, lexical cohesion, information packaging) all committed with `tom_level=recursive` + `skill=S7`; long-segment + adjacency-pair selection wired. *(See [data/codebook/error_codebook_fr_en.json:135](../data/codebook/error_codebook_fr_en.json#L135))*
- **Study pilot interface.** Consent → segments → questionnaire → thank-you, anonymous hash IDs, pseudo-random ordering with constraint on consecutive levels, Form A/B counterbalancing, response auto-save. RGPD-aware. Ready to run a pilot. *(See [study/study_app.py](../study/study_app.py))*

**One-line read:** The pipeline backbone and the student exercise loop are paper-ready; the gaps are concentrated in (a) the "comparison mode" branch of the spec, (b) longitudinal analytics + BKT progression, (c) inert UI surfaces with no data source, and (d) one user-visible PE-flow bug. Items 1, 3, and 9 are weekend-scale fixes; items 2, 4, 5, 6 are scope decisions.

---

## Group 1 — Core system + UI

### ToM-PE_System_Specification_v02.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §2.3 | Directory structure (config/, pipeline/, services/, interfaces/, schemas/) | Implemented | [src/tompe/](../src/tompe/) | Module layout matches spec. |
| §3.1–3.2 | `CorpusSegment` + `MTOutput` models | Implemented | [schemas/corpus.py:9](../src/tompe/schemas/corpus.py#L9), [:28](../src/tompe/schemas/corpus.py#L28) | Pydantic models present and used in pipeline. |
| §3.3 | `InjectedError` manifest with Layer 1 + Layer 2 explanations | Implemented | [schemas/error.py:47](../src/tompe/schemas/error.py#L47), [:13](../src/tompe/schemas/error.py#L13), [:22](../src/tompe/schemas/error.py#L22) | Plus Layer 2b `TechnicalExplanation` (extension). |
| §3.4 | `AnnotationLevel` + `ErrorAnnotation` + `AnnotationConfig` | Partial | [schemas/annotation.py:32](../src/tompe/schemas/annotation.py#L32), [schemas/enums.py:61](../src/tompe/schemas/enums.py#L61) | Schema complete; spec name "GUIDED/INDEPENDENT" renamed to "scout/analyst". |
| §3.5 | Dual pathway (controlled / authentic) | Partial | [schemas/enums.py:70](../src/tompe/schemas/enums.py#L70), [pipeline/authentic_detector.py:27](../src/tompe/pipeline/authentic_detector.py#L27) | Enum + model exist; `authentic_detector` raises `NotImplementedError`. |
| §3.6 | `AssessmentItem` with `comparison_outputs` / `comparison_type` | Partial | [schemas/item.py:34](../src/tompe/schemas/item.py#L34), [:58](../src/tompe/schemas/item.py#L58) | Schema fields exist; no pipeline or UI populates `comparison_outputs`. |
| §3.7 | `StudentResponse` (eval / PE / navigator / comparison modes) | Partial | [schemas/response.py:72](../src/tompe/schemas/response.py#L72) | Schema covers all 4 modes; runtime only persists eval + PE ([api.py:614](../src/tompe/services/api.py#L614)). |
| §3.8 | `ScoringResult` with HTER + per-MQM/ToM breakdowns | Implemented | [schemas/scoring.py:22](../src/tompe/schemas/scoring.py#L22), [services/scoring.py:50](../src/tompe/services/scoring.py#L50) | Full scoring engine for eval, PE, navigator. |
| §3.9 | `StudentProfile` + `BlindSpot` longitudinal model | Partial | [schemas/scoring.py:56](../src/tompe/schemas/scoring.py#L56), [services/analytics.py:6](../src/tompe/services/analytics.py#L6) | Schemas defined; `analytics.py` functions all `NotImplementedError`. |
| §4.1 | `segment_selector` (length, dedup, register) | Implemented | [pipeline/segment_selector.py:73](../src/tompe/pipeline/segment_selector.py#L73), [:50](../src/tompe/pipeline/segment_selector.py#L50) | Length + Jaccard dedup; register from corpus, no IATE-driven scoring. |
| §4.2 | `mt_generator` (Google, DeepL, LLM) | Partial | [pipeline/mt_generator.py:35](../src/tompe/pipeline/mt_generator.py#L35), [:76](../src/tompe/pipeline/mt_generator.py#L76) | Google + DeepL + LLM-as-translator; no NLLB; no BLEU/COMET computed. |
| §4.3 | Reference-based MQM-guided error injection | Implemented | [pipeline/error_injector.py:1](../src/tompe/pipeline/error_injector.py#L1), [pipeline/_injection_prompts.py](../src/tompe/pipeline/_injection_prompts.py) | Two-step LLM injection with XML verification per spec v1.1. |
| §4.4 | Layer 1 contrastive + Layer 2 system-behavior explanations | Implemented | [pipeline/explanation_generator.py:39](../src/tompe/pipeline/explanation_generator.py#L39) | Layer 1, 2a, 2b generators wired. |
| §4.5 | Authentic error detection (xCOMET + GEMBA cross-validation) | Missing | — | `authentic_detector.py:27` is a stub. |
| §4.6 | QE validation (xCOMET + GEMBA, ≥80% detection threshold) | Implemented | [pipeline/qe_validator.py:1](../src/tompe/pipeline/qe_validator.py#L1) | GEMBA-MQM only by design; xCOMET deferred (GPU). |
| §5 (Gradio) | Student app with Annotate→Justify→Feedback flow | Implemented | [interfaces/student_app.py:824](../src/tompe/interfaces/student_app.py#L824) | 3-phase Tabs UI, span selector, classification, feedback cards. |
| §5 / §3.7 | Comparison mode (Skill A indep eval / Skill B ranking) | Missing | — | No comparison UI; no rankings; no PE-worthiness verdict. |
| §5.2 | Student dashboard (radar, history, over-editing trend) | Partial | [student_app.py:1735](../src/tompe/interfaces/student_app.py#L1735), [:455](../src/tompe/interfaces/student_app.py#L455) | Skill radar + recent scores; no over-editing / FP trend chart. |
| §6.2 | Teacher item review queue (approve/reject/edit) | Implemented | [teacher_app.py:592](../src/tompe/interfaces/teacher_app.py#L592), [:634](../src/tompe/interfaces/teacher_app.py#L634) | Two-column layout, error-card editing, status transitions. |
| §6.3 | Exercise builder (level, justification, ordering) | Partial | [teacher_app.py:1094](../src/tompe/interfaces/teacher_app.py#L1094) | Manual selection + assignment; no AI-suggested-from-blind-spots flow. |
| §6.4 | Class Overview + Individual Student + Blind Spot views | Implemented | [teacher_app.py:1464](../src/tompe/interfaces/teacher_app.py#L1464), [:1858](../src/tompe/interfaces/teacher_app.py#L1858) | All three analytics tabs with charts + heatmap. |
| §7.1–7.4 | Scoring (IoU eval / HTER PE / Navigator) | Partial | [services/scoring.py:50](../src/tompe/services/scoring.py#L50), [:170](../src/tompe/services/scoring.py#L170), [:227](../src/tompe/services/scoring.py#L227) | Eval, PE, navigator scoring done; comparison-mode scoring (§7.4) absent. |
| §7.5 | LLM-based justification quality scoring | Missing | — | `JustificationScore` schema exists ([scoring.py:16](../src/tompe/schemas/scoring.py#L16)); no scorer. |
| §7.6 | Cognitive forcing protocol (justification before feedback) | Implemented | [services/feedback.py:16](../src/tompe/services/feedback.py#L16), [interfaces/student_app.py:824](../src/tompe/interfaces/student_app.py#L824) | Phase tabs gate Feedback behind Justification submission. |
| §8.2 | Teacher-controlled progression with recommendations | Partial | [teacher_app.py:1830](../src/tompe/interfaces/teacher_app.py#L1830), [services/progression.py:11](../src/tompe/services/progression.py#L11) | UI shows promote button at F1≥0.8; `recommend_next_level` is `NotImplemented`. |
| §8.3 | Adaptive progression (BKT mastery thresholds) | Missing | — | Mastery threshold constants exist ([competency.py:119](../src/tompe/schemas/competency.py#L119)); no BKT tracker. |
| §9 | Multi-tenancy fields (`teacher_id`, `class_id`) | Partial | [schemas/session.py:31](../src/tompe/schemas/session.py#L31), [:50](../src/tompe/schemas/session.py#L50) | `class_id` present; `teacher_id` defaulted; no multi-teacher auth. |
| §11 | FastAPI service layer wired up | Implemented | [services/api.py:175](../src/tompe/services/api.py#L175) | All major endpoint groups (auth, items, exercises, responses, feedback, analytics). |

#### Top 5 gaps

1. **Comparison mode end-to-end** (Skill A independent eval + Skill B ranking + PE-worthiness verdict): missing in pipeline, student app, scoring, and analytics — schema-only.
2. **`analytics.py` longitudinal functions** (`update_student_profile`, `detect_blind_spots`, `compute_class_analytics`) are all `NotImplementedError`; current blind-spot view recomputes everything ad hoc.
3. **Authentic error-detection pipeline** (`authentic_detector.py`) is a stub — only the controlled pathway runs end-to-end.
4. **LLM-based justification quality scoring (§7.5)** absent: `JustificationScore` schema unused, no scorer, no surface / partial / deep ratings shown.
5. **xCOMET-XL validation (§4.6)** skipped; QE relies on GEMBA-MQM alone, weakening the dual quality gate.

---

### ToM-PE_UI_Specification_v1.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §1.2 | Two-app deployment with shared FastAPI backend | Implemented | [services/api.py:57](../src/tompe/services/api.py#L57), [interfaces/student_app.py](../src/tompe/interfaces/student_app.py), [interfaces/teacher_app.py](../src/tompe/interfaces/teacher_app.py) | Gradio student + Streamlit teacher + FastAPI per spec. |
| §1.3 | One-click launch script (`./launch.sh`) | Partial | [teacher_app.py:2535](../src/tompe/interfaces/teacher_app.py#L2535) | No shell script; teacher app has Launch Controls subprocess buttons instead. |
| §2.1 | Student auth (login + token + session) | Implemented | [services/auth.py:152](../src/tompe/services/auth.py#L152), [student_app.py:710](../src/tompe/interfaces/student_app.py#L710) | bcrypt + bearer tokens; consent flow added on top. |
| §2.3 | `StudentAccount` + `ClassGroup` data models | Implemented | [schemas/session.py:31](../src/tompe/schemas/session.py#L31), [:50](../src/tompe/schemas/session.py#L50) | Includes `current_level`, `allowed_levels`, plus added `consent` field. |
| §3.1 | Student global nav (Exercises + My Progress) | Implemented | [student_app.py:772](../src/tompe/interfaces/student_app.py#L772) | Two tabs as per spec. |
| §3.2 | Exercise list view with status, level, mode | Implemented | [student_app.py:774](../src/tompe/interfaces/student_app.py#L774), [:89](../src/tompe/interfaces/student_app.py#L89) | Cards with level / mode / items / status badges. |
| §3.3.1 | Common item layout (source, translation, IATE glossary) | Partial | [student_app.py:803](../src/tompe/interfaces/student_app.py#L803) | Source+translation done; no IATE glossary panel; no progress bar. |
| §3.3.2 | Level-specific task descriptions (L0–L3, eval+PE+compare) | Partial | [student_app.py:1155](../src/tompe/interfaces/student_app.py#L1155) | L0/L1/L2/L3 eval + PE descriptions present; no L3 comparison description. |
| §3.3.3 | Error Types Guide collapsible panel | Implemented | [student_app.py:828](../src/tompe/interfaces/student_app.py#L828), [:50](../src/tompe/interfaces/student_app.py#L50) | Accordion with definitions and examples; no per-entry "How It Works" expander. |
| §3.3.4 / L0 | Navigator confirm/dispute buttons + false annotations | Partial | [student_app.py:1192](../src/tompe/interfaces/student_app.py#L1192), [pipeline/false_annotation_generator.py](../src/tompe/pipeline/false_annotation_generator.py) | Sprint #1 (A5a): false annotation generator landed (LLM + rule + manual modes); Confirm/Dispute UI + scoring + counter still pending (A5b/c/d). |
| §3.3.4 / L1 | Guided region hints + within-region span selection | Partial | [student_app.py:1213](../src/tompe/interfaces/student_app.py#L1213) | Yellow region highlights drawn; same span selector as L2 (no in-region constraint). |
| §3.3.4 / L2 | Independent click-drag span selection + classification | Implemented | [student_app.py:813](../src/tompe/interfaces/student_app.py#L813), [components/span_selector.py:1](../src/tompe/interfaces/components/span_selector.py#L1) | Custom span selector + pill-button classification. |
| §3.3.4 / L3 | Expert clean spans + "no errors" option + comparison view | Partial | [student_app.py:1227](../src/tompe/interfaces/student_app.py#L1227) | Warning text only; no clean-segment ratio applied; no comparison UI; no human-vs-MT discrimination. |
| §3.3.4 ② | Justification Mode A (free-text) + Mode B (3-field structured) | Implemented | [student_app.py:901](../src/tompe/interfaces/student_app.py#L901), [:913](../src/tompe/interfaces/student_app.py#L913), [:930](../src/tompe/interfaces/student_app.py#L930) | Mode A (global free), per-error short, per-error structured all wired. |
| §3.3.4 ③ | Feedback summary + Layer 1 + Layer 2a/2b cards | Implemented | [services/feedback.py:107](../src/tompe/services/feedback.py#L107), [:134](../src/tompe/services/feedback.py#L134), [interfaces/student_app.py:153](../src/tompe/interfaces/student_app.py#L153) | All three layers + student justification echoed first. |
| §3.3.5 | First-session tutorial overlay | Missing | — | No tutorial in `student_app.py`. |
| §3.3.6 | Color-coded pill button classification | Implemented | [student_app.py:846](../src/tompe/interfaces/student_app.py#L846), [components/colors.py](../src/tompe/interfaces/components/colors.py) | Pill buttons with coloured dots per category, severity radio. |
| §3.3.7 | Colorblind-safe palette + tag-color mapping | Implemented | [components/colors.py](../src/tompe/interfaces/components/colors.py) | `TAG_COLORS` used across student & teacher UIs. |
| §3.4 | Post-editing mode with diff + change list | Partial | [student_app.py:975](../src/tompe/interfaces/student_app.py#L975), [:983](../src/tompe/interfaces/student_app.py#L983) | Sprint #1 (A1): submission flow now wired (`pe_proceed_btn` advances; `edited_text` reaches API). Diff visualization (`pe_changes_html`) + per-edit change list still missing. |
| §3.5 | L3 Comparison view (multi-MT, ranking, human-MT discrimination) | Missing | — | No comparison UI; `ItemPathway` / `comparison_outputs` unused at runtime. |
| §3.6 | My Progress dashboard (radar, by error type, recent sessions) | Partial | [student_app.py:1735](../src/tompe/interfaces/student_app.py#L1735), [:455](../src/tompe/interfaces/student_app.py#L455) | Skill radar + summary cards + recent sessions; no over-editing trend. |
| §4.2.1 | Browse Corpus filters + selection | Implemented | [teacher_app.py:149](../src/tompe/interfaces/teacher_app.py#L149) | Sources, domain, direction, register, length, search; checkbox selection. |
| §4.2.2 | Upload Corpus (TMX/TSV) | Missing | [teacher_app.py:272](../src/tompe/interfaces/teacher_app.py#L272) | Page exists but ingestion is "feature coming in v2". |
| §4.2.3 | Generate Translations (multi-MT, manual edit, base-for-injection) | Partial | [teacher_app.py:282](../src/tompe/interfaces/teacher_app.py#L282) | Multi-MT + LLM + injection trigger; no per-row Edit + no base-selection radio. |
| §4.3 | Review Queue with detail editing + Approve/Reject/Regenerate | Partial | [teacher_app.py:592](../src/tompe/interfaces/teacher_app.py#L592), [:634](../src/tompe/interfaces/teacher_app.py#L634) | Approve / Reject / Save-Reviewed; no Regenerate; no batch operations. |
| §4.4 | Exercise Builder (level, justification, ordering, clean ratio) | Partial | [teacher_app.py:1094](../src/tompe/interfaces/teacher_app.py#L1094) | Manual selection + config; no AI-suggested-from-blind-spots top section. |
| §4.5.1 | Student Accounts table + bulk CSV import | Implemented | [teacher_app.py:1272](../src/tompe/interfaces/teacher_app.py#L1272), [:1289](../src/tompe/interfaces/teacher_app.py#L1289) | Add / import / level dropdown / class-move per spec. |
| §4.5.2 | Level Configuration page with mastery thresholds | Missing | — | No dedicated Level Configuration page; per-student promote button on analytics page only. |
| §4.6 | Analytics: Class Overview + Individual + Blind Spot heatmap | Implemented | [teacher_app.py:1464](../src/tompe/interfaces/teacher_app.py#L1464), [:1858](../src/tompe/interfaces/teacher_app.py#L1858) | All three analytics tabs + MQM × ToM heatmap with detection rates. |
| §4.7.1 | API Credentials page with show/hide + test connection | Partial | [teacher_app.py:2634](../src/tompe/interfaces/teacher_app.py#L2634) | Lists providers + env-var status; Test Connection is a stub ("v2"). |
| §4.7.2 | System Configuration + share-link + data export | Partial | [teacher_app.py:2535](../src/tompe/interfaces/teacher_app.py#L2535), [:2696](../src/tompe/interfaces/teacher_app.py#L2696) | Launch Controls + system tabs; no "Export All Data ZIP" or backup. |
| §6 | Critical-path P0/P1 components (FastAPI, span selector, L2 flow) | Implemented | [services/api.py](../src/tompe/services/api.py), [components/span_selector.py](../src/tompe/interfaces/components/span_selector.py), [student_app.py](../src/tompe/interfaces/student_app.py) | All P0+P1 priorities present. |

#### Top 5 gaps

1. **PE flow stops at the textarea**: `pe_proceed_btn` ([student_app.py:983](../src/tompe/interfaces/student_app.py#L983)) has no event handler, so PE submissions never advance — user-visible blocker.
2. **L3 Comparison view (multi-MT side-by-side, ranking, human-vs-MT) entirely absent** — single biggest missing student feature.
3. **L0 Navigator interaction is decorative only**: no Confirm / Dispute buttons per annotation, no false-annotation injector at item-build time.
4. **Corpus upload (TMX/TSV) is non-functional** ("v2" placeholder), forcing teachers to drop files into the filesystem manually.
5. **No Level Configuration page (§4.5.2) and no AI-suggested exercises (§4.4)** — the "Generate targeted exercise" loop from blind spots back to exercise builder is not wired.

---

### ToM-PE_Study_Interface_Spec_v1.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §1.3 | File structure (`study/study_app.py`, `segments/`, `responses/`, `exports/`) | Implemented | [study/study_app.py](../study/study_app.py), [study/segments/ectel2026_pilot.json](../study/segments/ectel2026_pilot.json), [study/responses/](../study/responses/), [study/exports/](../study/exports/) | Layout matches spec. |
| §2.1 | `study_config.json` schema (consent, post-task questions, dates) | Implemented | [study/study_config.json:1](../study/study_config.json#L1) | All required fields present. |
| §2.2 | Segment file format with `form_variant` for L2 | Partial | [study/segments/ectel2026_pilot.json](../study/segments/ectel2026_pilot.json) | File exists; parsed correctly by `_resolve_target_text` ([study_app.py:104](../study/study_app.py#L104)). |
| §3.1 | Linear flow (Consent → Segments → Questionnaire → Thank You) | Implemented | [study/study_app.py:194](../study/study_app.py#L194), [:226](../study/study_app.py#L226), [:273](../study/study_app.py#L273), [:308](../study/study_app.py#L308) | Four screens, no back navigation. |
| §3.2 / Consent | Consent + decline screens | Implemented | [study/study_app.py:218](../study/study_app.py#L218), [:222](../study/study_app.py#L222) | Consent button generates anonymous UUID hash; decline screen shown. |
| §3.2 / Segment evaluation | Source/target side-by-side + Q1/Q2/Q3 + auto-save | Implemented | [study/study_app.py:226](../study/study_app.py#L226), [:441](../study/study_app.py#L441) | Auto-save after each Next; Next disabled until Q1+Q3 answered. |
| §3.2 / Ordering | Pseudo-random per participant, L1 first, ≤2 consecutive | Implemented | [study/study_app.py:56](../study/study_app.py#L56) | `_build_segment_order` enforces both constraints. |
| §3.2 / Counterbalancing | Random Form A/B assignment | Implemented | [study/study_app.py:51](../study/study_app.py#L51), [:104](../study/study_app.py#L104) | Form chosen at consent; resolves L2 fluent / disfluent variant. |
| §3.2 / Timing | `displayed_at` + `submitted_at` + `response_time_seconds` | Implemented | [study/study_app.py:417](../study/study_app.py#L417), [:438](../study/study_app.py#L438) | Recorded per segment. |
| §3.2 / Questionnaire | Likert / single_choice / text / textarea types | Implemented | [study/study_app.py:277](../study/study_app.py#L277) | Dynamic from `post_task_questions` config. |
| §3.3 | Response JSON schema (`participant_id`, `segments[]`, `questionnaire`) | Implemented | [study/study_app.py:441](../study/study_app.py#L441), [:537](../study/study_app.py#L537) | Matches spec format incl. `fluency_variant` + `segment_order`. |
| §3.4 | Anonymous (no auth, hash UUID, no PII) | Implemented | [study/study_app.py:46](../study/study_app.py#L46), [:455](../study/study_app.py#L455) | `sha256(uuid4)[:8]`. |
| §4.1 | Study Management as new tab in teacher app | Implemented | [teacher_app.py:2311](../src/tompe/interfaces/teacher_app.py#L2311) | Note: `study/study_manager.py` is a separate broader-public study interface — by design, not duplication. |
| §4.3 / Setup | Editable consent + dates + segment file picker + Launch | Partial | [teacher_app.py:2326](../src/tompe/interfaces/teacher_app.py#L2326) | Translation-student-study tab missing segment file picker + Launch button. |
| §4.3 / Launch | "Launch Study" subprocess + share URL display | Missing | — | No subprocess-launch / share-URL display in either Setup; user must launch `tompe-study` manually. |
| §4.4 / Monitor | Participation summary, detection-by-condition, completion timeline | Partial | [teacher_app.py:2400](../src/tompe/interfaces/teacher_app.py#L2400) | Teacher tab shows participants/completed only; richer dashboard missing for translation-student studies. |
| §4.4 / Quality flags | Form imbalance, fast-completion warnings | Missing | [teacher_app.py:2400](../src/tompe/interfaces/teacher_app.py#L2400) | Not present in teacher-tab study monitor. |
| §4.5 / Export | CSV (long), CSV (wide), JSON downloads | Partial | [teacher_app.py:2437](../src/tompe/interfaces/teacher_app.py#L2437) | Teacher tab does long+JSON; CSV (wide) format missing. |
| §5.1 | Neutral palette, serif text, side-by-side layout | Implemented | [study/study_app.py:127](../study/study_app.py#L127) | Custom CSS uses Georgia serif, neutral background, side-by-side columns. |
| §6.1 | RGPD compliance (anonymous IDs, no PII, withdrawal text) | Implemented | [study/study_app.py:46](../study/study_app.py#L46), [study/study_config.json:18](../study/study_config.json#L18) | Hash IDs + withdrawal text in consent. |

#### Top 5 gaps

1. **"Launch Study" subprocess + Gradio share-URL surfacing absent**: teachers must `tompe-study` from the CLI; the participation link isn't shown anywhere in the teacher UI.
2. **Quality flags** (form imbalance ≤5, <10-min completions, low response-rate alerts) missing from the teacher-tab Monitor view.
3. **CSV (wide) export missing** from the teacher-tab Export view (only long-format + JSON).
4. **Segment editor / segment-file uploader is not implemented** in the teacher-tab Study setup view — teachers must edit the JSON file directly.
5. **Richer participation dashboard** (detection-by-condition, completion timeline) is missing from the translation-student-study tab.

> Note: `study/study_manager.py` is a separate interface for broader-public studies, not a duplicate to consolidate. See "Deliberate scope decisions" at the top of this document.

---

## Group 2 — Fluency Trap (student-facing)

### fluency-trap-badges-spec.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §2.1 | Navigator badge (L0 first exercise) | Implemented | [services/badges.py:50](../src/tompe/services/badges.py#L50) | Trigger: `completed_exercises_at_level >= 1`. |
| §2.1 | Scout / Analyst / Expert badges | Partial | [services/badges.py:63](../src/tompe/services/badges.py#L63) | Awards on level int > 0 every exercise; no `is_level_unlocked` / BKT-mastery gate. |
| §2.2 | BKT mastery (p≥0.98) check for progression | Missing | — | No BKT tracker exists; `progression.py` is `NotImplementedError`. |
| §2.3 | Progression badge visuals (locked silhouettes, accent colours) | Partial | [student_app.py:319](../src/tompe/interfaces/student_app.py#L319), [:310](../src/tompe/interfaces/student_app.py#L310) | Uses CSS greyscale + lock emoji; no pre-rendered locked PNG variants. |
| §3.1 | All 10 specialisation categories defined | Implemented | [schemas/badges.py:169](../src/tompe/schemas/badges.py#L169), [:182](../src/tompe/schemas/badges.py#L182) | Thresholds and badge names match spec exactly. |
| §3.3 | Counting rules (IoU≥0.5, exact category, exclude L0) | Implemented | [services/api.py:704](../src/tompe/services/api.py#L704), [services/badges.py:97](../src/tompe/services/badges.py#L97) | IoU + L0 exclusion both present. |
| §3.4 | Specialisation tier trigger logic | Implemented | [services/badges.py:121](../src/tompe/services/badges.py#L121) | Iterates tiers in reverse, awards highest. |
| §3.5 | Bronze/Silver/Gold tier visuals | Partial | [student_app.py:335](../src/tompe/interfaces/student_app.py#L335), [:361](../src/tompe/interfaces/student_app.py#L361) | Coloured borders + tier letter overlay; no metallic-frame composites. |
| §4.1 | False Positive Discipline trigger | Implemented | [services/badges.py:166](../src/tompe/services/badges.py#L166) | L3 + ≥5 items + zero FP check matches spec. |
| §4.1 | Clean Sheet trigger (repeatable) | Implemented | [services/badges.py:180](../src/tompe/services/badges.py#L180), [services/api.py:731](../src/tompe/services/api.py#L731) | Sprint #1 (A2): `item_results` now assembled at API call site. Needs manual end-to-end check. |
| §4.1 | Trap Detector trigger (≥10 disputes at L0) | Partial | [services/badges.py:202](../src/tompe/services/badges.py#L202) | Counter plumbing landed (A2); `correct_disputes=0` until L0 Confirm/Dispute UI ships (A5b–A5d). |
| §5.1 | XP base values (10 / 5 / 3 / −5) | Implemented | [schemas/badges.py:128](../src/tompe/schemas/badges.py#L128) | Constants match spec. |
| §5.2 | ToM level multipliers (×1.0–×2.0) | Implemented | [schemas/badges.py:113](../src/tompe/schemas/badges.py#L113) | Four levels mapped via legacy ToM names. |
| §5.2 | Scaffolding multipliers (×0.5–×2.0) | Implemented | [schemas/badges.py:120](../src/tompe/schemas/badges.py#L120) | All four scaffolding tiers mapped. |
| §5.3 | XP rounding (ceiling) | Implemented | [schemas/badges.py:149](../src/tompe/schemas/badges.py#L149) | `math.ceil` per component. |
| §6.1 | Skill radar S1–S7 dimensions | Implemented | [student_app.py:460](../src/tompe/interfaces/student_app.py#L460), [schemas/competency.py:47](../src/tompe/schemas/competency.py#L47) | Seven skills wired into radar SVG. |
| §6.2 | Axis values from BKT mastery (0.98 threshold) | Missing | [services/api.py:780](../src/tompe/services/api.py#L780) | API never sets `skill_profile`; radar always renders zeros. |
| §6.3 | Radar visuals (heptagonal, dashed mastery, accent fill) | Implemented | [student_app.py:483](../src/tompe/interfaces/student_app.py#L483) | SVG with mastery dashed circle + level-coloured fill. |
| §7.1 | Badge Collection panel (Location 1) | Implemented | [student_app.py:292](../src/tompe/interfaces/student_app.py#L292), [:1768](../src/tompe/interfaces/student_app.py#L1768) | Three sections (progression/specialisation/achievements) + XP. |
| §7.1 | Skill Radar panel (Location 2) | Partial | [student_app.py:1771](../src/tompe/interfaces/student_app.py#L1771) | Renders, but always shows zeros (no BKT data source). |
| §7.1 | Badge notification toast (Location 3) | Partial | [student_app.py:551](../src/tompe/interfaces/student_app.py#L551), [:1421](../src/tompe/interfaces/student_app.py#L1421) | Renders inline after feedback; no auto-dismiss / queue / Continue logic. |
| §7.1 | "Show all" toggle for specialisation | Missing | — | All 10 specialisation cells always rendered. |
| §7.2 | Hover/tap tooltips with progress | Partial | [student_app.py:381](../src/tompe/interfaces/student_app.py#L381), [:431](../src/tompe/interfaces/student_app.py#L431) | HTML `title=` attributes only; no rich tooltip with date earned. |
| §7.2 | Skill radar hover (BKT prob + observations) | Missing | — | No hover handlers on radar axes. |
| §8.1 | Badge distribution heatmap | Implemented | [teacher_app.py:2110](../src/tompe/interfaces/teacher_app.py#L2110) | Plotly heatmap with 4-stop colorscale. |
| §8.1 | Most/least earned badges | Partial | [teacher_app.py:2130](../src/tompe/interfaces/teacher_app.py#L2130) | Empty-categories warning only; no ranked most-earned list. |
| §8.2 | Individual student view (badges + radar mirror) | Missing | [teacher_app.py:1632](../src/tompe/interfaces/teacher_app.py#L1632) | Shows Wasserstein / MQM / ToM but not the student-facing badge collection. |
| §8.2 | XP timeline chart | Missing | — | `xp_history` stored but never rendered as a line chart. |
| §8.2 | Badge timeline (chronological earn list) | Missing | — | `earned_at` stored but no UI surfaces it. |
| §8.3 | Visibility toggle (`badges_visible`) | Implemented | [services/api.py](../src/tompe/services/api.py), [schemas/session.py:59](../src/tompe/schemas/session.py#L59) | Sprint #1 (A3): plumbed through `api_get_feedback`, `api_get_progress`, `api_get_badges`. Tracking continues internally per spec §8.3. |
| §8.3 | Threshold override per class | Implemented | [services/badges.py](../src/tompe/services/badges.py), [services/api.py](../src/tompe/services/api.py) | Sprint #1 (A3): per-class overrides reach `check_specialisation_badges` and `get_badge_summary`. Falls back to global `CATEGORY_THRESHOLDS`. |
| §9.1 | BadgeDefinition / EarnedBadge / StudentBadges schemas | Implemented | [schemas/badges.py:28](../src/tompe/schemas/badges.py#L28), [:40](../src/tompe/schemas/badges.py#L40), [:50](../src/tompe/schemas/badges.py#L50) | Pydantic models present (`StudentBadges` replaces `StudentXP`). |
| §9.2 | Filesystem JSON storage + post-exercise checks | Implemented | [services/badges.py:21](../src/tompe/services/badges.py#L21), [services/api.py:731](../src/tompe/services/api.py#L731) | `badges_store` + `process_badges_and_xp` runs in feedback flow. |
| §10 | Asset generation pipeline (PIL composite + locked variants) | Missing | — | No script; only static `.jpg` files in `assets/badges/`, no `*_locked.*`. |

### Top 5 gaps

1. **Skill Radar has no data source.** The student UI renders the heptagonal SVG but `api_get_progress` never returns `skill_profile`, so every student sees a blank radar. The most visible "implemented but inert" feature. Wire BKT or detection-rate-based mastery probabilities for S1–S7 into [api.py:780](../src/tompe/services/api.py#L780).
2. **Behaviour badges (Clean Sheet, Trap Detector) never fire.** `process_badges_and_xp` is called from [api.py:731](../src/tompe/services/api.py#L731) without `item_results`, so the per-item loop at [badges.py:180](../src/tompe/services/badges.py#L180) and the dispute counter at [:206](../src/tompe/services/badges.py#L206) never execute. False Positive Discipline works because it reads from `scoring` directly. Build the per-item breakdown dict at the call site.
3. **Teacher-set threshold overrides and visibility toggle are saved but ignored.** `class_obj.badge_threshold_overrides` and `badges_visible` are persisted ([schemas/session.py:60](../src/tompe/schemas/session.py#L60)) yet `check_specialisation_badges` reads only the global `CATEGORY_THRESHOLDS` and `_build_badge_collection_html` never checks visibility. Plumb the class context through `process_badges_and_xp`.
4. **Progression beyond Navigator is not gated by mastery.** Spec requires BKT p≥0.98 + teacher unlock; current code awards Scout / Analyst / Expert as soon as the student is *at* that level ([badges.py:63](../src/tompe/services/badges.py#L63)). `progression.py:20` is `NotImplementedError`. Either implement the BKT tracker or gate on a teacher-approval flag on `StudentAccount.allowed_levels`.
5. **Teacher individual-student badge surfaces are missing: XP timeline, badge timeline, and the embedded badge collection.** §8.2 requires teachers to see the student-facing panels plus two new charts. The data (`xp_history`, `earned_at`) is already stored — only `_analytics_individual_student` ([teacher_app.py:1632](../src/tompe/interfaces/teacher_app.py#L1632)) needs the rendering. Lowest-effort, highest-visibility win for EC-TEL / CIKM demos.

---

## Group 3 — Pipeline & error injection

### ToM-PE_Error_Injection_Annotation_Spec_v1.1.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §1.2 | Canonical XML tag format with type/severity/tom/desc attributes | Implemented | [pipeline/error_injector.py:44](../src/tompe/pipeline/error_injector.py#L44) | Regex enforces all four attributes. |
| §1.2.1 | severity_range per codebook entry; context-dependent severity | Implemented | [pipeline/mqm_taxonomy.py:39](../src/tompe/pipeline/mqm_taxonomy.py#L39) | Each `ErrorTypeSpec` carries `severity_range`. |
| §1.2.2 | Direction attribute (en_fr / fr_en / both) on error types | Implemented | [pipeline/mqm_taxonomy.py:32](../src/tompe/pipeline/mqm_taxonomy.py#L32) | `direction` field set per spec. |
| §1.3 | 10 primary tags | Implemented | [schemas/enums.py:6](../src/tompe/schemas/enums.py#L6) | All 10 tags as `PrimaryTag` enum. |
| §1.3 | ~25–37 type attribute values across primary tags | Implemented | [pipeline/mqm_taxonomy.py:39](../src/tompe/pipeline/mqm_taxonomy.py#L39) | 37 `ErrorTypeSpec` entries. |
| §1.4 | Inline XML examples in few-shot prompts | Implemented | [data/codebook/error_codebook_fr_en.json:151](../data/codebook/error_codebook_fr_en.json#L151) | Codebook examples carry inline XML. |
| §2.2 | Step 1 planning prompt with reasoning JSON schema | Implemented | [pipeline/error_injector.py:301](../src/tompe/pipeline/error_injector.py#L301) | `build_step1_prompt` + STEP1 schema. |
| §2.3 | Step 2 execution prompt with structured output JSON | Implemented | [pipeline/error_injector.py:330](../src/tompe/pipeline/error_injector.py#L330) | `build_step2_prompt` + STEP2 schema. |
| §2.4 | Verification: XML parse, diff, tag/sev/tom validation, explanation completeness | Implemented | [pipeline/error_injector.py:159](../src/tompe/pipeline/error_injector.py#L159) | All 4+ checks; fuzzy diff at 0.95. |
| §2.4 | xCOMET QE check post-injection | N/A | [experiments/pipeline_validation/track_a/xcomet_scoring.py:47](../experiments/pipeline_validation/track_a/xcomet_scoring.py#L47) | Deferred — GPU requirement; see Deliberate scope decisions. |
| §2.4 | GEMBA detection check post-injection | Implemented (opt-in) | [pipeline/qe_validator.py:197](../src/tompe/pipeline/qe_validator.py#L197), [error_injector.py:502](../src/tompe/pipeline/error_injector.py#L502) | Sprint #2 (B9): `inject_errors_reference_based(verify_gemba=True)` runs a post-injection GEMBA pass and raises on detection<threshold. Default off. |
| §2.4 | Retry queue (max 3 attempts with rephrased prompts) | Implemented | [pipeline/error_injector.py:301](../src/tompe/pipeline/error_injector.py#L301) | Loop up to `_MAX_INJECTION_RETRIES=3`. |
| §3.2 | 7-skill model (S1–S7) | Implemented | [schemas/enums.py:45](../src/tompe/schemas/enums.py#L45) | `SkillID` enum with descriptions. |
| §3.3 | Full MQM × ToM → Skill mapping matrix | Implemented | [pipeline/mqm_taxonomy.py:39](../src/tompe/pipeline/mqm_taxonomy.py#L39) | `ErrorTypeSpec` carries `primary_skill` + secondary. |
| §3.4 | 5-stage progression mapping (S1→S7 across stages) | Partial | [schemas/competency.py:31](../src/tompe/schemas/competency.py#L31) | `StageDefinition` exists; runtime gating not audited. |
| §3.5 | Per-skill mastery thresholds | Partial | [schemas/competency.py:23](../src/tompe/schemas/competency.py#L23) | `MasteryThreshold` model defined; thresholds not seeded. |
| §4.2 | `ErrorAnnotation` + `RegionHint` scaffolding model | Implemented | [schemas/annotation.py:32](../src/tompe/schemas/annotation.py#L32) | All fields per spec. |
| §4.3 | L0–L3 student-facing scaffolding views | Implemented | [interfaces/student_app.py:1](../src/tompe/interfaces/student_app.py#L1) | `AnnotationLevel` enum drives views. |
| §4.4 | Tag colour scheme (10 colours + clean green) | Implemented | [pipeline/mqm_taxonomy.py:296](../src/tompe/pipeline/mqm_taxonomy.py#L296) | `TAG_COLORS` dict matches hex values. |
| §5.1 | Codebook entry schema (definition, boundary_not, examples, explanation) | Implemented | [pipeline/codebook.py:42](../src/tompe/pipeline/codebook.py#L42) | `CodebookEntry` pydantic model. |
| §5.2 | Codebook coverage: 37 types, ~111 examples | Partial | [data/codebook/error_codebook_fr_en.json:6](../data/codebook/error_codebook_fr_en.json#L6) | Only 8 codebook entries present (vs 37 target). |
| §5.4 | Layer 1 contrastive explanation generator | Implemented | [pipeline/explanation_generator.py:39](../src/tompe/pipeline/explanation_generator.py#L39) | LLM call with 4-field schema. |
| §5.4 | Layer 2a popular-science explanation generator | Implemented | [pipeline/explanation_generator.py:78](../src/tompe/pipeline/explanation_generator.py#L78) | `SystemBehaviorExplanation`. |
| §5.4 | Layer 2b technical explanation (progressive disclosure) | Implemented | [pipeline/explanation_generator.py:111](../src/tompe/pipeline/explanation_generator.py#L111) | Optional, off by default. |
| §5.4 | layer2a / layer2b reusable explanation templates (committed) | Implemented | [data/codebook/layer2a_explanations.json](../data/codebook/layer2a_explanations.json), [data/codebook/layer2b_explanations.json](../data/codebook/layer2b_explanations.json), [explanation_generator.py](../src/tompe/pipeline/explanation_generator.py) | Sprint #2 (B6): cache files committed with seed entries; generators consult cache before LLM call. Bulk content authoring still pending (3.1 in Phase 3 plan). |
| §5.5 | Tagging strategy ablation (C1–C4) | Missing | — | No `experiments/ablation_tagging.py`. |
| §6 | Justification-before-feedback (cognitive forcing) | Implemented | [interfaces/student_app.py:1](../src/tompe/interfaces/student_app.py#L1) | Justify phase precedes feedback. |
| §7.2 | Authentic pathway error detection (xCOMET + GEMBA cross-validation) | Missing | [pipeline/authentic_detector.py:11](../src/tompe/pipeline/authentic_detector.py#L11) | `detect_authentic_errors` raises `NotImplementedError`. |
| §7.2 | `item_builder` full-pipeline orchestration | Missing | [pipeline/item_builder.py:10](../src/tompe/pipeline/item_builder.py#L10) | `build_item` / `build_batch` raise `NotImplementedError`. |

#### Top 5 gaps (after Sprint #2)

1. **Codebook coverage (§5.2)** — only 8 of the targeted ~37 codebook entries exist. The pipeline runs via the taxonomy fallback, but few-shot quality depends on the codebook; this is the single biggest content gap. *(Phase 3 item 3.1.)*
2. **Authentic pathway (§7.2)** — `authentic_detector.detect_authentic_errors` is a stub. Without it, the controlled-vs-authentic distinction is purely controlled. *(Phase 3 item 3.2.)*
3. **`item_builder` orchestration (§7.2)** — `build_item` / `build_batch` raise `NotImplementedError`; the full pipeline is currently driven by `experiments/pipeline_validation/generate_batch.py` rather than the canonical `pipeline/item_builder.py`. *(Phase 3 item 3.3.)*
4. **Tagging strategy ablation (§5.5)** — no `experiments/ablation_tagging.py`; the C1–C4 ablation that justifies the tag format choice is absent. *(Phase 3 item 3.4.)*
5. ~~**Pre-curated Layer 2a / 2b explanation templates (§5.4)**~~ — **RESOLVED — Sprint #2 (B6).** Cache files committed; generators consult them before LLM. Curating ~30 entries remains content work; tracked under Phase 3 item 3.1.

---

### pipeline-validation-spec-v3.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §1 | Three tracks A / B / C | Implemented | [run_all.py:1](../experiments/pipeline_validation/run_all.py#L1) | Track-level orchestration present. |
| §2.1 | 200-item batch (50 per corpus, 4 corpora) | Implemented | [config.py:29](../experiments/pipeline_validation/config.py#L29) | `TOTAL_ITEMS=200`, 4 corpora configured. |
| §2.1 | EN→FR direction lock | Implemented | [config.py:25](../experiments/pipeline_validation/config.py#L25) | `DIRECTION="en_fr"`. |
| §2.1 | 25% clean-segment ratio (50 clean items) | Implemented | [config.py:41](../experiments/pipeline_validation/config.py#L41) | `CLEAN_RATIO=0.25`. |
| §2.1 | 1 error / item (post-remediation v3 narrative) | Implemented | [generate_batch.py:255](../experiments/pipeline_validation/generate_batch.py#L255), [config/settings.yaml](../config/settings.yaml) | Sprint #1 (A4): `single_error=True` reads `validation_severity_distribution` from YAML; production keeps default. |
| §2.2 | Stratified ToM-level sampling incl. L3 | Implemented | [generate_batch.py:140](../experiments/pipeline_validation/generate_batch.py#L140) | `select_l3_long_segments` + adjacent_pairs. |
| §3 A1 | Structural validation (XML parse, attrs, span bounds, surrounding text) | Implemented | [track_a/structural_check.py:263](../experiments/pipeline_validation/track_a/structural_check.py#L263) | All 5 checks. |
| §3 A2 | GEMBA-MQM detection rate, category agreement, FP rate | Implemented | [track_a/gemba_detection.py:1](../experiments/pipeline_validation/track_a/gemba_detection.py#L1) | Full A2 pipeline. |
| §3 A2 | IoU > 0.5 span matching | Implemented | [pipeline/qe_validator.py:23-25](../src/tompe/pipeline/qe_validator.py#L23-L25), [:184](../src/tompe/pipeline/qe_validator.py#L184) | Sprint #2 (B1): `_GEMBA_IOU_THRESHOLD = 0.5` constant; validator and Track A2 now agree. (Student-scoring IoU stays 0.3 by design — different domain.) |
| §3 A3 | xCOMET-XL scoring with `score_drop`, by ToM, by severity, clean stability | N/A | [track_a/xcomet_scoring.py:164](../experiments/pipeline_validation/track_a/xcomet_scoring.py#L164) | Deferred — GPU requirement; module exists for future use. |
| §3 A3 | xCOMET-XL specifically (not wmt22-comet-da) | N/A | [config.py:85](../experiments/pipeline_validation/config.py#L85) | Deferred; `XCOMET_MODEL` deliberately on `wmt22-comet-da`. |
| §4.2 | B0 random perturbation baseline | Implemented | [baselines/random_perturbation.py:105](../experiments/pipeline_validation/baselines/random_perturbation.py#L105) | NLTK + WordNet, 3 ops. |
| §4.2 | B1 single-step LLM injection baseline | Implemented | [baselines/single_step_inject.py:1](../experiments/pipeline_validation/baselines/single_step_inject.py#L1) | `inject_single_step`. |
| §4.2 | B2 unconstrained LLM injection baseline | Implemented | [baselines/unconstrained_inject.py:1](../experiments/pipeline_validation/baselines/unconstrained_inject.py#L1) | `inject_unconstrained` with FAVA-style prompt. |
| §4.3 | 60 shared segments × 4 conditions | Implemented | [track_b/ablation_comparison.py:344](../experiments/pipeline_validation/track_b/ablation_comparison.py#L344) | `run_ablation` orchestrator. |
| §4.4 | Per-condition metrics (structural, GEMBA, category fidelity, score drop, preservation) | Implemented | [track_b/ablation_comparison.py:267](../experiments/pipeline_validation/track_b/ablation_comparison.py#L267) | All 5 metrics computed. |
| §5.1 | Three "annotators" (Pipeline GT, Human, GEMBA) on same 72 items | Implemented | [track_c/three_way_agreement.py:1](../experiments/pipeline_validation/track_c/three_way_agreement.py#L1) | Schema + IoU matching. |
| §5.2 | 72 / 84-item annotation set with practice + ToM-stratified sampling | Implemented | [track_c/prepare_annotation_set.py:1](../experiments/pipeline_validation/track_c/prepare_annotation_set.py#L1) | 84-item composition supersedes v2's 72. |
| §5.3 | Pairwise Cohen's κ, three-way overlap | Implemented | [track_c/three_way_agreement.py:78](../experiments/pipeline_validation/track_c/three_way_agreement.py#L78) | Manual + sklearn fallback. |
| §5.4 | Cochran-Armitage trend test by ToM level | Implemented | [track_c/three_way_agreement.py:113](../experiments/pipeline_validation/track_c/three_way_agreement.py#L113) | `_cochran_armitage_trend`. |
| §5.5 | Naturalness comparison (Mann-Whitney, Fisher, χ²) | Implemented | [track_c/naturalness_test.py:1](../experiments/pipeline_validation/track_c/naturalness_test.py#L1) | Pipeline vs authentic. |
| §5.6 (v3) | Phase B explanation quality review (factual / clarity / completeness) | Implemented | [track_c/explanation_quality.py:1](../experiments/pipeline_validation/track_c/explanation_quality.py#L1) | New v3 module present. |
| §5.6 | 24 explanation review items (6 per ToM) | Implemented | [config.py:63](../experiments/pipeline_validation/config.py#L63) | `ANNOTATION_PIPELINE_PER_TOM=6`. |
| §7 | Results tables 1–3 generation | Implemented | [tables.py:243](../experiments/pipeline_validation/tables.py#L243) | Sprint #2 spot-check confirmed: Table 3 emits factual_accuracy / clarity / completeness columns by ToM level. |
| §9 | Master orchestration script (`run_all.sh` / `run_all.py`) | Implemented | [run_all.py:1](../experiments/pipeline_validation/run_all.py#L1) | Track selection via CLI. |

#### Top 5 gaps (after Sprint #2)

1. ~~**Wrong xCOMET model in config (§3 A3)**~~ — **N/A — deliberate scope decision.** xCOMET-XL is GPU-deferred; `XCOMET_MODEL` deliberately points at `wmt22-comet-da`. Re-evaluate when GPU host arrives.
2. ~~**Single-error mode is not config-driven**~~ — **RESOLVED — Sprint #1 (A4) + Sprint #2 (B0).** `validation_severity_distribution` lives in `settings.yaml`; constants source from YAML at import; CLI `--single-error` / `--production` flags expose the toggle.
3. ~~**IoU threshold inconsistency (§3 A2)**~~ — **RESOLVED — Sprint #2 (B1).** `_GEMBA_IOU_THRESHOLD = 0.5` in `qe_validator.py`; matches Track A2 and `IOU_THRESHOLD = 0.5` in experiments config.
4. ~~**GEMBA / xCOMET not gating injection (§2.4)**~~ — **RESOLVED (opt-in) — Sprint #2 (B9).** `inject_errors_reference_based(verify_gemba=True)` runs a post-injection GEMBA pass and raises on detection<threshold. Default off so existing batch runs are unchanged; opt in per-call site or via a config flag if desired.
5. ~~**Tables 1–3 v3 explanation-quality column**~~ — **RESOLVED.** [tables.py:243](../experiments/pipeline_validation/tables.py#L243) emits factual_accuracy / clarity / completeness columns by ToM level (verified during Sprint #2).

> All five 2026-05-09 gaps for this spec are now closed. Remaining work for paper-readiness is research-scale and tracked under the Phase 3 plan (codebook coverage, authentic pathway, tagging ablation).

---

### pipeline-remediation-spec.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §1.3 R1 | Codebook entry: cross-sentence anaphora resolution | Implemented | [error_codebook_fr_en.json:135](../data/codebook/error_codebook_fr_en.json#L135) | `ACC-MIST-AR-001`. |
| §1.3 R2 | Codebook entry: discourse connective inconsistency | Implemented | [error_codebook_fr_en.json:174](../data/codebook/error_codebook_fr_en.json#L174) | `ACC-MIST-DC-001`. |
| §1.3 R3 | Codebook entry: tense sequence | Implemented | [error_codebook_fr_en.json:213](../data/codebook/error_codebook_fr_en.json#L213) | `FLU-GRAM-TS-001`. |
| §1.3 R4 | Codebook entry: lexical cohesion | Implemented | [error_codebook_fr_en.json:252](../data/codebook/error_codebook_fr_en.json#L252) | `TRM-INC-LC-001`. |
| §1.3 R5 | Codebook entry: information packaging | Implemented | [error_codebook_fr_en.json:291](../data/codebook/error_codebook_fr_en.json#L291) | `STY-AWK-IP-001`. |
| §1.3 | `tom_level=recursive` + `skill=S7` on R1–R5 | Implemented | [error_codebook_fr_en.json:140](../data/codebook/error_codebook_fr_en.json#L140) | All 5 entries set correctly. |
| §1.3 | Tag schema accepts new types | Implemented | [tag_schema.json:7](../data/codebook/tag_schema.json#L7) | Listed in `primary_tags.types`. |
| §1.3 | Taxonomy `ERROR_TYPE_SPECS` adds 5 L3 specs | Implemented | [pipeline/mqm_taxonomy.py:246](../src/tompe/pipeline/mqm_taxonomy.py#L246) | 5 `RECURSIVE_MULTI` specs at S7. |
| §1.4 Strategy 1 | Long-segment selection (30–150 tokens) for L3 R2 / R3 / R4 | Implemented | [segment_selector.py:218](../src/tompe/pipeline/segment_selector.py#L218) | Sprint #2 (B5): moved into `segment_selector.select_l3_long_segments`; scores by clause indicators. |
| §1.4 Strategy 2 | Positional adjacency pair concatenation for R1 / R5 | Implemented | [segment_selector.py:255](../src/tompe/pipeline/segment_selector.py#L255) | Sprint #2 (B5): moved into `segment_selector.select_l3_adjacent_pairs`; uses `document_id` + `position_in_doc`. |
| §1.4 Strategy 2 | `document_id` and `position_in_doc` on `CorpusSegment` | Implemented | [schemas/corpus.py:24](../src/tompe/schemas/corpus.py#L24), [segment_selector.py:218-220](../src/tompe/pipeline/segment_selector.py#L218-L220) | Sprint #2 (B5): also preserved through `select_segments`'s CorpusSegment construction. |
| §1.4 Strategy 2 | `is_likely_boundary` heuristic (header / length / noun overlap) | Implemented | [segment_selector.py:175-191](../src/tompe/pipeline/segment_selector.py#L175-L191) | Sprint #2 (B4): header regex (ANNEX/CHAPTER/…), short-s1 (<5 tokens), short-s2 (<4 tokens), content-word-overlap (stopword-filtered, no spaCy dep). |
| §1.4 Strategy 3 | LLM-generated context fallback | Missing | — | No code path generates synthetic context for L3. *(Phase 3 item 3.5.)* |
| §1.4 | `segment_selector.py` parameterised by `tom_level` | Implemented | [segment_selector.py:319](../src/tompe/pipeline/segment_selector.py#L319) | Sprint #2 (B5): `select_segments(tom_level=…)` relaxes token windows for `RECURSIVE_MULTI`; `generate_batch` imports L3 helpers from here. |
| §2.3 | Single-error validation mode (n_errors=1) | Implemented | [generate_batch.py:255](../experiments/pipeline_validation/generate_batch.py#L255) | Sprint #1 (A4): YAML-driven via `VALIDATION_SEVERITY_DISTRIBUTION`. |
| §2.3 | `validation_severity_distribution` config in `settings.yaml` | Implemented | [config/settings.yaml](../config/settings.yaml) | Sprint #1 (A4): added to `error_injection`; mirrored in `experiments/pipeline_validation/config.py`. |
| §3.1 | Batch regeneration: 200 items with L3 + 1 error each | Implemented | [generate_batch.py:382](../experiments/pipeline_validation/generate_batch.py#L382) | `generate_batch` supports new spec. |
| §3.5 | Re-run baselines on new 60 segments | Implemented | [track_b/ablation_comparison.py:344](../experiments/pipeline_validation/track_b/ablation_comparison.py#L344) | `run_ablation` reuses generated items. |
| §3.6 | Updated annotation set with L3 items | Implemented | [track_c/prepare_annotation_set.py:42](../experiments/pipeline_validation/track_c/prepare_annotation_set.py#L42) | `_BASELINE_TOM_QUOTA` includes `recursive=1`. |
| §4.3 | Reframe ablation narrative (Q1 / Q2 / Q3 in paper) | N/A | — | Narrative is paper text, not code. |
| §6 | UNPC corpus ingested or removed | Implemented (Option B) | [config.py:31-34](../experiments/pipeline_validation/config.py#L31-L34) | Sprint #2 (B2): `unpc` removed from `CORPORA`; empty `data/corpora/unpc/` kept as placeholder for future re-ingestion. |
| §8.1 | Codebook validation script | Missing | — | No `data/codebook` validator script committed. |

#### Top 5 gaps (after Sprint #2)

1. ~~**No `validation_severity_distribution` config knob (§2.3)**~~ — **RESOLVED — Sprint #1 (A4) + Sprint #2 (B0).** YAML knob lives in `error_injection`; Python constants source from YAML at import time; CLI flags expose the toggle.
2. ~~**`is_likely_boundary` heuristic incomplete (§1.4 Strategy 2)**~~ — **RESOLVED — Sprint #2 (B4).** Header regex + short-s1 + content-word-overlap heuristic in `segment_selector.py`.
3. **Strategy 3 (LLM context generation) missing (§1.4)** — No fallback when long-segment + adjacency yields too few L3 candidates. Spec marks this as the safety net for L3 coverage. *(Phase 3 item 3.5.)*
4. ~~**`segment_selector.py` not parameterised by `tom_level` (§1.4)**~~ — **RESOLVED — Sprint #2 (B5).** `select_segments(tom_level=…)` accepts `TOMLevel.RECURSIVE_MULTI` and relaxes token windows; L3 helpers moved into `pipeline/segment_selector.py`.
5. ~~**UNPC ingestion not actually fixed (§6)**~~ — **RESOLVED (Option B) — Sprint #2 (B2).** `unpc` dropped from `CORPORA`; placeholder dir retained for future re-ingest.
6. **Codebook validation script (§8.1)** — *Newly elevated.* No `data/codebook` validator script committed. Lower priority than Phase 3 items but worth scaffolding when codebook coverage expands. *(Tracked alongside Phase 3 item 3.1.)*

---

### annotation-tool-spec-v3.md

#### Gap table

| Section | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| §1 | Standalone annotation tool (separate from student app) | Implemented | [annotation_app.py:1](../src/tompe/interfaces/annotation_app.py#L1) | Self-contained Gradio app on port 7861. |
| §1 | Two phases (A error annotation + B explanation review) | Implemented | [annotation_app.py:307](../src/tompe/interfaces/annotation_app.py#L307) | `phase_a_view` + `phase_b_view`. |
| §2.1 | Login screen with annotator ID | Implemented | [annotation_app.py:289](../src/tompe/interfaces/annotation_app.py#L289) | `login_view`. |
| §2.2 | Instructions screen | Partial | [annotation_app.py:290](../src/tompe/interfaces/annotation_app.py#L290) | Brief markdown intro; no full instructions block matching spec wording. |
| §2.3 | Source / translation panels with span selection | Implemented | [annotation_app.py:316](../src/tompe/interfaces/annotation_app.py#L316) | `render_text_with_highlights` + JS span selector. |
| §2.3 | 10-category MQM pill buttons | Implemented | [annotation_app.py:40](../src/tompe/interfaces/annotation_app.py#L40) | All 10 `PrimaryTag` values rendered as buttons. |
| §2.3 | Severity radio (minor / major / critical) | Implemented | [annotation_app.py:349](../src/tompe/interfaces/annotation_app.py#L349) | `severity_radio`. |
| §2.3 | "Add Error" + multi-error chip list | Implemented | [annotation_app.py:354](../src/tompe/interfaces/annotation_app.py#L354) | `annotations_state` + `render_annotation_chips`. |
| §2.3 | "No Errors Found" button | Implemented | [annotation_app.py:373](../src/tompe/interfaces/annotation_app.py#L373) | `no_errors_btn`. |
| §2.3 | Confidence rating + free-text notes | Implemented | [annotation_app.py:362](../src/tompe/interfaces/annotation_app.py#L362) | Both present. |
| §2.4 | Per-item `timestamp_start` / `_end` + `duration_seconds` | Implemented | [annotation_app.py:609](../src/tompe/interfaces/annotation_app.py#L609) | Recorded in saved record. |
| §2.4 | Visible per-item timer | Implemented | [annotation_app.py:178-218](../src/tompe/interfaces/annotation_app.py#L178-L218), [:1083](../src/tompe/interfaces/annotation_app.py#L1083) | Sprint #2 (B3): `ANNOTATION_TIMER_JS` injected via `app.load(js=…)`; `.timer-display` ticks every 500ms and resets on `#btn-submit-next` / `#btn-no-errors` / `#btn-start-phase-a` / `#btn-start-phase-b` / `#btn-submit-expl` clicks. |
| §2.5 | Phase A → B transition screen | Implemented | [annotation_app.py:383](../src/tompe/interfaces/annotation_app.py#L383) | `transition_view`. |
| §2.6 | Phase B explanation review with Layer 1 + 2a + ground truth highlight | Implemented | [annotation_app.py:749](../src/tompe/interfaces/annotation_app.py#L749) | `_load_item_b` renders both layers. |
| §2.6 | 3-point rating scales (factual / clarity / completeness) | Implemented | [annotation_app.py:418](../src/tompe/interfaces/annotation_app.py#L418) | Three radios with spec-correct labels. |
| §2.6 | Optional comment field | Implemented | [annotation_app.py:433](../src/tompe/interfaces/annotation_app.py#L433) | `comment_box`. |
| §2.7 | Final completion screen | Partial | [annotation_app.py:983](../src/tompe/interfaces/annotation_app.py#L983) | Built but uses fragile `done_view.select` event hookup. |
| §3.1 | `ExpertAnnotation` pydantic schema | Implemented | [schemas/expert_annotation.py:40](../src/tompe/schemas/expert_annotation.py#L40) | All fields per spec. |
| §3.1 | `AnnotatedError` schema | Implemented | [schemas/expert_annotation.py:17](../src/tompe/schemas/expert_annotation.py#L17) | Matches spec. |
| §3.1 | `ExplanationRating` schema | Implemented | [schemas/expert_annotation.py:69](../src/tompe/schemas/expert_annotation.py#L69) | Matches spec. |
| §3.1 | `GEMBAAnnotation` / `GEMBAAnnotatedError` schemas | Implemented | [schemas/expert_annotation.py:27](../src/tompe/schemas/expert_annotation.py#L27) | Present for parallel annotation. |
| §3.2 | Storage at `data/annotations/{annotator_id}/{item_id}.json` | Implemented | [annotation_app.py:76](../src/tompe/interfaces/annotation_app.py#L76) | `save_annotation` writes per-item JSON. |
| §4.1 | 84-item annotation set composition | Implemented (runner) | [track_c/prepare_annotation_set.py:1](../experiments/pipeline_validation/track_c/prepare_annotation_set.py#L1), [track_c/build_annotation_set.py](../experiments/pipeline_validation/track_c/build_annotation_set.py) | Sprint #2 (B7): `build_annotation_set.py` is the end-to-end "batch → ablation → annotation_set.json" runner. Actual file is generated, not committed (correct — depends on a real pipeline run). |
| §4.2 | Segment reuse: same 6 source segments across baselines + full pipeline | Implemented | [track_c/prepare_annotation_set.py:106-150](../experiments/pipeline_validation/track_c/prepare_annotation_set.py#L106-L150) | Sprint #2 (B8): `_baseline_sample(forced_segment_ids=…)`. B0 picks first via ToM quota; B1/B2 reuse those `segment_id`s with stratified fallback for missing items. |
| §4.3 | Authentic MT items (12) | Partial | [config.py:65](../experiments/pipeline_validation/config.py#L65) | Slot reserved (`ANNOTATION_AUTHENTIC=12`); no real authentic source pipeline. |
| §5 | GEMBA-MQM parallel annotation pre-computed | Implemented | [track_a/gemba_detection.py:1](../experiments/pipeline_validation/track_a/gemba_detection.py#L1) | Available; spec says run before human annotation. |
| §6.1 | Three-way agreement (Pipeline × Human × GEMBA) with IoU + κ | Implemented | [track_c/three_way_agreement.py:1](../experiments/pipeline_validation/track_c/three_way_agreement.py#L1) | Full module. |
| §6.2 | Agreement by ToM level + Cochran-Armitage trend | Implemented | [track_c/three_way_agreement.py:113](../experiments/pipeline_validation/track_c/three_way_agreement.py#L113) | `_cochran_armitage_trend`. |
| §6.3 | Ablation comparison metrics from human annotation | Implemented | [track_b/ablation_comparison.py:267](../experiments/pipeline_validation/track_b/ablation_comparison.py#L267) | Cross-condition table. |
| §6.4 | Naturalness comparison (Mann-Whitney / Fisher / χ²) | Implemented | [track_c/naturalness_test.py:1](../experiments/pipeline_validation/track_c/naturalness_test.py#L1) | All three tests. |
| §6.5 | Time analysis | Partial | [track_c/explanation_quality.py:54](../experiments/pipeline_validation/track_c/explanation_quality.py#L54) | Phase B time analysis present; Phase A not separately committed. |
| §6.6 | False positive analysis (real-MT vs genuine FP categorisation) | Missing | — | No `false_positive_analysis.py`; spec has dedicated checklist item. |
| §6.7 | Explanation quality aggregate metrics + by ToM | Implemented | [track_c/explanation_quality.py:36](../experiments/pipeline_validation/track_c/explanation_quality.py#L36) | `n_ratings`, `by_tom`, `fully_satisfactory`. |
| §7.1 | Practice-mode flag (first 3 items excluded from analysis) | Partial | [annotation_app.py:624](../src/tompe/interfaces/annotation_app.py#L624) | `is_practice` flag stored from item, but no UI distinction. |
| §7.1 | Item randomisation with seed | Partial | [config.py:72](../experiments/pipeline_validation/config.py#L72) | Seed defined; randomisation done at `prepare_annotation_set` time. |
| §7.1 | French span selector handles accents / ligatures | Partial | [components/span_selector.py:106](../src/tompe/interfaces/components/span_selector.py#L106) | Generic JS, no specific French normalisation tested. |

#### Top 5 gaps (after Sprint #2)

1. ~~**No real `annotation_set.json` file (§4.1)**~~ — **RESOLVED (runner) — Sprint #2 (B7).** `track_c/build_annotation_set.py` orchestrates batch → ablation → annotation_set.json. The file is generated by running the script, not committed (correct).
2. ~~**Segment reuse across conditions not enforced (§4.2)**~~ — **RESOLVED — Sprint #2 (B8).** `_baseline_sample(forced_segment_ids=…)` makes B1/B2 reuse B0's chosen segment_ids with stratified fallback for missing items.
3. **False positive analysis missing (§6.6)** — No `false_positive_analysis.py`. Categorising human FPs into "real MT error" vs "genuine false alarm" is a checklist item that is not implemented. *(Phase 3 item 3.6.)*
4. ~~**Live timer not animated (§2.4)**~~ — **RESOLVED — Sprint #2 (B3).** `.timer-display` now ticks via `gr.Blocks.load(js=ANNOTATION_TIMER_JS)`; per-item buttons reset the timer. Manual browser check still owed.
5. **Authentic MT pathway absent (§4.3)** — 12 authentic items budgeted; `authentic_detector.py` is `NotImplementedError`. Either implement, or document the fall-back where authentic count goes to 0 and pipeline items expand. *(Phase 3 item 3.2.)*

---

## Appendix — audit methodology

- Each agent read the spec in full, then verified every code reference by opening the cited line.
- "Implemented" requires a wired runtime path, not just a schema field or config knob.
- "Partial" rows specify which fraction is done (e.g. "trigger logic yes, UI panel no").
- Where two specs overlap (e.g. UI spec + Study Interface spec on the same screen), the feature is audited under whichever spec defines it first; cross-references appear in the Note column.
- v2/v3 specs: only the latest version was audited. Where current code matches v2 but not v3, that is flagged in the row.
