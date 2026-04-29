## Context

`_build_system_prompt(task: str)` currently ignores the case's `expect` dict entirely. `loop()` does not accept it. `_run_case` in `scripts/eval.py` constructs the `loop()` call without forwarding `case["expect"]`. The fix requires threading `expect` from the case down through `_run_case` → `loop()` → `_build_system_prompt`.

## Goal

Append a single human-readable schema line to the system prompt when `expect.schema` is non-empty, so the LLM knows the exact key names required in `done.result`.

## Design Decisions

### Decision 1: Pass `expect: dict | None` (the full dict), not `expect_schema: dict | None` (just the schema sub-key)

**Options:**
- **(a) `expect: dict | None = None`** — pass the full `expect` dict from the case; `_build_system_prompt` extracts `expect.get("schema")` internally.
- **(b) `expect_schema: dict | None = None`** — extract the schema sub-key in `_run_case` before calling `loop()`; narrower surface.

**Decision: (a).** Reasons:
1. `case["expect"]` is the natural unit already carried by `_run_case`; extracting just the schema sub-key adds a transformation that would have to be repeated at every call site.
2. `expect` may gain future validator-aware behavior (e.g. injecting validator semantics into the prompt); passing the full dict avoids a second signature break.
3. Symmetry: `_run_case` calls `run_validators(case.get("expect", {}).get("validators", []), ...)` and passes `expect=case.get("expect")` to `loop()` — same dict, same key, no mismatch.

**Alternative rejected:** Option (b) is narrower but forces a re-break of `loop()`'s signature the moment validator semantics are injected.

### Decision 2: Append schema line after the existing fail-gate paragraph

The current prompt ends with the fail-gate / click-first paragraph. The schema line is appended as a new sentence after that block, before the final implicit newline. This placement ensures:
- The task description and fail guidance come first (highest priority for the LLM).
- The schema constraint is near the end, serving as a "last reminder before the model acts."

The injected line format:
`Your done.result MUST be a JSON object matching this schema: {"answer": "str"}. Required fields: answer.`

This uses the literal word `MUST` (RFC-2119 signal), the JSON-serialized schema (so the LLM sees exact key names and value-type hints), and the sorted list of required keys (redundant with the schema but helps models that skim).

### Decision 3: No change to `api/server.py` in this ticket

`_run_agent` in `api/server.py` currently ignores `task_req.expect_schema`. Plumbing it into `loop()` requires constructing an `expect` dict from `expect_schema` and is a logical follow-on. It is listed as task 9 (optional) to keep this ticket focused on the eval path where the benchmark impact is measured.

## Risks / Trade-offs

- Token overhead: ~20-40 tokens per run (negligible vs. 1K-10K context).
- Default-path safety: `_build_system_prompt(task)` with no `expect` kwarg returns byte-identical output — confirmed by unit test (task 3).
- No new module-level imports required (`json` is already imported in `loop.py`).
