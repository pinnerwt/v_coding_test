## Context

Benchmark runs write `task2/benchmark/<sanitized-branch>/results.json` and `scoreboard.md`. The master branch writes to `task2/benchmark/master/`. When a PR runs the benchmark, there is currently no automated comparison: a reviewer must open two scoreboard files and diff them by eye. Ticket #36 asks for a machine-readable diff emitted as `diff.md` per branch and posted as a PR comment.

Existing patterns:
- `scripts/benchmark.py` owns the write path (`write_outputs`).
- `scripts/score.py` owns scoreboard generation (`generate_scoreboard`).
- The CI workflow (`task2-benchmark.yml`) runs one job with a verify step.
- Both scripts are invokable via `uv run python -m scripts.<name>`.

## Goals / Non-Goals

**Goals:**
- Produce a Δ vs master markdown table (per-case deltas, aggregate deltas) when branch ≠ master.
- Write the diff to `task2/benchmark/<branch>/diff.md` (committed alongside `results.json`).
- Post the diff as a PR comment in CI.
- Flag newly-failing cases (regressions) with a severity marker.
- Produce an empty / omitted Δ table when branch is master or baseline is absent.
- Keep diff logic independently testable with pure-Python synthetic inputs.

**Non-Goals:**
- Changing the `results.json` schema.
- Supporting multi-level severity beyond binary (regression = newly-failing).
- Diffing anything other than `master` as the baseline (e.g., previous run on the same branch).
- Rendering the diff inside `scoreboard.md` itself (the diff is a sibling file).

## Decisions

### Decision 1: New module `task2/scripts/baseline_diff.py`, not embedded in score.py or benchmark.py

**Chosen:** Separate `baseline_diff.py` with a public `generate_diff_markdown(master: dict, branch: dict) -> str`.

**Alternatives considered:**
- *Inside `score.py` via `--diff` flag only:* score.py is already 250 lines; adding diff logic would mix two concerns. The diff is not a scoreboard variant — it compares two scoreboards. Keeping it separate makes it independently importable and testable.
- *Inside `benchmark.py`:* benchmark.py orchestrates run execution; it should stay focused on running cases and recording raw results. Diff rendering is presentation-layer.

**Rationale:** `baseline_diff.py` is a pure function (no I/O, no subprocess calls). `benchmark.py` calls it after `write_outputs` as the only write-side consumer. `score.py` can optionally import it via a `--diff` flag for human convenience, but the canonical output is `diff.md`.

### Decision 2: Output is `task2/benchmark/<branch>/diff.md` (committed file, not ephemeral)

**Chosen:** Write `diff.md` next to `results.json`; CI reads it back and posts it as a PR comment.

**Alternatives considered:**
- *Compute the diff in CI on the fly from the two results.json files:* would require installing Python in the comment-posting step, or duplicating logic in shell. The committed `diff.md` lets `benchmark.py` own the computation and CI only post it.
- *Append to `scoreboard.md`:* the scoreboard is the per-branch story; mixing in the delta makes it harder to read and harder to snapshot-test independently.

**Rationale:** Committing `diff.md` mirrors the existing pattern (results.json + scoreboard.md both committed). CI simply reads the file and posts it — no re-computation.

### Decision 3: Severity is binary — newly-failing = regression, everything else = advisory

**Chosen:** Only `status` regressions (was passing/unverified, now failed/skipped) are marked as regressions. Latency and cost increases are reported as deltas but not classified as regressions.

**Alternatives considered:**
- *Multi-tier severity (cost >20% increase = warning, latency >50% = warning):* valuable in theory but requires configurable thresholds and introduces false positives on noisy single-run data. The bench-repeats work (#35) makes per-case statistics more stable; adding cost/latency severity is better deferred until statistics are reliable.

**Rationale:** Simplest rule that's unambiguous. Ticket text says "a previously-passing case now failing is flagged as a regression with severity" — one severity level ("regression") is sufficient.

### Decision 4: CI posts diff via `gh pr comment --edit-last`

**Chosen:** New step in the existing `verify` job (after the verify step), using `gh pr comment --edit-last --body-file task2/benchmark/<branch>/diff.md`. If the file is absent or empty (master branch), the step is skipped.

**Alternatives considered:**
- *Separate job:* adds workflow latency and requires artifact-passing between jobs; unnecessary since `diff.md` is already in the checkout.
- *Posting scoreboard + diff together:* the scoreboard is 40+ lines; combining makes the PR comment hard to scan. The diff is the signal; link to the full scoreboard via the committed file.

**Rationale:** Minimal new YAML. `--edit-last` prevents comment proliferation on re-runs.

### Decision 5: When branch == master or master baseline is missing, diff.md is not written

**Chosen:** `benchmark.py` skips `write_diff` when `branch == "master"` or `task2/benchmark/master/results.json` does not exist. No `diff.md` is written in those cases.

**Rationale:** A missing `diff.md` is the unambiguous signal for CI to skip the comment step. Avoids writing an empty file that could confuse readers.

## Risks / Trade-offs

- **Stale master baseline:** if `task2/benchmark/master/results.json` is old (e.g. last updated months ago), the diff may show phantom improvements/regressions from unrelated work. → Mitigation: the diff header shows the `run_at` timestamp of both files so reviewers can see the baseline age.
- **Single-run noise:** without `--repeats`, a single-run pass/fail is noisy. → Mitigation: the diff flags status changes, not pass-rate fluctuations; repeats are handled separately by #35.
- **`gh` CLI not available in all CI environments:** the comment step uses `gh`, which is pre-installed on `ubuntu-latest` GitHub-hosted runners. → Mitigation: wrap in `if: github.event_name == 'pull_request'` so it only fires on PRs.
- **`--edit-last` may fail if no prior comment exists:** `gh pr comment --edit-last` requires an existing comment to edit. → Mitigation: use `gh pr comment --body-file ... --edit-last 2>/dev/null || gh pr comment --body-file ...` (create if no prior comment).

## Open Questions

- None blocking implementation. The threshold for latency/cost severity is deferred to a future ticket.
