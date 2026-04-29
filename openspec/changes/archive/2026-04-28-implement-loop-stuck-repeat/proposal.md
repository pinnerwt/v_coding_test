## Why

After PR #101 fixed the Qwen HTTP 400 crash via `_compact_messages`, the webvoyager-1 case ("List the latest version of Python") stopped crashing but now burns the full 20-step budget without converging: cost +160% ($0.1551 → $0.4023), prompt tokens +164% (149,389 → 393,771), p50/p95 latency +170% (145s → 390s) across the 3-case suite. The agent has no early-termination heuristic and loops to `max_steps` even when the LLM is emitting byte-identical tool calls step after step.

## What Changes

- In `agent/loop.py`, maintain a rolling buffer of the last K=3 `(tool_name, serialized_args)` tuples emitted by the LLM.
- When the most recent K entries are byte-identical, `loop()` returns `RunResult(status="failed", reason="stuck_repeat")` immediately instead of exhausting `max_steps`.
- Args are canonicalized via `json.dumps(args, sort_keys=True)` so dict-key ordering does not cause false misses.
- `K=3` is defined as a module-level constant `_STUCK_REPEAT_K = 3`.
- The `reason` field is the literal string `"stuck_repeat"`.
- The `RunResult` dataclass gains a `reason: RunResultReason | None = None` field (with `RunResultReason = Literal["stuck_repeat"]`) to carry per-failure context as a closed value set; future failure modes are deliberate additions to the alias.
- Out of scope: the optional AX-tree digest variant from ticket #70 (filed as a follow-up).

## Capabilities

### New Capabilities

_(none — this change extends an existing capability)_

### Modified Capabilities

- `agent-loop`: adds a new requirement for stuck-state early-termination and extends `RunResult` with a `reason` field.

## Impact

- `task2/agent/loop.py` — K-buffer tracking logic + early-exit branch in `loop()`.
- `task2/agent/trace.py` — no change required (`RunResult` lives in `loop.py`, not `trace.py`).
- `task2/tests/agent/test_loop.py` — two new unit tests (positive stuck detection, negative healthy-alternation).
- No API surface changes; `reason` defaults to `None` so all existing callers are unaffected.
- Supervisor coexistence: `_stuck_buf` is cleared whenever the supervisor handles a dispatch (detected via `supervisor.total_attempts()` increasing across the dispatch), ensuring stuck-detection does not pre-empt the supervisor's locator-escalation/halt/replan path for `read`-type calls.
