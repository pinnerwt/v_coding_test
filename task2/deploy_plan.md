# Deploy Plan — Task 2 Browser Agent on Zeabur

Plan for shipping a usable demo: a chat UI where reviewers submit tasks, see the agent's plan and step-by-step trace live, answer clarifying questions when the agent calls `ask_user`, and read the final result.

## Branching & deployment workflow

```
   feature/* ──PR──▶ dev ──PR──▶ master ──push──▶ Zeabur (when enabled)
                      │             │
                      │             └── task2 deploy: build image,
                      │                  smoke-test container, deploy
                      │
                      └── task2 CI: ruff + pytest
                          task2 benchmark: canary gate + diff comment
```

- **`feature/*`** — work in progress. PRs target `dev`. Same CI as today (`task2 CI` + `task2 benchmark`).
- **`dev`** — integration branch. Run the FastAPI server + chat UI here against the local Qwen3.5 backend (see *Local development* below). When `dev` is verified end-to-end (ask_user round-trip works, no regressions on the verification checklist), open a PR `dev → master`.
- **`master`** — production. Push triggers `task2 deploy`: builds the Docker image, runs a containerised smoke test (`curl /` returns 200), and conditionally deploys to Zeabur.
- **Zeabur deploy gating** — the deploy job is gated on `vars.ZEABUR_DEPLOY_ENABLED == 'true'`. While the Zeabur account is not yet provisioned, the variable stays unset and the deploy job is skipped. Build + smoke still run, so master is always known to be deployable.

When the Zeabur account exists: set repo variable `ZEABUR_DEPLOY_ENABLED=true`, set secret `ZEABUR_TOKEN`, set variable `ZEABUR_SERVICE_ID`, and replace the placeholder echo in `.github/workflows/task2-deploy.yml::deploy` with the actual deploy CLI/API call.

## Local development (dev branch)

Three processes, each in its own terminal:

1. **Local LLM** — `llama-server --model qwen3.5-27b ... --port 8090 --temp 1.0 --top-p 0.95 --top-k 20 --seed 42 --jinja` (config from CLAUDE.md). Verify with `curl http://localhost:8090/v1/models`.
2. **FastAPI backend** — from `task2/`:
   ```bash
   LLM_BASE_URL=http://localhost:8090 \
   LLM_MODEL=qwen3.5-27b \
   LLM_API_KEY=local \
   LLM_TEMPERATURE=0.0 \
   DB_PATH=./runs.db \
   uv run uvicorn api.server:app --reload --port 8000
   ```
3. **Frontend** — served by FastAPI at `http://localhost:8000/` once B1–B4 land. Until then, `/` shows the legacy one-shot form.

Smoke flow: open `http://localhost:8000/`, submit *"請問下禮拜六中午十二點可不可以訂位旭集？"*, verify the chat asks which branch, answer *"天母店"*, watch the trace pane render `goto / read / click / type` events, and confirm the run terminates with `done` or a real `fail`.

## What already exists

- `api/server.py` — FastAPI app with `POST /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/trace` (ndjson snapshot, not streaming), and a minimal HTML form at `/`.
- `api/db.py` + `agent/trace.py` — SQLite-backed `TraceWriter` writes `traces_runs` and `traces_events` rows.
- `Dockerfile` based on `mcr.microsoft.com/playwright/python` and `zeabur.json` mapping `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `DB_PATH`.
- `agent/loop.py` exposes `ask_user_callback: Callable[[str], str] | None`. Agent emits `ActEvent` rows for every tool call (`goto`, `click`, `type`, `read`, `done`, `fail`, `ask_user`) and `PlanEvent` rows for the initial plan.

## What's missing for the demo

1. **`ask_user` round-trip over HTTP.** `loop()` blocks the calling thread inside `ask_user_callback`. The current `BackgroundTasks` worker has no callback wired, so an `ask_user` call would hang the run forever.
2. **Live event streaming.** `GET /tasks/{id}/trace` reads SQLite once at request time and returns the snapshot. The frontend needs *push* — events as they happen.
3. **A frontend that's actually a chat.** The `_HTML` blob in `server.py` is a one-shot form + 2-second status poll. No chat thread, no plan rendering, no `ask_user` answer box.

## Architecture (target)

```
┌────────────┐                             ┌────────────────┐
│ Browser UI │──── POST /sessions ───────▶│                │
│  (chat)    │◀─── SSE /sessions/{id} ────│   FastAPI      │
│            │──── POST /sessions/{id}/   │   (api/server) │──┐
│            │       answer  ────────────▶│                │  │
└────────────┘                             └────────────────┘  │
                                                  │            │
                                                  ▼            ▼
                                          ┌─────────────┐ ┌──────────┐
                                          │ Agent loop  │ │  SQLite  │
                                          │ (worker     │ │  trace   │
                                          │  thread)    │ │  store   │
                                          └─────┬───────┘ └──────────┘
                                                ▼
                                          ┌─────────────┐
                                          │ Playwright  │
                                          └─────────────┘
