# Task 2 — Generalized Browser Automation Agent

## Goal

A service that takes a **natural-language task** ("find the most-cited paper on X on arXiv and return title + authors") and reliably executes it across diverse sites. Reviewers will hit our deployed Zeabur endpoint with **unseen tasks**, so the bar is "generalizes," not "passes our own eval."

The two non-negotiable axes from the brief:

- **Self-correction** — on failure, *diagnose the cause* and try a *different strategy* (not blind retry).
- **Self-maintenance** — detect UI/selector drift, switch locator strategy automatically.

## Non-goals

- Logging into accounts, captcha-solving, anti-bot evasion. If we hit a wall, we report `blocked` and stop.
- Multi-tab orchestration beyond what one task needs.
- Long-running crawls — one task per request.
- Mobile / non-Chromium browsers.

## Architecture

```
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌────────────┐
│ FastAPI  │──▶│ Planner  │──▶│ Agent loop   │──▶│ Playwright │
│  /tasks  │   │  (LLM)   │   │ (tool-using) │   │  browser   │
└──────────┘   └──────────┘   └──────┬───────┘   └─────┬──────┘
                                     │                 │
                              ┌──────▼─────┐    ┌──────▼──────┐
                              │ Supervisor │◀───│  Observer   │
                              │ (classify  │    │ (AX tree +  │
                              │  failure)  │    │  DOM digest)│
                              └────────────┘    └─────────────┘
```

### Components (Python, Playwright, FastAPI)

1. **`agent/llm.py`** — OpenAI-compatible client. Reads `LLM_BASE_URL` (default `http://localhost:8090`), `LLM_MODEL`, optional `LLM_API_KEY`. Per CLAUDE.md, must not hardcode a hosted provider.
2. **`agent/browser.py`** — small Playwright tool surface exposed to the LLM:
   `goto`, `click(intent)`, `type(intent, text)`, `select`, `read(intent?)`, `wait_for`, `back`, `screenshot`, `done(result, evidence)`, `fail(reason)`. **Targets are intents, not selectors** — the LLM names what it wants ("the Submit button"); resolution is `locate.py`'s job.
3. **`agent/locate.py`** — locator pipeline (this is the heart of self-maintenance):
   - **L1** Accessibility tree match (role + accessible name) — primary, drift-resilient.
   - **L2** DOM heuristics (label-for, placeholder, ARIA, text contains).
   - **L3** Semantic rerank — LLM picks among top-K candidate elements given intent + nearby text.
   - **L4** Vision fallback — screenshot + LLM bbox → click via coordinates.
   Each tier returns a confidence; pick the first above threshold. Successful (origin, intent) → resolved AX-fingerprint cached in SQLite; cache invalidates when fingerprint changes.
4. **`agent/observe.py`** — produces a compact, token-efficient observation: trimmed AX tree (interactable nodes only), URL, title, last-action result. Raw HTML never enters the prompt.
5. **`agent/plan.py`** — NL task → ordered step plan. Re-entered when supervisor escalates.
6. **`agent/loop.py`** — observe → choose tool → act → observe. Bounded by step count and USD budget.
7. **`agent/supervisor.py`** — failure classifier + recovery policy (table below). Each branch is a *different strategy*, not the same call retried.
8. **`api/server.py`** — `POST /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/trace`, plus a tiny HTML page to submit a task and watch the trace stream.

### Data stores

- **SQLite** for task records, traces, locator cache. Single file, no external deps.

## Self-correction policy

| Failure mode | Detection | Recovery |
|---|---|---|
| Locator returns 0 matches | `count() == 0` | Next L-tier (L1 → L2 → L3 → L4) |
| Locator returns >1 matches | Ambiguous | LLM rerank with surrounding text + section heading |
| Click had no effect | URL + AX-tree diff before/after is empty | Sweep for overlay/cookie banner first; then alt target |
| Form validation error | Error text node near field | Re-read task constraints, fix offending field, retry |
| Unexpected page after nav | URL/title doesn't match plan expectation | Replan from current state |
| Login wall / captcha | Pattern match (known + LLM check) | Halt with `blocked`; do not attempt bypass |

The escalation ladder caps at 3 strategies × 2 attempts before declaring `failed` with a structured trace.

## Self-maintenance

- **Adaptive locator cache**: `(origin, intent) → ax_fingerprint`. Future runs try cache first; on miss, fall through L1–L4 and refresh the cache.
- **Overlay handler**: pre-action sweep that closes common cookie banners / modals from a small built-in catalog, with an LLM fallback for unknown patterns. Tested against fixtures.
- **Drift fixtures** (see Eval): we author "v1" and "v2" of a page with the same semantics but renamed/moved selectors. The same task must pass both without code changes — that is the actual measurement of self-maintenance.

## Silent-failure prevention

- `done(result, evidence)` requires structured **evidence** (URL, visible text snippet, screenshot region) — without it the run is marked `unverified`, not `success`.
- **Result schema** validation: declared output keys must be present and well-typed. A missing field = `failed`, not `succeeded`.
- Final-state screenshot is diffed against the agent's stated evidence; mismatches downgrade to `unverified`.

