---
id: 94
slug: readme-zeabur-task-submission-docs
status: archived
tier: 0
urgency: P0
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- 'task2/README.md ### Zeabur section currently only documents env-var setup; nothing
  tells reviewers how to submit a task to the deployed URL.'
- 'AI-Coding-Test-EN.md Task 2 acceptance: reviewer-facing URL must be exercisable
  via documented interface. Without submission docs, reviewers can''t use the URL
  even after the user fills it in.'
related:
- 18
filed_pr: null
merged_pr: 140
archived_at: '2026-04-29'
trigger: '2026-04-29 — `/full_task2` Tier 0 deliverable-gap check: README''s `###
  Zeabur` section has `<TBD>` URL placeholder AND no `Submitting a task` subsection;
  closing the docs half of bar #3 is workflow-only and unblocks reviewer use the moment
  the user fills the URL in.'
---

# Document task-submission user-flow in README's `### Zeabur` section

**Workflow-only / no production code changes — README documentation only.** Fast-path eligible.

## Why

`AI-Coding-Test-EN.md` Task 2 defines the reviewer-facing deliverable as a Zeabur URL where reviewers submit unseen natural-language tasks. The current `### Zeabur` section in `task2/README.md` (lines 181-191) only documents how to *deploy* the app (connect repo, set env vars). It does **not** document what the deployed URL exposes: the HTML form at `/`, the `POST /tasks` JSON endpoint, the `GET /tasks/{run_id}` polling endpoint, or the `GET /tasks/{run_id}/trace` event-stream endpoint.

Without this, even after the user deploys and fills in the live URL, a reviewer landing on the README has no documented path from "I have the URL" to "I submitted a task and got a structured response." This is one of the five Tier 0 bars (`task2/README.md ### Zeabur section ... documents how to submit a task`).

## Acceptance

The `### Zeabur` section in `task2/README.md` MUST contain, in addition to the existing setup paragraph:

1. **A `Submitting a task` subsection** (or equivalent) covering both interfaces:
   - **Browser form** — visit `<live-url>/` to use the HTML form (one task per submission, polls until terminal status).
   - **HTTP API** — `curl -X POST <live-url>/tasks -H 'Content-Type: application/json' -d '{"task":"..."}'` returns `{"id": "<run_id>"}`, then poll `GET <live-url>/tasks/<run_id>` until `status` ∈ `{succeeded, failed, timeout, internal_error}`.
2. **A trace-fetch line** — `GET <live-url>/tasks/<run_id>/trace` returns NDJSON of the per-step events (one JSON object per line) for reviewers who want to inspect agent behavior.
3. **A worked-example block** — a short copy-paste-ready shell snippet using a real test task (e.g. "Open https://example.com and return the H1 text") that a reviewer can run against the live URL once the `<TBD>` is replaced.
4. **Terminal-status reference** — list the four terminal `status` values (`succeeded`, `failed`, `timeout`, `internal_error`) so reviewers know when to stop polling. Optionally point to `task2/api/server.py` for the response schema.

## Out of scope

- Adding new endpoints (e.g. `/healthz`) — separate ticket if needed.
- CORS / auth changes.
- Filling in the actual `<TBD>` URL — that requires the user-side Zeabur deploy.
- Editing `prompts/task2/`, `task2/agent/`, `task2/api/`, or any test file.
- Editing top-of-README sections (Benchmarks, Setup, Running tests, etc.).

## Tests

Doc-only change — no Python test surface. Verification is:
- `grep -A 40 "### Zeabur" task2/README.md` shows the new subsection with the four required items above.
- `bash task2/smoke_test.sh` passes (unchanged behavior).
- Visual review: a reviewer reading just the `### Zeabur` section can submit a task to the deployed URL without spelunking the codebase.
