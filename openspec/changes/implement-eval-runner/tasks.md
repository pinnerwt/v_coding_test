## 1. Dependencies and package scaffold

- [ ] 1.1 From `task2/`, run `uv add pyyaml` to add the YAML parser as a runtime dep; confirm `pyproject.toml` and `uv.lock` are updated.
- [ ] 1.2 Create `task2/scripts/__init__.py` (empty file — makes scripts/ a package so tests can import from it).
- [ ] 1.3 Create `task2/eval/__init__.py` (empty file — marks eval/ as a package).
- [ ] 1.4 Create `task2/eval/cases/` directory (will hold YAML case files).
- [ ] 1.5 Create `task2/eval/results/` directory with a `.gitkeep` so the results directory is tracked but outputs are not committed.
- [ ] 1.6 Verify the scripts package is importable: from `task2/`, run `uv run python -c "import scripts"` and confirm no ImportError.

## 2. Red — Failing tests (results JSON shape)

- [ ] 2.1 Create `task2/tests/test_eval.py`. Add `from scripts.eval import run_suite` — this MUST fail with `ModuleNotFoundError` until `scripts/eval.py` exists. Confirm failure with `uv run pytest tests/test_eval.py -x`.
- [ ] 2.2 Add `test_results_json_shape`: patch `scripts.eval.loop` to return a canned `RunResult(status="succeeded", result={"title": "Hello"}, evidence={"url": "http://x", "text_snippet": "Hello"}, verifier={"ok": True, "reasons": []})`. Call `run_suite(cases=[<one inline fixture case dict>], results_dir=tmp_path)`. Assert the returned path exists and `json.loads(path.read_text())` succeeds. Assert top-level keys `run_at` and `cases` are present. Assert `cases` has exactly 1 entry with keys `id`, `status`, `steps`, `usd`, `l_tier_counts`, `validators`.
- [ ] 2.3 Add `test_results_json_l_tier_counts_is_dict`: same setup; assert `cases[0]["l_tier_counts"]` is a `dict` (not `null`, not absent).
- [ ] 2.4 Add `test_results_json_validators_list`: patch loop to return `result={"title": "Hello"}`; inline case has `validators: ["title.nonempty"]`; assert `cases[0]["validators"]` is a list of length 1 with `{"name": "title.nonempty", "ok": True}`.
- [ ] 2.5 Add `test_skipped_case_has_correct_shape`: define an inline case without `fixture: true`; call `run_suite(..., live=False)`; assert `cases[0]["status"] == "skipped"`, `steps == 0`, `usd == 0.0`, `l_tier_counts == {}`, `validators == []`.
- [ ] 2.6 From `task2/`, run `uv run pytest tests/test_eval.py -x` and confirm all new tests fail with `ModuleNotFoundError` (expected red state).

## 3. Red — Failing tests (case loader)

- [ ] 3.1 Add `test_load_cases_valid_yaml`: create a temp YAML file with all required fields; call `load_cases(path)` (or equivalent loader function); assert the result is a list with one element containing all expected fields. Confirm failure since `load_cases` does not exist yet.
- [ ] 3.2 Add `test_load_cases_missing_required_field_raises`: create a temp YAML file missing the `task` field; assert `load_cases(path)` raises `ValueError` mentioning the missing field.
- [ ] 3.3 Add `test_fixture_heading_yaml_loads`: call `load_cases("eval/cases/fixture-heading.yaml")` (relative to `task2/`); assert `id == "fixture-heading"` and `fixture == True`. Confirm failure since the YAML file does not exist yet.
- [ ] 3.4 Add `test_fixture_count_yaml_loads`: same for `fixture-count.yaml`; assert `id == "fixture-count"` and `fixture == True`.

## 4. Red — Failing tests (validator runner)

- [ ] 4.1 Add `test_validator_nonempty_passes`: call `run_validators(["title.nonempty"], {"title": "Hello"})` (or equivalent); assert result is `[{"name": "title.nonempty", "ok": True}]`. Confirm failure.
- [ ] 4.2 Add `test_validator_nonempty_fails_empty_string`: call with `{"title": ""}`; assert `ok == False`.
- [ ] 4.3 Add `test_validator_nonempty_fails_missing_key`: call with `{}`; assert `ok == False`.
- [ ] 4.4 Add `test_validator_len_gte_passes`: call `run_validators(["items.len_gte: 1"], {"items": ["a", "b"]})`; assert `ok == True`.
- [ ] 4.5 Add `test_validator_len_gte_fails_empty_list`: call with `{"items": []}`; assert `ok == False`.
- [ ] 4.6 Add `test_validator_len_gte_fails_missing_key`: call with `{}`; assert `ok == False`.

## 5. Green — Implement `scripts/eval.py` core