## Trace schema (replayable)

Every run produces a trace that is **sufficient to replay the agent's decisions without re-running the live browser**. The LLM side can be re-played deterministically by feeding the recorded observations back in; the browser side can be replayed visually via screenshots. Stored as JSONL (one event per line) in SQLite `traces.events`, plus a header row in `traces.runs`.

### `Run` (one row per task)

```ts
Run {
  run_id: string                      // ULID
  task: string                        // verbatim NL task
  expect_schema?: object              // declared output schema, if any
  budget: { steps: int, usd: float, seconds: int }
  llm: { base_url, model, temperature, seed? }   // identifies the model state
  agent_version: string               // git SHA of the running code
  started_at, ended_at: iso8601
  status: "succeeded" | "unverified" | "failed" | "blocked" | "timeout"
  final: {
    result?: object                   // structured output if any
    evidence?: Evidence               // see done() contract
    failure?: { kind, reason, last_step_id }
  }
  totals: { steps, llm_calls, prompt_tokens, completion_tokens, usd, browser_ms }
}
```

### `Event` (append-only, ordered by `seq`)

Events share `{ run_id, seq, ts, step_id }`. `kind` discriminates:

```ts
ObservationEvent {
  kind: "observation"
  url, title: string
  ax_tree_digest: string              // trimmed AX tree shown to the LLM (the EXACT prompt input)
  ax_fingerprint: string              // hash for drift detection
  screenshot_ref: string              // path / blob id; not inlined
  viewport: { w, h }
}

PlanEvent {                           // emitted by plan.py / replan
  kind: "plan"
  reason: "initial" | "replan"
  steps: string[]                     // ordered NL steps the planner produced
  llm_call_id: string                 // links to the LLMCallEvent
}

DecisionEvent {                       // the LLM's chosen tool call
  kind: "decision"
  intent: string                      // e.g. "click the Submit button"
  tool: "goto"|"click"|"type"|"select"|"read"|"wait_for"|"back"|"screenshot"|"done"|"fail"
  args: object
  rationale: string                   // LLM's stated reason (1–2 lines)
  llm_call_id: string
}

LocateEvent {                         // emitted by locate.py per resolution attempt
  kind: "locate"
  intent: string
  tier: "cache" | "L1_ax" | "L2_dom" | "L3_rerank" | "L4_vision"
  outcome: "hit" | "miss" | "ambiguous" | "error"
  candidates: { ax_role, ax_name, selector, score }[]   // top-K, capped
  chosen?: { selector, ax_fingerprint, confidence }
  cache_action?: "read" | "write" | "invalidate" | null
  ms: int
}

ActEvent {                            // result of executing the tool against the browser
  kind: "act"
  tool, args: ...
  outcome: "ok" | "no_effect" | "nav" | "timeout" | "error"
  diff: { url_changed: bool, ax_changed: bool, error?: string }
  ms: int
}

SupervisorEvent {                     // failure classification + recovery routing
  kind: "supervisor"
  trigger_event_seq: int              // which Act/Locate event tripped it
  classified_as: "LocatorMiss"|"Ambiguous"|"NoEffect"|"FormError"|"NavDrift"|"Blocked"|"Timeout"
  policy: "next_tier" | "rerank" | "sweep_overlay" | "replan" | "halt"
  attempt: int                        // 1..N within this strategy ladder
}

LLMCallEvent {                        // verbatim record of every LLM round-trip
  kind: "llm_call"
  llm_call_id: string                 // referenced by Plan/Decision events
  purpose: "plan"|"decide"|"locate_rerank"|"locate_vision"|"classify_failure"|"verify_evidence"
  model, base_url: string
  prompt: { system, messages, tools? }   // FULL prompt, deterministic replay input
  response: { content, tool_calls?, finish_reason }
  tokens: { prompt, completion }
  usd: float
  ms: int
}

DoneEvent {
  kind: "done"
  result: object
  evidence: { url, text_snippet, screenshot_ref, ax_path? }
  verifier: { ok: bool, reasons: string[] }   // schema + evidence checks
}
```

### Replay contract

- **LLM replay**: given a `Run`, the sequence of `LLMCallEvent.prompt` is the exact input to the model. Re-running with the same `model` + `seed` + `temperature=0` should reproduce `LLMCallEvent.response`. Divergence points are visible per-call.
- **Decision replay**: feed `ObservationEvent.ax_tree_digest` back into `loop.py` in offline mode (no real browser); assert the agent emits the same `DecisionEvent.tool` + `args`. This is how we regression-test prompt/policy changes against historical traces.
- **Locator replay**: `LocateEvent.candidates` + `chosen` is enough to re-rank offline against a new `locate.py` and confirm it would still pick the same element (or do better).
- **Visual replay**: `screenshot_ref` per observation/decision lets a developer scrub through the run in the trace viewer.

