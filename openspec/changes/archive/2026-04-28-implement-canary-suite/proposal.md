## Why

The current CI gate for Task 2 only checks that a `results.json` file exists and is newer than the merge-base commit — it does not inspect pass/fail outcomes, so any regression, even a complete failure of every case, silently passes. We need a hard-blocking gate that catches regressions on a small set of "must-always-pass" cases before they land on master.

## What Changes

- Add a `canary: true` field to the case YAML schema so individual cases can be tagged as canary.
- Tag `fixture-heading` as a canary case, and add a new `canary-read-h1` case that reads the H1 of a fixture page. Both cases get a `data:`-URL `fixture_url` so the runner navigates to a self-contained page before the loop starts; budgets are aligned at 5 steps. `fixture-count` is intentionally NOT canary-tagged: its list-extraction path hits an unrelated `IntentParseError` in the locate engine (parser does not recognize "items"/"list" roles), which is out of scope here. `fixture-count` keeps a `fixture_url` for general benchmarking but stays non-canary until that pipeline issue is fixed in a follow-up ticket.
- Introduce `scripts/canary_gate.py` (invokable as `uv run python -m scripts.canary_gate --results <path>`) that reads a `results.json`, identifies canary-tagged cases, and exits non-zero if any canary case is not passing, or exits zero with a warning printed to stdout if all canaries pass but non-canaries failed.
- Extend `.github/workflows/task2-benchmark.yml` with a new "Canary gate" step that calls `canary_gate.py` and blocks merge on non-zero exit.
- Add pure-Python unit tests (no Playwright, no LLM) using synthetic `results.json` fixtures covering: (a) one canary failed → gate fails; (b) all canaries pass + non-canaries failed → gate passes with warning.

## Capabilities

### New Capabilities

- `canary-gate`: The canary gate script and its CLI contract (exit codes, stdout shape, what counts as "passing"), the `canary: true` case YAML field, and the CI workflow step that invokes the gate.

### Modified Capabilities

- `eval-runner`: The case YAML schema gains the optional `canary: bool` field (default `false`). `load_cases` must not reject files that carry the new field; no other runner behavior changes.
- `bench-repeats`: The CI workflow note about `--repeats 3` for "canary and drift suites" is now fulfilled by the new canary category; the forward reference in the spec must be updated to remove "canary suites" as a future placeholder.

## Impact

- `task2/eval/cases/fixture-heading.yaml` — add `canary: true`
- `task2/eval/cases/fixture-count.yaml` — add `fixture_url` (for general benchmarking; not canary-tagged)
- `task2/eval/cases/canary-read-h1.yaml` — new case file
- `task2/scripts/canary_gate.py` — new module
- `task2/tests/test_canary_gate.py` — new test file
- `.github/workflows/task2-benchmark.yml` — new "Canary gate" step
- `openspec/specs/eval-runner/spec.md` — delta: add `canary` field to case YAML schema
- `openspec/specs/bench-repeats/spec.md` — delta: remove stale forward reference to "canary suites"