- [ ] 5.1 Create `task2/scripts/eval.py`. Define `load_cases(path: str | Path) -> list[dict]`: opens and parses YAML; validates required fields (`id`, `domain`, `category`, `task`, `expect`, `budget`); raises `ValueError` on missing field with file path in the message.
- [ ] 5.2 Implement `run_validators(validators: list[str], result: dict) -> list[dict]`: iterates validator expressions; parses `<key>.nonempty` and `<key>.len_gte: <N>`; returns `[{"name": expr, "ok": bool}, ...]`.
- [ ] 5.3 Implement `CaseResult` frozen dataclass with fields: `id: str`, `status: str`, `steps: int`, `usd: float`, `l_tier_counts: dict`, `validators: list[dict]`.
- [ ] 5.4 Implement `_run_case(case: dict, llm_client, browser) -> CaseResult`: constructs a `TraceWriter(":memory:")`, calls `loop(case["task"], browser, llm_client, max_steps=case["budget"]["steps"])`, extracts steps from the result (use `0` if `RunResult` does not expose step count directly), sets `usd=0.0`, sets `l_tier_counts={}` (L-tier extraction from trace is deferred until trace integration is wired), runs `run_validators(case["expect"].get("validators", []), result.result or {})`, returns `CaseResult`.
- [ ] 5.5 Implement `run_suite(cases: list[dict], *, results_dir: str | Path, live: bool = False, llm_client=None, browser=None) -> Path`: filters cases by `fixture` flag when `live=False`; for each case calls `_run_case` or produces a `skipped` `CaseResult`; builds the results JSON dict with `run_at` (UTC ISO 8601) and `cases` list; writes to `results_dir/<ts>.json`; returns the path.
- [ ] 5.6 Add `if __name__ == "__main__":` block with `argparse` for `--live` and `--case` flags; loads cases from `eval/cases/` (relative to `task2/`); constructs `LLMClient` and `Browser` from env; calls `run_suite`; prints per-case progress and final file path; exits with code 0 or 1 based on case statuses.
- [ ] 5.7 From `task2/`, run `uv run pytest tests/test_eval.py -x` and confirm the results-JSON-shape and skipped-case tests pass.

## 6. Green — Case YAML files and fixture HTML

- [ ] 6.1 Check `task2/tests/fixtures/` for an existing HTML file with a heading. If one exists (e.g. `loop_happy_path.html`), reference it in `fixture-heading.yaml`. If not, create `task2/tests/fixtures/eval_heading.html` — a minimal HTML page with a single `<h1>` heading.
- [ ] 6.2 Create a fixture HTML page for the count case: `task2/tests/fixtures/eval_list.html` — a minimal HTML page with an unordered list of 3 items.
- [ ] 6.3 Create `task2/eval/cases/fixture-heading.yaml` with fields: `id: fixture-heading`, `domain: fixture`, `category: read-and-summarize`, `task: "Read the page heading and return it as title"`, `expect: { schema: { title: str }, validators: [title.nonempty] }`, `budget: { steps: 5, usd: 0.05, seconds: 30 }`, `fixture: true`. Include the fixture URL or file path in a `fixture_url` field or as part of `domain`.
- [ ] 6.4 Create `task2/eval/cases/fixture-count.yaml` with fields: `id: fixture-count`, `domain: fixture`, `category: search-and-extract`, `task: "Read all list items on the page and return them as items"`, `expect: { schema: { items: "list[str]" }, validators: ["items.len_gte: 1"] }`, `budget: { steps: 5, usd: 0.05, seconds: 30 }`, `fixture: true`.
- [ ] 6.5 From `task2/`, run `uv run pytest tests/test_eval.py -x` and confirm the YAML-loader tests and fixture-file-load tests pass.

## 7. Green — Full test suite (validator and suite tests)

- [ ] 7.1 From `task2/`, run `uv run pytest tests/test_eval.py` and confirm all eval runner tests pass (green bar for this file).
- [ ] 7.2 From `task2/`, run `uv run pytest` (full suite) and confirm zero regressions in existing tests.

## 8. Lint and format

- [ ] 8.1 From `task2/`, run `uv run ruff check --fix .` to auto-fix any lint issues.
- [ ] 8.2 From `task2/`, run `uv run ruff format .` to auto-format changed files.
- [ ] 8.3 From `task2/`, run `uv run ruff check .` and confirm it exits clean (zero errors, zero warnings).

## 9. Refactor under green

- [ ] 9.1 Verify `scripts/eval.py` contains no hardcoded `LLM_BASE_URL`, `localhost:8090`, or model name strings outside `os.environ.get(...)` defaults. Run `grep -n "localhost:8090\|openai.com\|anthropic.com" task2/scripts/eval.py` and confirm empty output.
- [ ] 9.2 Confirm `scripts/eval.py` has no module-level docstrings or function docstrings (per the no-docstrings rule). One-line `#` why-comments are allowed.
- [ ] 9.3 Confirm the pre-commit gate passes: from `task2/`, run `uv run ruff format . && uv run ruff check . && uv run pytest` in sequence; all three must exit clean.