### Trace viewer

`GET /tasks/{run_id}/trace` returns the JSONL stream; the small HTML page renders it as a timeline (observation → decision → locate → act → supervisor) with screenshots inline. This is the primary debugging surface — referenced from every failed eval case in `eval/results/`.

### What we deliberately do NOT store

- Raw HTML of pages (too large; AX digest is the canonical observation).
- Cookies / auth tokens / user-typed secrets — redacted before write.
- LLM internals beyond what the API returns.

### Storage & retention

- Default retention 30 days; eval-set runs flagged `pinned=true` are kept indefinitely. Screenshots in object storage / local volume keyed by `screenshot_ref`.

## Evaluation set

`eval/cases/*.yaml`. Per case:

```yaml
id: arxiv-recent-rlhf
domain: arxiv.org
category: search-and-extract
task: "Find the most recent arXiv paper about RLHF and return its title and authors"
expect:
  schema: { title: str, authors: list[str] }
  validators:
    - title.nonempty
    - authors.len_gte: 1
budget: { steps: 20, usd: 0.10, seconds: 90 }
```

Categories (≥3 cases each, mix of fixtures + live):

1. **Search & extract** — Wikipedia, arXiv, HN, MDN
2. **Form filling** — public demo forms, search refinement
3. **Multi-page navigation** — pagination, follow link, return value
4. **Conditional pick** — find item matching a constraint
5. **Read & summarize** — docs page → bulleted answer
6. **Drift suite** — fixture v1/v2 pairs with renamed selectors, hosted statically in-repo. This exercises self-maintenance deterministically in CI.

`scripts/eval.py` runs the suite, writes `eval/results/<ts>.json` (per-case status, steps, USD, which L-tier resolved each click). README publishes the latest scoreboard. Live cases run behind `--live` so CI stays deterministic.

## Deployment (Zeabur)

- Base image: `mcr.microsoft.com/playwright/python:latest`.
- Env: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY?`, `MAX_STEPS`, `MAX_USD`.
- One headless browser per request, recycled within a worker.
- Optional persistent volume for SQLite locator cache (cold cache is acceptable).
- README pins the deployed URL.

## TDD tickets (each is red → green → refactor)

1. **`llm.py`** — mocked HTTP; assert OpenAI chat-completions request shape and `LLM_BASE_URL` honored.
2. **`browser.py` minimal** — `goto` + `read("h1")` against a local fixture served by `http.server`.
3. **`locate.py` L1** — fixture with a real `<button>` and a `role=button` spoofer; "Submit button" must resolve the real one.
4. **`locate.py` L2** — fixture with no accessible name; label-for / placeholder resolves correctly.
5. **`locate.py` L3** — fixture with three buttons sharing text "Save"; LLM rerank (mocked) picks the right section.
6. **`locate.py` L4** — fixture where target has no accessible metadata; vision LLM mock returns a bbox; click hits expected coords.
7. **Locator cache** — second resolve of same intent hits cache; AX-fingerprint mismatch invalidates.
8. **`supervisor.py`** — synthetic "0 matches" error → `LocatorMiss` → escalate to L2.
9. **`loop.py` happy path** — 2-step task on a local fixture finishes with `done` + valid evidence.
10. **`loop.py` self-correction** — fixture where L1 fails by design; run still succeeds via L2.
11. **`loop.py` silent-failure guard** — `done` without evidence → status `unverified`.
12. **`trace.py` schema + writer** — round-trip a `Run` + each `Event` variant through JSON; `seq` strictly increasing; redaction of secret-typed fields verified.
13. **Trace replay harness** — feed a recorded `LLMCallEvent.prompt` sequence into `loop.py` with the live browser stubbed; assert produced `DecisionEvent`s match the recording. This is the regression test surface for prompt/policy changes.
14. **`api/server.py`** — `POST /tasks` validates schema, returns id; `GET` returns final state and trace.
15. **Eval runner** — toy 2-case suite produces results JSON with expected shape.
16. **Drift suite** — fixture v1 and v2 (renamed selectors); same task passes both, no code change.
17. **Live cases** — one per category, behind `--live`. README documents results honestly.
18. **Dockerfile + Zeabur** — `docker run` + `curl POST /tasks` completes a fixture task end-to-end.

**Done bar**: drift suite 100%, fixture eval ≥ 80%, live ≥ 60% (or honest number reported), deployed Zeabur URL reachable, prompts captured under `prompts/task2/`.

## Honest risks / tradeoffs

- **Local Qwen3.5 27B is weaker than frontier on long-horizon planning.** Mitigation: short bounded plans, constrained tool-call grammar, structured observations. Will measure and surface in README.
- **Vision fallback is expensive.** Only triggered when L1–L3 all miss; cost is logged per case and visible on the scoreboard.
- **Live sites change.** Drift fixtures are the gate; live cases are a leaderboard, not pass/fail.
- **Single browser per request** caps concurrency. Acceptable for demo; called out in README.
