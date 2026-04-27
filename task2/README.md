# Task 2 — Generalized Browser Automation Agent

<!-- TRENDS:BEGIN -->
## Benchmark trends

![Pass rate over time](benchmark/_trends/pass_rate.svg)

![Latency over time](benchmark/_trends/latency.svg)

![Cost per run](benchmark/_trends/cost.svg)
<!-- TRENDS:END -->


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
