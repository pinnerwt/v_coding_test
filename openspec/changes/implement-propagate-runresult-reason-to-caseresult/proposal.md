## Why

`agent.loop.loop()` correctly sets `RunResult.reason` to one of `RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat", "seconds_budget", "no_progress"]` on every early-termination exit. But `scripts/eval.py:CaseResult` has **no `reason` field**, so the constructor at `scripts/eval.py:310-329` cannot pass it through, and `asdict(CaseResult)` at `scripts/eval.py:411` writes JSON without it. Confirmed by inspecting `task2/benchmark/task2-implement-no-progress-stuck-detection/webvoyager/20260429_200118.json`: `webvoyager-1` shows `status=timeout latency_ms_total=142453` (i.e. exceeded the `budget["seconds"]=120` ceiling), so `loop()` *must* have hit the `if (time.monotonic() - t_loop) >= budget_seconds` branch at `agent/loop.py:803-817` and set `reason="seconds_budget"` — yet the JSON's case keys show no `reason` field at all. This blinds every post-merge `/done_pr` step 1b/1b' diagnosis: "is webvoyager-1 timing out via wall-clock budget, no-progress detector, max_steps exhaustion, or stuck_repeat?" is currently unanswerable from the artifact, and the question matters for picking the next ticket (a wall-clock timeout argues for prompt/path-length reduction; a max_steps exhaustion argues for a converge-to-done heuristic; a no_progress fp-stagnation argues for fingerprint sensitivity tuning).

## What Changes

- Add `reason: str | None = None` field to the `CaseResult` dataclass in `task2/scripts/eval.py`, immediately after the existing `failure_detail` field, so `asdict(CaseResult)` writes a `"reason"` key on every case entry in the benchmark JSON.
- Wire `reason=run_result.reason` into the success-path `CaseResult(...)` construction at `scripts/eval.py:310-329` (the path that runs after `loop()` returns a `RunResult`).
- Leave the exception-path `CaseResult(...)` at `scripts/eval.py:287-297` with `reason=None` (no `RunResult` exists on that path; the case crashed before `loop()` returned).

## Capabilities

### New Capabilities

- (none — this extends an existing spec capability)

### Modified Capabilities

- `eval-runner`: new requirement "CaseResult carries the run_result.reason for terminations that produced a RunResult"; the existing `CaseResult skip_reason field` requirement is unchanged.

## Impact

- **Code**: `task2/scripts/eval.py` — add `reason` field to `CaseResult` dataclass; wire `run_result.reason` into the success-path constructor.
- **Tests**: `task2/tests/` — four new unit tests (seconds_budget propagation; no_progress propagation; succeeded reason=None; benchmark JSON includes `"reason"` key on every case dict).
- **Specs**: `openspec/specs/eval-runner/spec.md` — delta applied from this change's `specs/eval-runner/spec.md`.
- No changes to `agent/loop.py`, no new external dependencies.
- Downstream effect: the next post-merge benchmark JSON will have a populated `reason` field on every failed/timeout case; `/done_pr` step 1b' can read it directly when computing per-case regression deltas, removing a class of measurement-blind ticket-selection failures.
