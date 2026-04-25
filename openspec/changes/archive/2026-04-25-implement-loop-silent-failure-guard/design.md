## Context

Tickets #9 (loop happy path) and #10 (loop self-correction) are complete. The loop's `done` handler (in `loop.py`, inside the `for tool_call in response.tool_calls` dispatch block) currently does this:

```python
if tool_call.name == "done":
    return RunResult(
        status="succeeded",
        result=args.get("result"),
        evidence=args.get("evidence"),
    )
```

It returns `"succeeded"` unconditionally, regardless of whether `evidence` is present, well-formed, or completely empty. From `task2/plan.md` (Silent-failure prevention): `done(result, evidence)` requires structured evidence (URL, visible text snippet, screenshot region) — without it the run is marked `unverified`, not `success`.

This ticket implements the first of those three checks: the mandatory-field guard. The `screenshot_ref` field is listed in the plan's `DoneEvent` shape as part of the evidence structure, but its presence cannot be validated without the screenshot-diff feature (a separate future ticket). The minimum required fields for this ticket are `url` and `text_snippet`.

The trace schema in `plan.md` specifies that `DoneEvent` includes `verifier: { ok: bool, reasons: string[] }`. `RunResult` must carry this verdict so callers (and the future trace writer) can inspect it.

## Goals / Non-Goals

**Goals:**

- When `done` is invoked with `evidence` missing entirely (absent from args), or with `evidence={}`, or with `url` or `text_snippet` absent/empty/non-string, `RunResult.status` is `"unverified"`.
- When `done` is invoked with `evidence` containing both `url` (non-empty string) and `text_snippet` (non-empty string), `RunResult.status` remains `"succeeded"`.
- `RunResult` gains a `verifier: dict | None` field that holds `{ok: bool, reasons: list[str]}` for `done` exits, and `None` for `fail`/`timeout` exits.
- Two new tests in `test_loop.py`: one red-first (no evidence → `unverified`), one regression guard (valid evidence → `succeeded`, `verifier.ok=True`).
- `RunStatus` type alias gains `"unverified"`.
- Pre-commit gate (`ruff format . && ruff check . && pytest`) stays clean.

**Non-Goals:**

- Validating `screenshot_ref` presence (requires screenshot-diff feature — separate ticket).
- Result schema validation (declared output keys present and well-typed — separate ticket).
- Final-state screenshot diff (separate ticket).
- Changing the `done` tool's JSON schema exposed to the LLM (it already documents `url` and `text_snippet` as required; no change needed).
- Any changes to `browser.py`, `locate.py`, `supervisor.py`, `llm.py`, `locator_cache.py`.

## Decisions

### Decision 1: Mandatory evidence fields — `url` and `text_snippet` only

The plan lists the full `DoneEvent.evidence` shape as `{ url, text_snippet, screenshot_ref, ax_path? }`. For this ticket, only `url` and `text_snippet` are treated as mandatory. `screenshot_ref` is listed in the trace schema but its validation requires the screenshot-diff feature (a separate ticket). `ax_path` is explicitly optional (`?`). Requiring only `url` + `text_snippet` at this stage is the most defensible minimal interpretation: it matches what `done` tool's JSON schema already marks as `required`.

**Alternative considered**: require `screenshot_ref` as well. Rejected because validating it without the screenshot-diff feature would be a dead check (we'd accept any string, including an empty one), adding no real safety. Deferring cleanly avoids half-measures.

### Decision 2: Validity check — non-empty string for each required field

A field is "present and valid" if and only if: it exists in the evidence dict, its value is a `str`, and its value has at least one non-whitespace character. An empty string or a string of only spaces is treated as absent. This is the minimum bar — it rules out the most common LLM silent-failure patterns (empty dict, `{"url": "", "text_snippet": ""}`).

### Decision 3: `RunResult` gains `verifier: dict | None` — defaults to `None`

`RunResult` is a frozen dataclass. Adding `verifier: dict | None = None` as the last field (with a default) is backward-compatible: existing constructors that don't pass `verifier` still work. The `verifier` dict shape is `{"ok": bool, "reasons": list[str]}` — mirroring `DoneEvent.verifier` in the trace schema. For `fail` and `timeout` exits, `verifier` remains `None` (no evidence check was performed).

**Alternative considered**: a dedicated `Verifier` dataclass. Rejected — the trace schema uses a plain object; a plain dict keeps `RunResult` simpler and aligns with JSON serialization downstream. If the verifier grows complex, it can be promoted later.

### Decision 4: `RunStatus` gains `"unverified"` — distinct from `"succeeded"` and `"failed"`

The plan's `Run.status` enum is `"succeeded" | "unverified" | "failed" | "blocked" | "timeout"`. The loop currently only uses `"succeeded" | "failed" | "timeout"`. Adding `"unverified"` is additive and non-breaking. The `Literal` type alias `RunStatus` in `loop.py` is updated to include it.

### Decision 5: Evidence check lives in `loop.py` `done` handler — not a separate helper module

Scope is deliberately minimal. The check is a few lines of Python; extracting it to `agent/evidence.py` or similar would create an abstraction with exactly one caller. Per the repo's CLAUDE.md principle: "Don't introduce abstractions for hypothetical second callers." A private helper function `_check_evidence(evidence: dict | None) -> dict` inside `loop.py` keeps it local and discoverable.

### Decision 6: Test strategy — no new fixture required

Both new tests (`test_loop_done_without_evidence` and `test_loop_done_with_valid_evidence`) use the existing `loop_happy_path.html` fixture via `fixture_server`. The first test drives the LLM to call `done` with `evidence={}` after a `goto`. The second is a light regression guard that duplicates the happy-path shape but also asserts `result.verifier["ok"] is True`. No new HTML is needed.

## Risks / Trade-offs

- **Existing `test_loop_happy_path` does not assert `verifier`** — it will still pass because `verifier` defaults to `None` for existing callers that don't pass it. However, after this change, `test_loop_happy_path` will get `verifier={"ok": True, "reasons": []}` in the result (since the evidence is valid). The test doesn't assert on `verifier`, so it stays green. The new `test_loop_done_with_valid_evidence` is the explicit regression guard.
- **`RunStatus` type alias broadens** — any downstream code that pattern-matches on `RunStatus` (e.g. `if result.status == "succeeded"`) must now handle `"unverified"` explicitly or its branch will silently miss it. At this stage, only `loop.py` and tests produce `RunResult`; the API server (`api/server.py`) is not yet wired to `loop.py` in this ticket, so the blast radius is contained.
- **LLM may learn to pass trivial evidence** — e.g. `{"url": "http://example.com", "text_snippet": "x"}`. The guard catches empty evidence but not semantically meaningless evidence. The screenshot-diff feature (future ticket) addresses the semantic gap.

## Open Questions

(none — all decisions resolved above)
