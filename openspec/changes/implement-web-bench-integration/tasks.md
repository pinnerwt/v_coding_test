## 1. Red — Failing tests (write tests before any implementation)

- [x] 1.1 Create `task2/tests/test_bench.py`. Add imports for the not-yet-existing loader (`from eval.bench.webvoyager_loader import load_webvoyager`) and bench runner (`from scripts.bench import main`). Run `uv run pytest tests/test_bench.py --collect-only` from `task2/` and confirm the collection itself fails with `ModuleNotFoundError` — this is the expected red state.
- [x] 1.2 Add `test_brief_exists`: assert `Path("prompts/task2/web-benchmarks.md").exists()` is `True` (path relative to repo root, i.e. `Path(__file__).parents[3] / "prompts/task2/web-benchmarks.md"`). Run `uv run pytest tests/test_bench.py::test_brief_exists -x` and confirm it fails because the file does not exist yet.
- [x] 1.3 Add `test_brief_names_selected_benchmark`: read `prompts/task2/web-benchmarks.md` and assert the text contains `"WebVoyager"` and at least one of `"selected"` / `"Selected"` / `"SELECTED"`. Run and confirm fails (file absent).
- [x] 1.4 Add `test_brief_lists_all_benchmarks`: read the brief and assert it contains each of: `"WebArena"`, `"Mind2Web"`, `"BrowserGym"`, `"WebVoyager"`, `"MiniWoB++"`, `"WebShop"`, `"GAIA"`. Run and confirm fails.
- [x] 1.5 Add `test_fixture_file_exists`: assert `Path("tests/fixtures/benchmarks/webvoyager/tasks_sample.json").exists()`. Run from `task2/` and confirm fails.
- [x] 1.6 Add `test_fixture_parses_as_json`: load `tasks_sample.json` with `json.load`, assert result is a list of length 3–5, each entry has keys `id`, `web_name`, `ques`, `web`. Run and confirm fails.
- [x] 1.7 Add `test_loader_returns_case_dicts`: call `load_webvoyager("tests/fixtures/benchmarks/webvoyager/tasks_sample.json")` and assert: result is a list; each item has keys `id`, `task`, `domain`, `category`, `expect`, `budget`, `fixture`; `fixture` is `False`. Run and confirm fails (loader module absent).
- [x] 1.8 Add `test_loader_id_prefix`: first item's `id` starts with `"webvoyager-"`. Run and confirm fails.
- [x] 1.9 Add `test_loader_maps_ques_to_task`: first item's `task` equals the `ques` value of the first fixture entry. Run and confirm fails.
- [x] 1.10 Add `test_loader_maps_web_to_domain`: first item's `domain` equals the `web` value of the first fixture entry. Run and confirm fails.
- [x] 1.11 Add `test_runner_smoke_no_live`: patch `scripts.bench.loop`, `scripts.bench.Browser`, `scripts.bench.LLMClient`. Call `main(["--suite", "webvoyager"])` (no `--live`) with env vars pointing to `tmp_path` for results and fixture for tasks. Assert the written JSON has `run_at` and `cases` where all entries have `status == "skipped"` (because `fixture == False` and `live == False`). Run and confirm fails (module absent).
- [x] 1.12 Add `test_runner_smoke_result_shape`: patch `scripts.bench.loop` to return a canned `RunResult(status="succeeded", result={"answer": "hello"}, evidence={"url": "http://x", "text_snippet": "hello"}, verifier={"ok": True, "reasons": []})` plus `Browser` and `LLMClient`. Call `main(["--suite", "webvoyager", "--live"])`. Assert the written JSON has `run_at` and `cases` with at least one entry containing all `CaseResult` keys: `id`, `status`, `steps`, `usd`, `l_tier_counts`, `validators`. Run and confirm fails.

## 2. Green — Vendored fixture