```

Single container. Worker thread per session. SSE for one-way push (simpler than WebSocket; survives Zeabur's HTTP proxy without special config). Chat UI is a static HTML/JS file served from `/`.

## Backend changes

### B1. Session state machine

`traces_runs` already stores `status` (null → running, then `succeeded`/`failed`). Add a new in-memory registry keyed by `run_id`:

```python
@dataclass
class SessionState:
    run_id: str
    answer_queue: queue.Queue[str]      # blocks the worker thread on ask_user
    pending_question: str | None        # set when worker is paused, cleared on answer
    event_subscribers: list[queue.Queue[str]]   # SSE consumers
    status: Literal["running", "awaiting_user", "done"]

_SESSIONS: dict[str, SessionState] = {}
```

Two queues, no asyncio: the agent loop is sync, so a worker thread + `queue.Queue` is the right primitive. Subscribers' queues let multiple tabs watch the same run.

### B2. `ask_user` HTTP callback

Replace the `BackgroundTasks` background runner with an explicit thread that owns a `SessionState`:

```python
def _ask_user_http(session: SessionState):
    def callback(question: str) -> str:
        session.pending_question = question
        session.status = "awaiting_user"
        _emit(session, {"type": "ask_user", "question": question})
        answer = session.answer_queue.get()       # blocks worker thread
        session.pending_question = None
        session.status = "running"
        _emit(session, {"type": "answer", "answer": answer})
        return answer
    return callback
