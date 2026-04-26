## 1. Red — Failing tests (live gating)

- [ ] 1.1 Create `task2/tests/test_live_gating.py`. Add `from scripts.eval import run_suite, load_cases` — run `uv run pytest tests/test_live_gating.py --collect-only` from `task2/` and confirm it collects (module already importable since `scripts/eval.py` exists).
- [ ] 1.2 Add `test_live_case_skipped_without_live_flag`: define an inline case dict with `live: True` and no `fixture: True`. Patch `scripts.eval.loop` with a canned `RunResult`. Call `run_suite(cases=[live_case], results_dir=tmp_path, live=False)`. Assert `data["cases"][0]["status"] == "skipped"`. Run `uv run pytest tests/test_live_gating.py::test_live_case_skipped_without_live_flag -x` — confirm it passes (this behavior already exists; the test documents it).
- [ ] 1.3 Add `test_live_case_executed_with_live_flag`: same inline live case; patch `scripts.eval.loop` to return `RunResult(status="succeeded", result={"summary": "Hello"}, ...)`. Call `run_suite(..., live=True)`. Assert `data["cases"][0]["status"] == "succeeded"` (not `"skipped"`). Run and confirm passes.
- [ ] 1.4 Add `test_mixed_suite_gating`: define two inline cases — one with `fixture: True`, one with `live: True` (no fixture). Patch `scripts.eval.loop` with one canned result (for the fixture case only). Call `run_suite(..., live=False)`. Assert `data["cases"]` has 2 entries; first has non-skipped status; second has `status == "skipped"`. Run and confirm passes.
- [ ] 1.5 Add `test_all_live_yaml_files_load`: call `load_cases` on each of the five `live-*.yaml` paths (relative to `task2/`). Assert each returns a list of length 1, each has all required fields, and each has `case.get("fixture", False) == False`. Run `uv run pytest tests/test_live_gating.py::test_all_live_yaml_files_load -x` — confirm it fails with `FileNotFoundError` (YAML files do not exist yet). This is the **red state** for the YAML authoring tasks.

## 2. Green — Live case YAML files

- [ ] 2.1 Create `task2/eval/cases/live-search-extract.yaml`:
  ```yaml
  id: live-search-extract
  domain: en.wikipedia.org
  category: search-and-extract
  live: true
  task: "Navigate to https://en.wikipedia.org/wiki/Python_(programming_language) and return the first sentence of the lead paragraph as summary"
  expect:
    schema:
      summary: str
    validators:
      - summary.nonempty
  budget:
    steps: 20
    usd: 0.25
    seconds: 120
  ```
- [ ] 2.2 Create `task2/eval/cases/live-form-fill.yaml`:
  ```yaml
  id: live-form-fill
  domain: duckduckgo.com
  category: form-fill
  live: true
  task: "Navigate to https://duckduckgo.com/, type 'Python programming language' into the search box, submit the search, and return the title of the first result as first_result_title"
  expect:
    schema:
      first_result_title: str
    validators:
      - first_result_title.nonempty
  budget:
    steps: 20
    usd: 0.25
    seconds: 120
  ```
- [ ] 2.3 Create `task2/eval/cases/live-multi-page-nav.yaml`:
  ```yaml
  id: live-multi-page-nav
  domain: books.toscrape.com
  category: multi-page-nav
  live: true
  task: "Navigate to https://books.toscrape.com/, go to page 2 of the catalogue, and return the title of the first book listed on that page as book_title"
  expect:
    schema:
      book_title: str
    validators:
      - book_title.nonempty
  budget:
    steps: 30
    usd: 0.30
    seconds: 150
  ```
- [ ] 2.4 Create `task2/eval/cases/live-conditional-pick.yaml`:
  ```yaml
  id: live-conditional-pick
  domain: books.toscrape.com
  category: conditional-pick
  live: true
  task: "Navigate to https://books.toscrape.com/catalogue/category/books/mystery_3/index.html, find the first book with a five-star rating, and return its title as book_title"
  expect:
    schema:
      book_title: str
    validators:
      - book_title.nonempty
  budget:
    steps: 25
    usd: 0.30
    seconds: 150
  ```
- [ ] 2.5 Create `task2/eval/cases/live-read-summarize.yaml`:
  ```yaml
  id: live-read-summarize
  domain: docs.python.org
  category: read-and-summarize
  live: true
  task: "Navigate to https://docs.python.org/3/library/pathlib.html and return the first paragraph of the module description as summary"
  expect:
    schema:
      summary: str
    validators:
      - summary.nonempty
  budget:
    steps: 20
    usd: 0.25
    seconds: 120
  ```
- [ ] 2.6 From `task2/`, run `uv run pytest tests/test_live_gating.py::test_all_live_yaml_files_load -x` and confirm it passes (all five YAML files load successfully, all fields present, no fixture flag). This is the **green state**.

## 3. Green — Full gating test suite

- [ ] 3.1 From `task2/`, run `uv run pytest tests/test_live_gating.py -v` and confirm all gating tests pass (green bar for this file).
- [ ] 3.2 From `task2/`, run `uv run pytest` (full suite) and confirm zero regressions in existing tests (fixture, eval, drift suites all still pass).

## 4. Lint and format

- [ ] 4.1 From `task2/`, run `uv run ruff check --fix .` to auto-fix any lint issues in `tests/test_live_gating.py`.
- [ ] 4.2 From `task2/`, run `uv run ruff format .` to auto-format the new test file.
- [ ] 4.3 From `task2/`, run `uv run ruff check .` and confirm it exits clean (zero errors, zero warnings).

## 5. Refactor under green

- [ ] 5.1 Verify `tests/test_live_gating.py` patches `scripts.eval.loop` (not `agent.loop.loop`) — same import-boundary pattern as `test_eval.py`. Run `grep -n "patch" task2/tests/test_live_gating.py` and confirm the patch target is `scripts.eval.loop`.
- [ ] 5.2 Verify none of the five live YAML files contain `fixture: true` — run `grep -l "fixture" task2/eval/cases/live-*.yaml` and confirm the output is empty.
- [ ] 5.3 Verify `scripts/eval.py` was not modified by this ticket — run `git diff task2/scripts/eval.py` and confirm empty output.
- [ ] 5.4 From `task2/`, run `uv run ruff format . && uv run ruff check . && uv run pytest` in sequence; all three must exit clean.

## 6. README update

- [ ] 6.1 Add a "## Live eval results" section to `task2/README.md` with a placeholder table:
  ```markdown
  ## Live eval results

  Run manually with `uv run python scripts/eval.py --live` from `task2/`.

  | Case | Site | Status | Steps | Notes |
  |---|---|---|---|---|
  | live-search-extract | en.wikipedia.org | — | — | Not yet run |
  | live-form-fill | duckduckgo.com | — | — | Not yet run |
  | live-multi-page-nav | books.toscrape.com | — | — | Not yet run |
  | live-conditional-pick | books.toscrape.com | — | — | Not yet run |
  | live-read-summarize | docs.python.org | — | — | Not yet run |
  ```
- [ ] 6.2 After the first manual `uv run python scripts/eval.py --live` run, replace `—` placeholder values with real observed status, steps, and brief notes. This step is a manual documentation task, not a test gate.
