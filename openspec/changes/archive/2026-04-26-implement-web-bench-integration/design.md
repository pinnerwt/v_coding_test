## Context

The eval runner (`scripts/eval.py`) and `run_suite` are complete (ticket #15). The runner accepts any list of `Case`-compatible dicts, calls `loop()` per case, and writes `eval/results/<ts>.json`. Ticket #19 asks for an additional eval source from a public benchmark, a research brief, and tests.

Seven benchmarks are surveyed in `prompts/task2/web-benchmarks.md`. This design document records the benchmark selection decision and the implementation approach for the loader and runner entry.

Constraints:
- No new Python packages — all upstream formats must be parseable with stdlib.
- No hardcoded LLM provider — `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` from env.
- No comments/docstrings in production code; tests may have single-line docstrings.
- TDD: tests first, code second.
- `ruff` clean.

## Goals / Non-Goals

**Goals:**

- Research brief at `prompts/task2/web-benchmarks.md` covering all seven benchmarks (license, scope, hosting cost, task format, headline metric) with a concrete selected benchmark marked.
- Loader `task2/eval/bench/webvoyager_loader.py` converting WebVoyager JSON task entries into `Case`-compatible dicts passable to `run_suite`.
- Vendored fixture `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json` (3–5 entries).
- Runner `task2/scripts/bench.py` with `--suite webvoyager` that calls `run_suite` and writes `eval/results/<ts>.json` with the existing shape.
- Tests: loader parse, runner smoke test (stubbed browser + LLM), brief existence check.

**Non-Goals:**

- Integrating more than one benchmark (scope is exactly one — WebVoyager).
- Vendoring the full upstream WebVoyager dataset (fixture only, 3–5 entries).
- WebArena integration (requires self-hosted Dockerized sites — explicitly out of scope for this ticket).
- Modifying `scripts/eval.py` or `run_suite` — the bench runner is a separate entry point that delegates to the existing machinery.
- Achieving any specific pass rate on WebVoyager tasks — the runner produces honest JSON; no pass-rate gate.

## Decisions

### Decision 1: Select WebVoyager as the integration target

**Rationale:**

| Benchmark | License | Scope | Hosting cost | Task format | Why rejected / why selected |
|---|---|---|---|---|---|
| WebArena | MIT | Live / snapshot Docker | High — self-hosted Docker sites per task | JSON with site, intent, config | Requires Dockerized server images per task; not feasible without infra setup |
| Mind2Web (offline) | MIT | Snapshot (DOM replay) | None — HF dataset | JSON of recorded browser traces | Traces replayed against frozen DOM snapshots; cannot exercise real browser loop |
| Online-Mind2Web | MIT | Live web | None — HF dataset | JSON with URL + instruction | Viable; but requires Hugging Face API access and dataset download tooling |
| BrowserGym | Apache-2.0 | Simulated + live | Medium — depends on task set | Gym environment wrapper | Gym API does not map cleanly to our `loop()` signature without a non-trivial adapter |
| WebVoyager | CC BY 4.0 | Live web | None — task list is a JSON file | JSON list of `{id, web_name, ques, web}` objects | Simple JSON, no infra, live-web scope matches our agent, CC BY 4.0 is permissive for research use — **SELECTED** |
| MiniWoB++ | MIT | Simulated (mini HTML sites) | Low — serves from local server | JSON task descriptors | Simulated env; does not exercise live-web generalization |
| WebShop | MIT | Simulated (shopping env) | Medium — requires running WebShop server | Structured shopping queries | Requires running a local WebShop server |
| GAIA web subset | CC BY 4.0 | Live web | None — HF dataset | JSON with question + annotator_metadata | Viable; but GAIA tasks are question-answering with web search, not pure browser tasks — less aligned with our tool surface |

WebVoyager is the best fit: open JSON task list (no infra), live-web scope aligned with our agent, permissive license, and a simple field structure (`id`, `web_name`, `ques`, `web`) that maps cleanly to our `Case` schema.

**Alternative rejected**: Online-Mind2Web — also viable but requires HF dataset API access and a heavier download; WebVoyager task list is a single JSON file vendorable as-is.

### Decision 2: Loader maps WebVoyager fields to Case schema at load time (not at runner boundary)

The loader converts upstream fields to our `Case` dict shape before passing to `run_suite`. This keeps `run_suite` and `loop()` unchanged and makes the loader independently testable.

Mapping:
- `id` → `case["id"]` (prefixed `webvoyager-` to avoid collisions)
- `ques` → `case["task"]`
- `web` → `case["domain"]` (used as the start URL for `goto`)
- `web_name` → `case["category"]` (used as a label; no impact on runner logic)
- `expect` → `{"schema": {"answer": "str"}, "validators": ["answer.nonempty"]}` (coarse; WebVoyager ground truth is not machine-checkable without human eval, so we assert structure not content)
- `budget` → `{"steps": 20, "usd": 0.25, "seconds": 120}` (fixed defaults matching live-cases budget)
- `fixture: False` (benchmark cases are always live; gated by `--live` flag in `bench.py`)

**Alternative rejected**: adapter at runner boundary (lazy conversion inside `run_suite`). Rejected — `run_suite` expects `Case` dicts; mutating the signature would break existing callers.

### Decision 3: bench.py is a standalone entry point that imports run_suite

`scripts/bench.py` is `python -m scripts.bench`. It builds clients, loads the benchmark via the loader, calls `run_suite`, and exits. It does not modify `eval.py`. This mirrors how `eval.py`'s `main()` works — same pattern, separate file.

### Decision 4: Smoke test stubs both browser and LLM

The runner smoke test patches `scripts.bench.loop` (same import-boundary pattern as `test_eval.py` patches `scripts.eval.loop`) and `scripts.bench.Browser` + `scripts.bench.LLMClient`. One WebVoyager case from the vendored fixture is run; the test asserts the output JSON has `run_at` and `cases` with the required `CaseResult` keys. No real network or browser call.

### Decision 5: Vendored fixture is 3 entries, manually extracted

Three representative entries are hand-selected from the public WebVoyager task JSON and stored at `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json`. They cover three different `web_name` values (different sites) to exercise the loader's `domain` mapping. The full upstream dataset (~600+ tasks) is not vendored.

## Risks / Trade-offs

- **WebVoyager live tasks may be unreachable** → The `--live` flag gates them; without `--live`, all benchmark cases are skipped. No CI impact.
- **Ground-truth checking is impossible automatically** → WebVoyager answers require human judgment. We use `answer.nonempty` as the only validator, which checks the agent returned something — not that it's correct. This is honest and documented in the brief.
- **CC BY 4.0 requires attribution** → The research brief and fixture header must credit the WebVoyager authors. No code license impact.
- **Field `web` is a URL in some entries and a site name in others** → The vendored fixture uses only entries where `web` is a valid URL. The loader treats `web` as the `goto` start URL; if it is not a URL, `goto` will fail and `loop` returns `failed`. This is acceptable — the smoke test uses a fixture entry with a valid URL.

## Open Questions

- None blocking. Benchmark selection is decided; fixture entries are hand-selected from the public dataset.
