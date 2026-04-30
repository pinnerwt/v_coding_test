# vici — AI Coding Test

[![task2 CI](https://github.com/pinnerwt/v_coding_test/actions/workflows/task2-ci.yml/badge.svg?branch=master)](https://github.com/pinnerwt/v_coding_test/actions/workflows/task2-ci.yml)
[![task2 benchmark](https://github.com/pinnerwt/v_coding_test/actions/workflows/task2-benchmark.yml/badge.svg)](https://github.com/pinnerwt/v_coding_test/actions/workflows/task2-benchmark.yml)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-025E8C?logo=dependabot&logoColor=white)](https://github.com/pinnerwt/v_coding_test/network/updates)
[![Coverage (task2)](https://img.shields.io/badge/coverage-83%25%20line%20%2F%2063%25%20branch-yellowgreen)](task2/coverage.xml)
[![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/packaging-uv-261230?logo=python&logoColor=white)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=000)](https://github.com/astral-sh/ruff)
[![OpenSpec](https://img.shields.io/badge/workflow-OpenSpec-6E56CF)](openspec/)

This repo solves the three tasks defined in [`AI-Coding-Test-EN.md`](AI-Coding-Test-EN.md) (Chinese: [`AI-Coding-Test-ZH.md`](AI-Coding-Test-ZH.md)). The whole repo is **test-driven** and developed in the open with Claude Code, using OpenSpec for spec-first changes and `uv` + `ruff` for Python tooling. See [`CLAUDE.md`](CLAUDE.md) for the operating rules.

## Tasks

| #  | Title                                          | Status         | Where                  |
|----|------------------------------------------------|----------------|------------------------|
| 1  | GitHub CI/CD as Claude Skills                  | not started    | —                      |
| 2  | Generalized Browser Automation Agent           | in progress    | [`task2/`](task2/)     |
| 3  | SEC 10-K Item-level Structured Extraction      | not started    | —                      |

Zeabur URLs land in each task's README once deployed.

## Repository layout

```
.
├── AI-Coding-Test-EN.md      # the brief
├── CLAUDE.md                  # repo-wide operating rules (TDD, uv, ruff)
├── .github/
│   ├── workflows/             # CI + benchmark workflows
│   ├── dependabot.yml         # weekly uv + github-actions updates
│   └── PULL_REQUEST_TEMPLATE.md
├── openspec/                  # spec-first changes (changes/, specs/)
├── prompts/                   # key prompts used to drive development
└── task2/                     # browser automation agent (uv project)
```

## Quick start (task 2)

```bash
cd task2
uv sync
uv run playwright install chromium   # one-time post-install browser fetch
uv run pytest                         # tests
uv run ruff check . && uv run ruff format --check .
```

See [`task2/README.md`](task2/README.md) for the operator's guide (Docker, env vars, Zeabur, eval scoreboard).

## Development workflow

- **TDD is non-negotiable.** Red → green → refactor. Bug fixes start with a regression test. Eval sets count as tests for tasks 2 and 3. See [`CLAUDE.md`](CLAUDE.md).
- **OpenSpec** drives non-trivial changes — see [`openspec/changes/`](openspec/changes/) and [`openspec/specs/`](openspec/specs/). Use the `opsx:*` slash commands (`/opsx:new`, `/opsx:apply`, `/opsx:verify`, `/opsx:archive`).
- **Conventional commits** scoped by task: `feat(task2): ...`, `fix(task2): ...`, `test(task2): ...`, `chore(ci): ...`.
- **Python:** `uv` for env / deps (`uv sync`, `uv add`, `uv run`), `ruff` for lint and format. Don't use `pip`, `poetry`, `venv`, `black`, or `flake8`.
- **No `--no-verify`**, no mocking the LLM in LLM-contract tests, no weakening tests to pass CI.

## CI/CD

GitHub Actions live in [`.github/workflows/`](.github/workflows/):

- **`task2-ci.yml`** — runs on pushes to `master` and PRs touching `task2/` or its workflow file. Installs `uv`, syncs deps with `--frozen`, installs Chromium for Playwright, runs `ruff check`, `ruff format --check`, and `pytest --cov-report=xml`. Coverage XML is uploaded as a build artifact (`task2-coverage`).
- **`task2-benchmark.yml`** — runs on PRs to `master`, verifies a benchmark record exists for the branch since the merge-base.

Concurrency is keyed by ref so superseded runs cancel themselves.

## Dependabot

Configured in [`.github/dependabot.yml`](.github/dependabot.yml):

| Ecosystem        | Directory   | Cadence | Commit prefix    | Labels                     |
|------------------|-------------|---------|------------------|----------------------------|
| `uv`             | `/task2`    | weekly  | `chore(task2)`   | `dependencies`, `task2`    |
| `github-actions` | `/`         | weekly  | `chore(ci)`      | `dependencies`, `ci`       |

Open PRs are capped at 5 per ecosystem. Dependabot PRs are subject to the same CI gates as human PRs.

## Test coverage

The latest `task2/coverage.xml` reports **83% line coverage** and **63% branch coverage** across `task2/agent`, `task2/api`, and the supporting scripts. To regenerate locally:

```bash
cd task2
uv run pytest --cov-report=xml --cov-report=term
```

CI also produces `coverage.xml` on every PR — download it from the run's `task2-coverage` artifact. Coverage is not yet published to an external service (Codecov, etc.); the badge above reflects the committed snapshot.

## Prompts

The `prompts/` directory is read by the reviewers — it is the AI-collaboration record:

- [`prompts/01_general.md`](prompts/01_general.md) — repo-wide setup prompts (CLAUDE.md, uv, ruff).
- [`prompts/02_task2.md`](prompts/02_task2.md) — task 2 prompts: planning, skill creation (`/new_task2`, `/done_pr`, `/review_task2`), API server, eval runner.
- [`prompts/task2/`](prompts/task2/) — focused prompt files for sub-decisions (locator strategies, web benchmarks, deciding mechanisms).

## Deployment

Each task is deployed as a public service on [Zeabur](https://zeabur.com/) per the brief. URLs are added to each task's README once live.

- task 2: see [`task2/README.md`](task2/README.md#deployment) for Docker, env vars (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `DB_PATH`), and the `task2/zeabur.json` build config.

## Contributing / collaborating

This is a personal coding-test submission, not an open-source project — issues and PRs from outside collaborators aren't expected. The PR template at [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) documents the per-PR checklist used during development (state-before/state-after diagrams, test evidence, OpenSpec change link).

## License

No license file is included; the work is submitted for evaluation per the test brief. Treat all rights as reserved unless otherwise stated.

---

## Appendix — development log

Preserved from earlier dev notes; the per-skill prompts themselves live in [`prompts/02_task2.md`](prompts/02_task2.md).

### Skills created

- **`/new_task2`** — read `task2/plan.md`, derive the next ticket, create an OpenSpec change with `/opsx:new` + `/opsx:ff`, branch + commit, drive `/opsx:apply`, run smoke + `/opsx:verify` + `/simplify`, then open a PR. Worker subagents downgraded from Opus to Sonnet for non-planning work.
- **`/done_pr`** — `/opsx:archive`, commit spec updates, push, merge, sync `master`.
- **`/review_task2`** — `codex exec "review the diff against master"` → orchestrator (Opus) writes the implementation plan → Sonnet subagent applies fixes → `/simplify` → loop until no changes.

### Process (rough chronology)

1. Plan task 2 with Opus 4.7; add a `Trace` schema for replayable decisions.
2. Implement first ticket end-to-end; add CI; build `/new_task2` skill.
3. Loop tickets through `/new_task2`; review with `/review_task2` + manual codex on the GitHub UI.
4. Add benchmarks (web search), smoke test, eval metrics; close with `/done_pr`.
5. As the time went by, letting claude to open tickets itself, and review with other sub agents (codex out of quota during the developement). Adjusting the priority in different directions as well to avoid over engineering.
6. Found that it's too slow with openspec + TDD + ticket resolving despite the stability and testability, so create a new research branch which focuses only on the successful rate + latency + token usage.
7. Once the agent has basic functionalities, use webvoyager benchmark to test the agent. Review the tests along with the AI and try to reach more successful rate without being too specific for certain edge cases.
8. Try out special cases for
  - vision click (like what claude MCP do)
  - Cloudflare bypass
  - Caching test
  - Model switch for planning and supervisor

### If I would do this another time
1. Define the spec very clearly at the very beginning, avoid the over-engineering while letting claude create tickets itself. Define clear metric (successful rate first, then latency/token usage) to be optimized. Define the correct benchmarks to be run.
2. While saying defining the spec very clearly, it should include the whole pipeline from "accepting users intent" to "output result", e.g. "planning" -> "loop" -> "planning"/"results" process, with different components. Cut the spec into different stages.
3. If maintenance is important, I think we can cut "Planning" -> "Tests" -> "Developement" -> "PR" -> "Review"/"Refactor" -> "Merge" into different subagents, and use a topological sort of tickets according to their dependencies. In this case, we can maximize the efficiency of developement in time. The token usage is not 
3. By-ticket implementation is still necessary. I still don't trust in long context coding skills in AI so far.
4. Avoid openspec. If the spec 


### Optimization findings

- Subagent model assignment: only planning uses Opus 4.7; implementer/verifier subagents use Sonnet to control cost and latency.
- Implementer subagents tended to add comments/docstrings that `/simplify` strips later — instructed implementers up front to skip those, removing a wasted edit cycle.
