# Task 2 — Generalized Browser Automation Agent

See `plan.md` for the full design. This README is the operator's guide.

## Setup

```bash
cd task2
uv sync
uv run playwright install chromium
```

`playwright install chromium` is a one-time post-`uv sync` step — Playwright wheels do not ship the browser binary, and `uv` does not run post-install hooks.

## Running tests

```bash
uv run pytest
```

## Lint / format

```bash
uv run ruff check .
uv run ruff format .
```

## Deployment

### Docker (local)

```bash
docker build -t vici-task2 task2/

docker run -p 8000:8000 \
  -e LLM_BASE_URL=<openai-compatible-base-url> \
  -e LLM_MODEL=<model-name> \
  -e LLM_API_KEY=<optional-api-key> \
  vici-task2
```

For persistent SQLite storage across restarts, mount a host directory:

```bash
docker run -p 8000:8000 \
  -e LLM_BASE_URL=<openai-compatible-base-url> \
  -e LLM_MODEL=<model-name> \
  -e DB_PATH=/data/vici.db \
  -v /host/path:/data \
  vici-task2
```

### Zeabur

Live URL: `<TBD: Zeabur URL after deployment>`

Connect this repo on the Zeabur dashboard, set the build root to the repo root (the `task2/zeabur.json` file points Zeabur to `task2/Dockerfile`), then set these environment variables:

- `LLM_BASE_URL` — reachable OpenAI-compatible API endpoint
- `LLM_MODEL` — model name to use
- `LLM_API_KEY` — API key (optional, omit for key-free endpoints)
- `DB_PATH` — path inside the container for the SQLite DB (default `/tmp/vici.db`; set to a mounted volume path for persistence)

## Configuration

Environment variables consumed by the LLM client (see `agent/llm.py`):

- `LLM_BASE_URL` — defaults to `http://localhost:8090`
- `LLM_MODEL` — required (no default)
- `LLM_API_KEY` — optional, forwarded as `Authorization: Bearer ...`

## Live eval results

Run manually with `uv run python -m scripts.eval --live` from `task2/`. Per the plan, live cases are a leaderboard, not a pass/fail gate — drift fixtures remain the gate.

Last manual run: 2026-04-26, against local Qwen3.5 27B at `http://localhost:8090` (cases run individually via `--case <id>` due to an unhandled intent-parse exception in the suite-wide path; see notes).

| Case | Site | Status | Steps | Notes |
|---|---|---|---|---|
| live-search-extract | en.wikipedia.org | failed | 0 | `IntentParseError`: LLM emitted intent with role `paragraph`, only `button/checkbox/heading/link/textbox` supported by `parse_intent` |
| live-form-fill | duckduckgo.com | failed | 0 | Agent ran without crashing but validator `first_result_title.nonempty` failed — no result extracted |
| live-multi-page-nav | books.toscrape.com | succeeded | 0 | Validator `book_title.nonempty` passed |
| live-conditional-pick | books.toscrape.com | failed | 0 | `IntentParseError`: role `page` not supported |
| live-read-summarize | docs.python.org | succeeded | 0 | Validator `summary.nonempty` passed |

Score: 2/5 succeeded, 3/5 failed (1 validator failure, 2 agent crashes). The two errors are the same root cause — `agent/locate.py:parse_intent` accepts only a fixed set of ARIA roles, so when the LLM names a non-role noun ("paragraph", "page") the loop crashes instead of recovering. Honest takeaway: locator robustness on unstructured pages is the next bottleneck. `steps` reads 0 because `_run_case` does not yet thread the loop's step count into `CaseResult` — separate follow-up.