```

`POST /sessions/{id}/answer` pushes onto `answer_queue`; the worker resumes on the next `loop()` iteration.

### B3. Live event push

Wrap `TraceWriter` so every `write_event` also fans out a JSON-encoded event to each subscriber queue:

```python
class StreamingTraceWriter(TraceWriter):
    def __init__(self, *args, on_event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_event = on_event

    def write_event(self, event):
        super().write_event(event)
        if self._on_event:
            self._on_event(event.model_dump())
```

`GET /sessions/{id}/events` returns an SSE stream (`text/event-stream`) that drains the subscriber queue and emits `data: {...}\n\n` frames. Close on `status == "done"` and a terminal `done`/`fail` event.

Events surfaced to the frontend (in order of usefulness):
- `plan` — initial plan steps + expected end state.
- `act` — tool call started: `{tool, args}`.
- `act_result` — tool result: `{tool, ok, summary}`.
- `ask_user` — agent paused with a question.
- `answer` — user replied (echo).
- `error` — exception, locator miss, transport error, timeout.
- `done` / `fail` — terminal.

### B4. Endpoints

| Method | Path                           | Purpose                                       |
|--------|--------------------------------|-----------------------------------------------|
| POST   | `/sessions`                    | Create session, kick off agent. Returns `{id}`. |
| GET    | `/sessions/{id}/events`        | SSE stream. Replays past events, then live.   |
| POST   | `/sessions/{id}/answer`        | `{answer: str}`. Resumes a paused agent.      |
| GET    | `/sessions/{id}`               | Current snapshot (for refresh/recovery).      |
| GET    | `/`                            | Serve the chat UI HTML.                       |

Keep the legacy `POST /tasks` etc. behind their existing paths so anything currently pointing at them keeps working — add new endpoints alongside.

## Frontend (chat UI)

Single static file: `api/static/index.html` + a small JS module. No build step, no React — keeps the Dockerfile flat.

### Layout
```
┌─────────────────────────────────────────────┐
│  Browser Agent                              │
├─────────────────────────────────────────────┤
│  Chat                  │  Trace             │
│  ─────                 │  ─────             │
│  user: book a table…   │  ▸ plan (5 steps)  │
│  agent: (thinking…)    │  ▸ goto google.com │
│  agent: which branch?  │  ▸ type "旭集"     │
│  ─ Tianmu / Xinyi / …  │  ▸ click result    │
│  user: Tianmu          │  ⚠ locator_miss    │
│  agent: done — booked  │  ▸ done            │
│                        │                    │
│  [type a message...]   │                    │
└─────────────────────────────────────────────┘
```

Left pane: chat thread. Right pane: timeline of trace events, click-to-expand for details (URL, error message, ax_tree digest size, etc.). On mobile: stack vertically, trace pane collapsed by default.

### Behavior
1. User types task, presses send → `POST /sessions` → opens SSE on `/sessions/{id}/events`.
2. SSE handler routes events:
   - `plan` → render as a checkable step list at top of trace pane.
   - `act` / `act_result` → append to trace pane; mark current plan step active.
   - `ask_user` → unlock chat input, render question as the latest agent message, show options as quick-reply chips if the question contains "or" between proper nouns (cheap heuristic; otherwise free-text).
   - `error` → red badge in trace pane + a single chat message ("hit a snag — recovering…").
   - `done` / `fail` → render result/answer in chat, lock input, show "start new task" button.
3. Chat input is disabled by default and only enabled when `status == "awaiting_user"` — prevents users from typing into the void mid-run. (Optional v2: a "tell the agent something" channel that injects a user message into the next planning step.)

### State recovery

If the user refreshes mid-run: `GET /sessions/{id}` to restore `status` + `pending_question`, then resubscribe to SSE. SSE replays past events from SQLite so the trace pane rebuilds itself.

## Zeabur deployment specifics

1. **`zeabur.json`** — add `LLM_TEMPERATURE` (optional, defaults to `0.0`) to envs. Bump `port` only if needed.
2. **`Dockerfile`** — add `COPY api/static/ api/static/` (currently doesn't copy any frontend assets). Confirm the playwright base image has the Chromium binaries pre-installed (`v1.58.0-noble` does).
3. **Persistence** — `DB_PATH` should land on Zeabur's persistent volume mount, not ephemeral `/tmp`, so a refresh after a redeploy doesn't 404 every old session. (Acceptable for the demo to skip this and just lose history on redeploy — flag it in README.)
4. **SSE buffering** — Zeabur's proxy sometimes buffers `text/event-stream` until the connection closes. Set `X-Accel-Buffering: no` and `Cache-Control: no-cache` on the SSE response; flush after every event. Verify in the deployed env, not just locally.
5. **Cold start** — Playwright spawns Chromium on the first `Browser()` call. ~3–5s. Either accept the first-task latency or warm a singleton browser at app startup. Singleton has its own pitfalls (one stuck page poisons all sessions); for the demo scale, per-session is fine.
6. **Concurrency** — uvicorn default is single worker. With per-session worker threads, each session needs ~300MB (Chromium) + LLM-call memory. On Zeabur's smaller plans, cap concurrent sessions explicitly (return 429 from `POST /sessions` if `len(_SESSIONS_running) >= MAX`).

## Verification checklist (pre-merge)

- [ ] `pytest` green (current: 874 passing).
- [ ] `ruff check` and `ruff format --check` clean.
- [ ] **End-to-end ask_user**: local `uvicorn` → open `/` → submit ambiguous task ("book a table at 旭集") → verify a question appears in chat, answer it, verify the agent resumes and reaches `done` or a real `fail`.
- [ ] **SSE replay on refresh**: start a session, refresh the page mid-run, confirm the trace pane reconstructs from SQLite.
- [ ] **Concurrent sessions**: open two tabs, submit different tasks, confirm trace events don't cross-contaminate.
- [ ] **Soak**: 5-iteration tier-1 with `LLM_TEMPERATURE=0.0` via `scripts/benchmark.py --repeats 5` to baseline pass-rate distribution and rule out resource leaks before the demo.
- [ ] **Zeabur smoke**: deploy, hit `/`, run one Wikipedia task, confirm SSE actually streams (not buffered to end).

## Order of work

Roughly half a day of focused implementation:

1. **B1+B2 (session + ask_user wiring)** — ~1.5 hr. Most of the new code; everything else depends on it.
2. **B3 (SSE streaming writer)** — ~1 hr.
3. **Frontend HTML/JS** — ~2 hr. Plain DOM, fetch + EventSource. No framework.
4. **B4 (endpoints + tests)** — folded into B1–B3.
5. **Zeabur deploy + SSE buffering verification** — ~30 min.
6. **Verification checklist run-through** — ~1 hr.

Out of scope for this milestone: persistent session history, auth, multi-user accounts, cost meter, replay-from-trace UI, mobile-optimized layout. File these as follow-up tickets if reviewers ask.
