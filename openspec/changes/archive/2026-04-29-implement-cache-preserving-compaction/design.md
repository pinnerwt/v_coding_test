## Context

`_compact_messages` (`task2/agent/loop.py:174`) is invoked once per loop step before the LLM call when the serialized message list exceeds `LLM_CONTEXT_CHAR_BUDGET` (default 80,000 chars). Today it walks indices `1..n-1` and rewrites the `content` field of state messages and tool messages to fixed elision sentinels, preserving the system message and the most-recent state message.

The local Qwen 27B endpoint at `http://localhost:8090` performs prefix-cache lookup on every chat completion — a request whose tokenized prefix is byte-identical to a prior request avoids re-prefilling. Mutating `messages[i].content` of a previously-sent message breaks the prefix match and forces a full re-prefill of the kept tail. Observed wall-clock impact: per-step latency jumps from ~5-12s to ~28-31s starting at the step where compaction first fires (~step 12 on `webvoyager-1`).

## Goals / Non-Goals

**Goals:**
- Make `_compact_messages` cache-friendly: the kept-tail of consecutive compactions must be byte-identical, so the LLM server's prefix cache survives across steps.
- Preserve the existing two invariants: (1) the system message is never dropped; (2) the most recent state message is never dropped.
- Same external signature, same call site, same return type.

**Non-Goals:**
- Tuning `LLM_CONTEXT_CHAR_BUDGET` itself.
- Implementing summarization of dropped messages.
- Verifying the prefix cache exists on every backend; the change is correct (and a tiny win) on backends without prefix cache, and a large win on those with.
- Changing the loop, planner, or any other agent-loop semantics.

## Decisions

### Drop oldest, preserve newest tail

Replace the in-place rewrite with a contiguous-prefix drop: keep `messages[0]` (system), and the most recent K messages such that their total serialized length fits the budget. Never drop the most-recent state message (so the planner still has the live observation).

**Why:** the prefix cache invariant is "what was sent before is sent again unchanged at the same positions." A drop of the *oldest* messages shifts surviving messages to lower indices but keeps their content byte-identical to what was sent on the prior step (modulo the same shift). On most KV-cache implementations the cache key is the token sequence, not the message-array index — so the kept tail's tokens still match a previously seen prefix when re-prefilled into the new request.

**Alternatives considered:**
- **Truncate trailing characters of old messages**: also breaks prefix cache and loses semantically critical content (URLs, tool call ids).
- **Replace old content with a single summary message**: introduces non-determinism (depends on summarizer), adds an LLM round-trip, and still mutates positions over time.
- **Keep current `<elided>` sentinels**: original problem.

### What "drop" means concretely

Walk from index 1 forward until the budget fits, removing whole messages. Constraint: do not drop the most-recent state message. Implementation:

1. Find `last_state_idx` (rightmost state message; same as today).
2. Build a candidate "drop set" starting at index 1, advancing rightward, stopping before `last_state_idx`.
3. Each drop subtracts `len(json.dumps(messages[i]))` (plus 2 for the JSON list separator, but since we serialize once at the end the exact arithmetic uses the post-drop sum).
4. Continue until either the budget fits or only `[system, last_state]` remain.
5. Return the filtered list. If even `[system, last_state]` exceeds budget, return them anyway — truncating either of those would break correctness, and the LLM is responsible for handling oversize prompts in that pathological case (today's elision-based code has the same pathological-case behavior).

### Test surface

Three unit tests pinned to the new contract:

1. **Byte-identity of kept tail.** Construct an oversized message list. Call `_compact_messages`. Assert every message in the result is `is`-equal (or `==`-equal with no `<elided>` substring) to a message in the input.
2. **Prefix stability across consecutive calls.** Compact list `L1` → result `R1`. Append a new state+tool pair to `L1` to produce `L2`. Compact `L2` → result `R2`. Assert there exists a position `k` such that `R2[1:k]` is a contiguous tail of `R1[1:]` (meaning: dropping more from the front + appending at the back preserves the in-the-middle messages byte-identically).
3. **System and last-state preserved.** Construct a list where every non-system, non-last-state message could be dropped. Assert `result[0]` is the system message and the final state message is in `result`.

### Removal of dead constants

`_ELIDED_STATE_CONTENT` and `_ELIDED_TOOL_CONTENT` are unused after the rewrite — delete them.

## Risks / Trade-offs

- **[Risk] Loss of historical context degrades planner behavior.** The current code keeps stub markers ("Current state: <elided>") so the planner sees a positional placeholder. Dropping messages removes the placeholder. → **Mitigation:** the planner already reasons primarily off the *most recent* state and the *plan progress* preamble, both of which are preserved. The elided shells in the prior implementation carried zero information by construction (literal sentinel strings); their disappearance is informationally equivalent to their elision.

- **[Risk] Pathological case where `[system, last_state]` already exceeds the budget.** → **Mitigation:** the prior implementation had the exact same pathological case (it could not elide the system message or the last state). Behavior is unchanged in that boundary.

- **[Risk] Prefix cache is implementation-dependent — Qwen at localhost:8090 today, but Zeabur backend tomorrow.** → **Mitigation:** the cache-friendly behavior is a strict superset of the cache-blind correctness; backends without a prefix cache see no regression (slightly fewer tokens, same correctness).

- **[Trade-off] Tests asserting `<elided>` content presence will be removed.** → Acceptable; those tests pinned the *implementation* of compaction, not its contract.

## Migration Plan

Single PR. No deploy gate, no flag — the old behavior is strictly worse on any backend that has a prefix cache, and equivalent on any that doesn't. Rollback is a `git revert`.

## Open Questions

None blocking. Empirical confirmation of the latency cliff disappearing on `webvoyager-1` is the success metric, recorded by `/done_pr` step 1a's WebVoyager run.
