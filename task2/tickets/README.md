# task2/tickets/

Per-ticket Markdown files for Task 2. Each file is the canonical record for one TDD ticket.

## Directory layout

```
task2/tickets/
  active/     tickets with status: active or in-flight
  archive/    tickets with status: merged, archived, or dropped
  INDEX.md    generated table (one row per ticket) — do not edit by hand
  README.md   this file
```

Files are named `<NNN>-<slug>.md` where `<NNN>` is the ticket id zero-padded to at least 3 digits.

## Frontmatter schema

Every file MUST begin with a YAML frontmatter block delimited by `---` lines containing all 14 fields:

| Field | Type | Allowed values |
|---|---|---|
| `id` | int | unique, monotone |
| `slug` | string | kebab-case, max 6 words |
| `status` | string | `active`, `in-flight`, `merged`, `archived`, `dropped` |
| `tier` | int | 1–6 (see Tier definitions below) |
| `urgency` | string | `P0`, `P1`, `P2`, `P3` |
| `axes` | mapping | three int sub-fields: `pass_rate`, `tokens_pct`, `latency_pct` |
| `dependencies` | list[int] | ticket ids that must be merged first; `[]` when none |
| `pre_flight_gates` | list[str] | gate identifiers from the vocabulary below; `[]` when none |
| `evidence` | list[str] | relative paths to supporting artifacts; `[]` when none |
| `related` | list[int] | related ticket ids (not hard dependencies); `[]` when none |
| `filed_pr` | int or null | PR number where this ticket was first filed |
| `merged_pr` | int or null | PR number that merged this ticket; null when not merged |
| `archived_at` | string or null | ISO-8601 date (YYYY-MM-DD) when archived; null when active |
| `trigger` | string | "YYYY-MM-DD — workflow event that surfaced this ticket" |

### Tier definitions

| Tier | Category |
|---|---|
| 1 | Process / workflow correctness and standards-setting |
| 2 | Measurement / observability correctness |
| 3 | Stop-the-bleeding correctness regressions |
| 4 | Diagnostic / audit unblockers |
| 5 | Benchmark-impact tickets |
| 6 | Hygiene (refactor, dead-code removal, doc-only) |

### Pre-flight gate vocabulary

| Gate | Meaning |
|---|---|
| `no-other-task2-prs-open` | No other task2 PR may be open when this ticket lands |
| `qwen-reachable` | `http://localhost:8090/v1/models` must respond before starting |
| `no-benchmark-in-flight` | No benchmark run may be in progress |

### axes sub-fields

All three are integers representing estimated percentage impact (positive = improvement, negative = regression):

- `pass_rate` — expected change in WebVoyager pass rate (e.g. `+20` for an expected +20% improvement)
- `tokens_pct` — expected change in total tokens per run (e.g. `-15` for -15% token reduction)
- `latency_pct` — expected change in p50/p95 latency (e.g. `-10` for -10% latency reduction)

Use `0` when impact on that axis is unknown or negligible.

## Skill consumer contract

| Skill | Reads | Writes |
|---|---|---|
| `/new_task2` step 1 | `task2/tickets/INDEX.md` only (for scoring/selection); then pages in the selected ticket file for full body | — |
| `/new_task2` step 11 | — | New `task2/tickets/active/<NNN>-<slug>.md`; runs `regen_tickets_index.py` |
| `/done_pr` step 1b / 1b' | — | New ticket files under `active/`; runs `regen_tickets_index.py` |
| `/done_pr` step 1c | `task2/tickets/active/<NNN>-*.md` | `git mv` to `archive/`; updates `status`, `merged_pr`, `archived_at`; runs `regen_tickets_index.py`; one commit |
| `/review_task2` step 3 | `task2/tickets/active/` (cross-check grep) | — |

## How to regen INDEX.md

```bash
cd /path/to/repo
uv run python task2/scripts/regen_tickets_index.py
```

The script reads all `active/*.md` and `archive/*.md` frontmatter using PyYAML and writes `INDEX.md` with:
- Active section: sorted ascending by `id`
- Archive section: sorted ascending by `archived_at` (then `id` as tie-breaker)

Running the script twice in a row produces byte-identical output (idempotent).

## Adding a new ticket

1. Find the highest existing id: `ls task2/tickets/active/ task2/tickets/archive/ | grep -oE '^[0-9]+' | sort -n | tail -1`
2. Write `task2/tickets/active/<NNN>-<slug>.md` with all 14 required frontmatter fields and a self-contained body.
3. Run `uv run python task2/scripts/regen_tickets_index.py`.
4. Stage both files and commit: `docs(task2): file ticket #<N> — <short title>`.

## Archiving a ticket (merging a PR)

Run `/done_pr` step 1c or manually:

```bash
git mv task2/tickets/active/<NNN>-<slug>.md task2/tickets/archive/<NNN>-<slug>.md
# Edit the moved file: set status: archived, merged_pr: <PR>, archived_at: YYYY-MM-DD
uv run python task2/scripts/regen_tickets_index.py
git add task2/tickets/archive/<NNN>-<slug>.md task2/tickets/INDEX.md
git commit -m "docs(task2): archive ticket #<N> — <short title>"
```
