---
name: "Update Agent2"
description: Restart the live Task 2 /sessions server in tmux, drive the ask_user_test_set against it, read each SSE trace end-to-end, verify that thinking/action/answer are all correct (not just that ask_user fired), and overwrite task2/issues.md with the findings. Use when the user asks to "test the served agent", "run the ask_user smoke", or "find issues in the deployed agent".
category: Evaluation
tags: [task2, qualitative-eval, smoke, ask_user]
---

A qualitative pass over the served Task 2 agent. The goal is not a green/red number — it is a written diagnosis grounded in real SSE traces. Every claimed pass must be backed by reading the trace and confirming all three of: planner thinking, action sequence, final answer.

## When to use

- User asks to "restart the server and run the test set / ask_user cases".
- User asks for "issues in the live agent" / "what is the served agent doing wrong".
- After a non-trivial change to `agent/plan.py`, `agent/loop.py`, or `api/sessions.py`, before touching benchmark numbers.

Do **not** use this skill for:
- Quantitative pass-rate measurement → use `/score` and `scripts/bench.py`.
- A code review of the diff → use `/review_task2`.
- TDD on a ticket → use `/new_task2`.

## Inputs and assumptions

- A tmux session named `task2` exists with a shell in the `task2/` working directory. Verify with `tmux list-sessions`. If absent, ask the user before creating one (could collide with their workflow).
- Local LLM is up at `http://localhost:8090` (Qwen3.5 27B, OpenAI-compat). Verify with `curl -s http://localhost:8090/v1/models | head`.
- Server is intended to be restarted in-place — do **not** spawn a second uvicorn on the same port.
- Datasets (`task2/eval/cases/ask_user_test_set.md`) are immutable per memory rule. Never edit cases to make the agent pass.

## Steps

### 1. Restart the server

```bash
tmux send-keys -t task2 C-c
tmux send-keys -t task2 "uv run uvicorn api.server:app --host 0.0.0.0 --port 40781" Enter
```

Wait briefly, then `tmux capture-pane -t task2 -p | tail -10`. Confirm `Uvicorn running on http://0.0.0.0:40781`. If the port is held by a zombie process, ask before `kill -9`-ing it.

Confirm liveness with one HTTP probe:

```bash
curl -s http://localhost:40781/sessions/nonexistent
# expect: {"detail":"not found"}
```

### 2. Drive the cases via HTTP

Use the live `/sessions` API. Do **not** import `agent.loop` directly — the point of this skill is to exercise the deployed surface end-to-end (browser, LLM, locator, SSE).

Default subset (manual smoke, ~12 min on Qwen3.5-27B):
- **A1** — `Book a table at Inparadise (旭集) for noon next Saturday.` (canned answer: `天母店 (Tianmu)`)
- **A3** — `Book a flight from Taipei to Tokyo and return the cheapest fare.` (canned: `December 15, 2026, one-way`)
- **A6** — `Find the best ramen restaurant in Tokyo on Google Maps.` (canned: `highest-rated by Google reviews, in Shinjuku`)
- **U1** — `Tell me the name of the Turing Award winner in 2018.`
- **U4** — `Find the abstract of the paper 'Attention Is All You Need' on arXiv.`

