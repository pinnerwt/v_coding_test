## Context

The run JSON at `task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json` contains 13 `step_breakdown` entries for webvoyager-1. Each entry already carries `latency_breakdown_ms.llm_ms`, `latency_breakdown_ms.observation_ms`, `latency_breakdown_ms.dispatch_ms`, and `prompt_tokens`. The data is complete; the only missing piece is a formal assertion and a documented lever ranking.

Lever analysis from the raw numbers:

- **Step-1 observation cost**: 12,380ms — a one-time AX-tree build + playwright `waitForLoadState`. Cutting 6s here saves ~5% of total (6/127).
- **LLM cost per step**: median ~5.6s (steps 2-12), peak 29.9s at step 13. Sum ≈ 105s across all 13 steps (~102s on steps 2-13). A 30% prompt cut reduces this by ~31s → total wall-clock ≈ 96s, comfortably under 120s.
- **Path-shortening**: 13 steps × ~6.5s avg = ~84s LLM cost. Saving 3 steps saves ~20s → total ≈ 107s, borderline under 120s.
- **Prompt growth**: `prompt_tokens` grows from 1,084 (step 1) to 21,522 (step 13) — a 20× accumulation. Steps 6-13 average ~16,000 tokens each. The per-step LLM cost is highly correlated with prompt size.

Decision: **prompt-trim is the winning lever** because (a) it is the largest single source of variability (prompt growth explains the 29.9s step-13 spike), (b) a 30% cut would bring total wall-clock from 127s to ~100s with margin, and (c) the implementation surface is isolated to context management in `agent/loop.py` or the prompt assembly, with no browser/network changes required.

## Goals / Non-Goals

**Goals:**
- Write a single read-only pytest test that proves the LLM-dominance assertion against the existing artifact.
- Embed the full lever ranking and winner in the test's docstring so the next ticket-selector has machine-readable evidence.
- File a tier-5 ticket for prompt-trim.

**Non-Goals:**
- Implementing prompt-trim, observation-trim, or path-shortening (those are follow-on tickets).
- Running additional benchmark runs or modifying any production agent code.
- Adding a dedicated analysis script or notebook.

## Decisions

**Decision: one test file, one test function.**
The ticket names exactly one test. Creating a dedicated `test_benchmark_analysis.py` avoids coupling with `test_benchmark.py` (which tests script behavior) and `test_bench.py` (runner integration). The file is static — it reads the vendored artifact by absolute path relative to the repo root.

**Decision: assert `llm_ms > 5 * dispatch_ms` on every step from index 1 onward (multiplicative form), not just the median.**
The ticket spec says "median step," but a per-step assertion is strictly stronger and was free to write. Steps 2-13 have `llm_ms` in the range 4,619–29,931ms (step 13 is the 29.9s spike) and `dispatch_ms` in 45–639ms, giving ratios from 10× to 145×. A threshold of 5 is well below the minimum observed ratio, making the test robust to minor model speed changes while still documenting the dominance. The multiplicative form (`llm_ms > 5 * dispatch_ms`) avoids `ZeroDivisionError` if a future cached step records `dispatch_ms == 0`.

**Decision: also assert `prompt_tokens` growth to document lever (a).**
The docstring needs to justify the prompt-trim lever. Adding an assertion that `prompt_tokens` at the final step is at least 10× the prompt_tokens at step 1 is a lightweight invariant that encodes the growth pattern without being fragile.

**Decision: follow-up ticket filed as `task2/tickets/active/097-prompt-trim-webvoyager-1.md`.**
ID 97 is the next sequential ID after 96 (the diagnostic). This is a `docs(task2):` action — the ticket file is a markdown document, not code.

## Risks / Trade-offs

- [Risk: artifact path hardcoded in test] The test must reference the specific benchmark run JSON by path. If the directory is renamed, the test breaks. Mitigation: use `pathlib.Path(__file__).parents[1] / "benchmark" / "task2-propagate-runresult-reason-to-caseresult" / "webvoyager" / "20260429_203237.json"` so the path is relative to the test file within the `task2/` tree (`tests/test_benchmark_analysis.py` → `parents[1] == task2/`).
- [Risk: run artifact deleted or overwritten] The benchmark JSON is checked into the repo as evidence. It is not regenerated on CI; the test is a static assertion against a committed artifact. No mitigation needed beyond the existing git history.
- [Risk: lever ranking stale after future runs] The docstring captures the ranking for this single run at this point in time. The next tier-5 ticket should supersede the diagnostic. Acceptable for a tier-4 ticket.
