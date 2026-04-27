## Context

The agent loop dispatches all tool calls returned in a single LLM response before calling `observe.build_observation` for the next step. Currently `last_action` is a single `dict | None` variable that is overwritten on each dispatch iteration. When N>1 tool calls arrive in one response (e.g. `goto` then `read`), only the last overwrite reaches the observation — the model cannot see what the earlier tool calls did. This loss is silent and may cause the model to repeat work it already completed.

The change affects three files: `loop.py` (accumulation), `observe.py` (signature + key name), and `trace.py` (`ObservationEvent` field). All three are covered by existing tests that must be migrated and extended.

## Goals / Non-Goals

**Goals:**
- Every action dispatched within a single LLM response step reaches the next observation as an ordered list.
- Outcome (`"ok"` / `"error"`) and optional `"error"` string are preserved per action entry.
- Single-tool-call steps produce a length-1 list — no regression.
- Existing tests remain green with key name migrated from `last_action` to `last_actions`.
- Round-trip through `ObservationEvent` JSON is preserved.

**Non-Goals:**
- Changing the `last_action` dict shape (keys remain `tool`, `intent`, `outcome`, `error?`).
- Adding per-action screenshots or timing.
- Changing how `done`/`fail` actions are handled (they exit immediately, no list needed).
- Back-compat alias: `last_action` (singular) is not kept in the observation dict — one clean rename.

## Decisions

### D1: Shape — `last_actions: list[dict]` (no back-compat alias)

**Chosen**: Replace `last_action: dict | None` in the observation dict with `last_actions: list[dict]`. Empty list `[]` when no actions were taken (first step or step with no dispatched actions).

**Alternatives considered**:
- `last_action` (latest) + `prior_actions: list` — keeps back-compat for callers that only read `last_action`, but splits related data into two keys, complicating observation parsing.
- `last_actions: list | None` — `None` vs `[]` is an unnecessary distinction; `[]` is cleaner.

**Rationale**: A single canonical key is simpler. No external consumer currently reads `last_action` from the observation JSON (it's only used by the LLM prompt and tests). A clean rename avoids dual-key ambiguity.

### D2: Accumulation — reset list per step, append per dispatch

**Chosen**: At the top of each loop iteration, reset `last_actions = []`. Append one dict per successful dispatch. Pass the complete list to `build_observation` after the dispatch loop.

**Rationale**: Matches the semantic "actions taken since the previous observation" exactly. No state bleeds between steps.

### D3: `ObservationEvent.last_actions` — optional field with default `[]`

**Chosen**: Add `last_actions: list[dict] = []` to `ObservationEvent`. This is additive — existing event construction that omits the field still validates.

**Rationale**: Existing `TraceWriter` tests construct `ObservationEvent` without `last_actions`; keeping a default avoids breaking them unnecessarily. The field is still serialized in JSON.

### D4: `build_observation` signature — rename parameter

**Chosen**: Change `last_action: dict | None` to `last_actions: list[dict]`. Internally the observation dict emits `"last_actions"` instead of `"last_action"`.

**Rationale**: Single call site in `loop.py`; no other callers. Rename is safe.

## Risks / Trade-offs

- **Observation key rename breaks existing tests** → All tests that assert on `obs["last_action"]` must be migrated to `obs["last_actions"]`. The test suite is the full list of affected callsites; grep confirms `last_action` appears in `test_observe.py` and `test_loop.py`.
- **LLM prompt content changes** → The model will now see `"last_actions": [...]` instead of `"last_action": ...`. This is a prompt-surface change but the model is not trained on this codebase's observation format, so no fine-tuning risk.
- **Empty list on first step** → Previously first step had `last_action: null`. Now it has `last_actions: []`. Tests asserting `is None` must change to `== []`.

## Migration Plan

1. Write failing tests (red) for: multi-tool `last_actions` list, single-tool length-1 list, empty list on step 1, `ObservationEvent` round-trip with `last_actions`.
2. Rename parameter and key in `observe.py`.
3. Change accumulation in `loop.py`: reset `last_actions = []` per step, append per dispatch, pass to `build_observation`.
4. Add `last_actions: list[dict] = []` to `ObservationEvent` in `trace.py`.
5. Migrate existing test assertions: `last_action` → `last_actions`, `is None` → `== []`.
6. Run `uv run ruff check --fix .` and `uv run pytest`.

No database migration needed (traces are append-only; old events are not rewritten).