(The doc's own "manual smoke" is A1+A3+U1+U4. Add A6 for superlative-gating coverage. Run the full 8+8+3 only when the user asks for the full suite — it is ~60 min.)

The runner lives in-repo at `task2/scripts/run_ask_user_http.py`. Run it with `OUT_DIR=task2/benchmark/<branch-slug>/ask_user_smoke uv run python scripts/run_ask_user_http.py` so evidence lands in-repo. The runner uses a per-slot keyword map (`CASES[i].answers`) to pick a contextually-correct canned reply for each `ask_user` question, with a case-level `default` for unmatched questions. If a case starts asking new slots that the map doesn't cover, extend the map in that file rather than swapping the case.

If the runner is missing, reproduce its core loop:

1. `POST /sessions {task}` → `run_id`
2. Open `GET /sessions/{run_id}/events` (SSE stream).
3. For each `data:` line, parse JSON. On `type=ask_user`, pick the canned reply by keyword-matching the question text, then `POST /sessions/{run_id}/answer {answer: <reply>}`. On `type=terminal`, break.
4. Dump every event to `task2/benchmark/<branch-slug>/ask_user_smoke/<case_id>.json` so the evidence is in-repo, not in `/tmp`.
5. Hard timeout per case: 360 s.

Run cases sequentially, not in parallel — one browser, one LLM, and the harness depends on per-run SSE order.

### 3. Read the traces — verify thinking, action, answer

This is the part that distinguishes this skill from a benchmark script. **Do not** report a case as PASS based only on `terminal.status` or "ask_user fired/didn't fire". For each case, read the saved JSON and check all three:

- **Thinking** — the `kind=plan` events. Did the planner gate on ambiguity correctly? Were the steps coherent? Were `ask_user` questions focused on one slot?
- **Action** — the `kind=act` event sequence. Did the agent execute its own plan, or skip steps? Did `goto`s lead somewhere useful, or did it bounce between search engines? Did `read` errors get recovered properly?
- **Answer** — the `terminal.result` and `terminal.evidence`.
  - Is the result *factually* correct? Sanity-check against world knowledge (e.g. 2018 Turing Award is Bengio/Hinton/LeCun).
  - Does the evidence text snippet actually support the answer, or is it a UI button label, a homepage carousel, or a generic widget?
  - Does `result.status` (if present) say `"unable_to_complete"` / `"failed"` while `terminal.status="done"`? That is a silent false-positive — call it out.

Watch for these specific failure modes (seen in prior runs of this skill):

| Symptom | Trace tell | Real diagnosis |
|---|---|---|
| Same `ask_user` question N times in a row | N `ask_user` events with near-identical text after a non-matching answer | Loop doesn't track "already asked, answer was off-topic" — should default once, not re-ask |
| Bundled question | One `ask_user` text contains "and" / multiple "?" | Planner not enforcing one-slot-per-ask |
| Bogus `done` | `done` follows a `read` with `outcome=error`, OR plan_cursor far behind plan length | Agent declaring success on stale data |
| `done` with self-failed result | `terminal.status="done"` but `result.status` ∈ {`unable_to_complete`, `failed`, `blocked`} | Loop not honoring agent's own failure self-report |
| Locale-brittle locator | `fail` reason mentions "character encoding" / "Chinese characters" / a CJK label | Locator pipeline can't handle CJK DOM text |
| Trace gap | Step ids jump (e.g. step-1 → step-6) with no events between | Internal locator retries silent — debuggability hole |
| Wasted hops | `goto` to a search engine followed immediately by `goto` elsewhere with no `read` in between | Agent overplanning; one wasted action per case |

For each case write a short verdict block:

```
### <case_id> — <task summary> — <PASS / FAIL / PARTIAL>
- Thinking: <one line, with concrete trace evidence>
- Action: <one line, naming the actual tool sequence>
- Answer: <one line, factual check of the result + evidence>
```

`PARTIAL` is for cases where the system flagged `unverified` correctly but the user-visible result is misleading — that is still a real bug.

### 4. Overwrite `task2/issues.md` with the findings

The deliverable is a single markdown file at `task2/issues.md`, **overwritten in full** each run — not appended to. The point is the current state of open issues from the latest smoke; stale verdicts from previous rounds are noise. If issues from a prior round are still open, re-state them in the new file with refreshed evidence; if they were fixed, drop them.

Structure:

1. **Header** — one paragraph naming the round and pointing at the in-repo trace directory (`task2/benchmark/<branch-slug>/ask_user_smoke/round<N>/`).
2. **Per-case verdict table** — one row per case (`case`, `expected ask`, `asked`, `terminal`, `result_quality`, `t_s`).
3. **Per-case verdict blocks** — the `### <case_id> — <task summary> — PASS/FAIL/PARTIAL` block from step 3, with Thinking / Action / Answer bullets for failed cases. Skip narration for clean PASSes; one line is enough.
4. **Issue sections** — one section per issue, ordered by severity. Each section:
   - Title: `## I<N> — <one-line description>`.
   - Severity: P1 / P2 / P3.
   - Evidence: bullet list pointing at the in-repo trace JSONs (not `/tmp/`).
   - Diagnosis: 1–3 sentences naming the likely faulty code path (e.g. `agent/plan.py`'s info-sufficiency heuristic, `agent/loop.py`'s `_handle_done`). For carry-over issues that have since been fixed, mark the title `(FIXED)` and keep the diagnosis + reference to the regression test.
5. **Lower-severity observations** — single bulleted list at the bottom for things not worth a separate ticket but worth tracking.
6. **Cross-cutting note** if the harness itself revealed a spec gap.

Do **not**:
- Open tickets unless the user explicitly asks. The user has historically said "just write to issues.md" — respect that.
- Edit `ask_user_test_set.md` or any benchmark dataset — immutable.
- Pre-seed specific domains in any prompt fix proposal (per memory `feedback_no_preseeding_domains.md`). Phrase fixes as page-shape rules, not site-specific recipes.

### 5. End-of-turn summary

Two sentences: which cases ran, which issues are now in `task2/issues.md` (I1 / I2 / …), and where the evidence lives. Offer next-step actions only if a clear one exists (e.g. "Want me to file I1 and I2 as tickets?"); otherwise stop.

## Common mistakes to avoid

- **Calling something PASS without reading the trace.** If you only inspect `summary.terminal.status`, you will miss A3-style bogus successes and A1-style status/result mismatches. The user has called this out: "verify that thinking, action, and answer are all correct."
- **Re-running the failing case immediately to see if it flakes.** It does flake (live web, live LLM, sampling). One run is the single sample; document it. Re-running to "see if it passes" wastes time and gives a false sense of stability.
- **Importing `agent.loop` directly to "skip the server".** The whole purpose of this skill is to exercise the deployed surface. Direct-import skips SSE, the session worker, the streaming trace writer, and the answer-queue plumbing — exactly the seams where bugs hide.
- **Drowning fix proposals in narration.** Keep each F<N> ≤ 25 lines. The reader is the next agent that will implement the fix; they want concrete file paths, not an essay.
- **Suggesting site-specific fixes.** Memory rule: agent is generalized. Never write "if booking, do X; if Apple, do Y". Always rephrase as "if page exhibits Y shape, do Z".
