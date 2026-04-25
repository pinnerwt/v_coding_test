## Why

Tickets #1–#8 have delivered all the building blocks — LLM client, browser primitives, a four-tier locator pipeline, locator cache, and failure-classifying supervisor — but nothing yet composes them into a running agent. Ticket #9 closes that gap: `loop.py` wires observe → decide → act → observe so the agent can actually complete a task end-to-end. Without the loop, every upstream module is untested in composition and the system cannot be deployed or demonstrated.

## What Changes

- Add a new module `task2/agent/loop.py` that:
  - Accepts a natural-language task string, a `Browser` instance (already open), and an `LLMClient` (or configurable `base_url` / `model`).
  - Implements the observe → choose tool → act → observe cycle.
  - Exposes three LLM tool calls to the model: `goto(url)`, `read(intent?)`, and `done(result, evidence)`. These are the minimal set required to make a 2-step happy-path test pass. `fail(reason)` is also included so the LLM has a clean exit for blocked tasks.
  - Is bounded by a `max_steps` parameter (default 20) to prevent infinite loops.
  - Returns a `RunResult` dataclass with `status` (`"succeeded"` | `"failed"` | `"timeout"`), `result`, and `evidence` fields.
  - Treats `done(result, evidence)` as the success terminal: if evidence is present (URL + text snippet), the run exits `succeeded`. If evidence is absent/empty, this ticket's happy path does not need to handle it (that is ticket #11); minimal guard is sufficient.
- Add a new fixture `task2/tests/fixtures/loop_happy_path.html` — a minimal 2-page local fixture used by the happy-path test (step 1: navigate; step 2: read a value and call `done`).
- Add `task2/tests/agent/test_loop.py` with the happy-path acceptance test: a 2-step task against the local fixture completes with `status="succeeded"` and non-empty evidence.
- No changes to `agent/llm.py`, `agent/browser.py`, `agent/locate.py`, `agent/locator_cache.py`, `agent/supervisor.py`.

## Capabilities

### New Capabilities

- `agent-loop`: The observe→decide→act loop that drives the LLM tool-calling cycle. Core contract: the loop drives a task to completion (via `done(result, evidence)`) or to a bounded failure (via `fail(reason)` or step-count exhaustion). For this ticket, only the happy path (2-step task, `done` with valid evidence → `succeeded`) is required.

### Modified Capabilities

(none — no existing spec-level requirement changes)

## Impact

- **Code**: new `task2/agent/loop.py`; new `task2/tests/agent/test_loop.py`; new `task2/tests/fixtures/loop_happy_path.html`.
- **Dependencies**: none new. The loop composes existing modules (`agent.llm`, `agent.browser`, `agent.locate`) with no additional packages.
- **Existing modules**: `agent/llm.py`, `agent/browser.py`, `agent/locate.py`, `agent/locator_cache.py`, `agent/supervisor.py` unchanged.
- **Future tickets**: ticket #10 (self-correction) wires the supervisor into `loop.py`; ticket #11 (silent-failure guard) adds the unverified-evidence branch; ticket #12 (trace writer) adds full event persistence. Those paths are deliberately absent from this ticket.
