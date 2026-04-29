## Context

`_build_system_prompt(task: str)` currently ignores the case's `expect` dict entirely. `loop()` does not accept it. `_run_case` in `scripts/eval.py` constructs the `loop()` call without forwarding `case["expect"]`. The fix requires threading `expect` from the case down through `_run_case` → `loop()` → `_build_system_prompt`.

## Design Decisions

### Decision 1: Pass `expect: dict | None` (the full dict), not `expect_schema: dict | None` (just the schema sub-key)

**Options:**
- **(a) `expect: dict | None = None`** — pass the full `expect` dict from the case; `_build_system_prompt` extracts `expect.get("schema")` internally.
- **(b) `expect_schema: dict | None = None`** — extract the schema sub-key in `_run_case` before calling `loop()`; narrower surface.

**Decision: (a).** Reasons:
1. `case["expect"]` is the natural unit already carried by `_run_case`; extracting just the schema sub-key adds a transformation that would have to be repeated at every call site.
2. `expect` may gain future validator-aware behavior (e.g. injecting validator semantics into the prompt); passing the full dict avoids a second signature break.
3. Symmetry: `_run_case` calls `run_validators(case.get("expect", {}).get("validators", []), ...)` and passes `expect=case.get("expect")` to `loop()` — same dict, same key, no mismatch.

### Decision 2: Append schema line at the end of the existing prompt

The schema line is appended after the existing fail-gate / click-first paragraph so it serves as the last instruction the model sees before acting. The line uses the literal word `MUST` (RFC-2119 signal), `json.dumps(schema)` (exact key names and value-type hints), and a sorted list of required keys (redundant with the schema but helps models that skim).