- [x] 2.1 Create directory `task2/tests/fixtures/benchmarks/webvoyager/`.
- [x] 2.2 Create `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json` with exactly 3 hand-selected WebVoyager task entries (from the public dataset at https://github.com/MinorJerry/WebVoyager). Each entry must have `id`, `web_name`, `ques`, `web` fields; `web` must be a valid `https://` URL. Sample entries should cover 3 different `web_name` values (different sites). Include a CC BY 4.0 attribution comment in a wrapper object or as a leading `_attribution` field — but since JSON does not support comments, add an `_attribution` key to the root object OR keep entries as a plain list and record attribution in the test file's docstring. Prefer a plain JSON list with no extra keys to keep the loader simple.
- [x] 2.3 From `task2/`, run `uv run pytest tests/test_bench.py::test_fixture_file_exists tests/test_bench.py::test_fixture_parses_as_json -x` and confirm both pass.

## 3. Green — Loader

- [x] 3.1 Create `task2/eval/bench/__init__.py` (empty).
- [x] 3.2 Create `task2/eval/bench/webvoyager_loader.py`. Implement `load_webvoyager(path: str | Path) -> list[dict]` using only stdlib (`json`, `pathlib`). Apply the field mapping from the design: `id` → `"webvoyager-" + str(entry["id"])`, `ques` → `task`, `web` → `domain`, `web_name` → `category`, hardcoded `expect` / `budget` / `fixture=False`. No docstring, no comments.
- [x] 3.3 From `task2/`, run `uv run pytest tests/test_bench.py::test_loader_returns_case_dicts tests/test_bench.py::test_loader_id_prefix tests/test_bench.py::test_loader_maps_ques_to_task tests/test_bench.py::test_loader_maps_web_to_domain -x` and confirm all four pass.

## 4. Green — Bench runner

- [x] 4.1 Create `task2/scripts/bench.py`. Implement `main(argv)` that:
  - Parses `--suite <name>` (required) and `--live` (flag).
  - For `--suite webvoyager`: resolves the task source path (default `tests/fixtures/benchmarks/webvoyager/tasks_sample.json` for local dev, overridable via env var `WEBVOYAGER_TASKS`), calls `load_webvoyager`, then calls `run_suite`.
  - Reads `LLM_BASE_URL` (default `http://localhost:8090/v1`), `LLM_MODEL` (default `qwen3`), `LLM_API_KEY` (default `local`) from env — identical to `eval.py`.
  - Reads `EVAL_RESULTS_DIR` (default `eval/results`) from env.
  - Writes `eval/results/<ts>.json` via `run_suite`.
  - Exits using `compute_exit_code`.
  - No docstrings, no comments.
- [x] 4.2 Ensure `task2/scripts/__init__.py` exists (it should already; verify with `ls task2/scripts/__init__.py`).
- [x] 4.3 From `task2/`, run `uv run pytest tests/test_bench.py::test_runner_smoke_no_live tests/test_bench.py::test_runner_smoke_result_shape -x` and confirm both pass.

## 5. Green — Research brief

- [x] 5.1 Create `prompts/task2/web-benchmarks.md`. The brief MUST contain sections for each of the seven benchmarks (WebArena, Mind2Web / Online-Mind2Web, BrowserGym, WebVoyager, MiniWoB++, WebShop, GAIA web subset). For each: license, scope, hosting cost, task format, headline metric. Include a recommendation section that names WebVoyager as the selected benchmark with reasoning covering license (CC BY 4.0), hosting cost (none — plain JSON), task format simplicity (`id`, `web_name`, `ques`, `web` fields), and fit with our `Case` schema. Mark WebVoyager explicitly as the integration choice (e.g., `**SELECTED**` or equivalent). Include CC BY 4.0 attribution to the WebVoyager authors.
- [x] 5.2 From `task2/`, run `uv run pytest tests/test_bench.py::test_brief_exists tests/test_bench.py::test_brief_names_selected_benchmark tests/test_bench.py::test_brief_lists_all_benchmarks -x` and confirm all three pass.

## 6. Full green bar

- [x] 6.1 From `task2/`, run `uv run pytest tests/test_bench.py -v` and confirm all tests in the new module pass.
- [x] 6.2 From `task2/`, run `uv run pytest` (full suite) and confirm zero regressions in existing tests (`test_eval.py`, `test_drift.py`, `test_live_gating.py`, agent/api tests all still pass).

## 7. Lint and format

- [x] 7.1 From `task2/`, run `uv run ruff check --fix .` to auto-fix any lint issues in new files.
- [x] 7.2 From `task2/`, run `uv run ruff format .` to auto-format all new files.
- [x] 7.3 From `task2/`, run `uv run ruff check .` and confirm it exits clean (zero errors, zero warnings).

## 8. Refactor under green

- [x] 8.1 Verify `scripts/bench.py` does not import `scripts.eval` by name — it should import `run_suite`, `compute_exit_code` directly from `scripts.eval` (same pattern as production use). Run `grep -n "import" task2/scripts/bench.py` and confirm only specific names are imported, no `import scripts.eval` as a module alias.
- [x] 8.2 Verify `test_bench.py` patches `scripts.bench.loop`, `scripts.bench.Browser`, `scripts.bench.LLMClient` (not `agent.loop.loop`, etc.) — correct import-boundary mocking. Run `grep -n "patch" task2/tests/test_bench.py` and confirm.
- [x] 8.3 Verify no production code in `eval/bench/` or `scripts/bench.py` contains comments or docstrings. Run `grep -n "#\|\"\"\"" task2/eval/bench/webvoyager_loader.py task2/scripts/bench.py` and confirm output is empty.
- [x] 8.4 From `task2/`, run `uv run ruff format . && uv run ruff check . && uv run pytest` in sequence; all three must exit clean.
