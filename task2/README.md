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

## Configuration

Environment variables consumed by the LLM client (see `agent/llm.py`):

- `LLM_BASE_URL` — defaults to `http://localhost:8090`
- `LLM_MODEL` — required (no default)
- `LLM_API_KEY` — optional, forwarded as `Authorization: Bearer ...`

## Live eval results

Run manually with `uv run python scripts/eval.py --live` from `task2/`.

| Case | Site | Status | Steps | Notes |
|---|---|---|---|---|
| live-search-extract | en.wikipedia.org | — | — | Not yet run |
| live-form-fill | duckduckgo.com | — | — | Not yet run |
| live-multi-page-nav | books.toscrape.com | — | — | Not yet run |
| live-conditional-pick | books.toscrape.com | — | — | Not yet run |
| live-read-summarize | docs.python.org | — | — | Not yet run |
