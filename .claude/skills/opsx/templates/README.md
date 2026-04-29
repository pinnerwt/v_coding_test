# `/opsx:ff` artifact templates

Cache of starting-point skeletons for `proposal.md` / `design.md` / `tasks.md` / `specs/<capability>/spec.md`, keyed by ticket-shape signature.

## Why this exists

`/new_task2` step 4 dispatches a sonnet subagent to invoke `/opsx:ff` and produce all four artifacts from scratch each iteration. Many task2 tickets generate near-identical structures (e.g. tier-2 scoreboard-math tweaks, tier-5 new-tool additions to `agent/_dispatch`, tier-1 process-doc updates). Regenerating them costs ~30–60s of sonnet runtime per artifact pass; that compounds across `/auto_task2`'s 8-iteration ceiling. With a matching template the subagent edits placeholders rather than authoring from a blank page.

The cache is **opt-in** and **fallback-safe**: if no template matches a ticket's signature, the subagent proceeds exactly as today (from-scratch generation via `/opsx:ff`). Adding wrong templates can regress artifact quality; the validate-against-archive gate (below) is the safety net.

## Signature scheme

A template is keyed by `(tier, primary_axis, first_touched_file_pattern)`:

- **`tier`** (int, 1–6) — read from the ticket's `tier:` frontmatter field. The same six tiers used by `/new_task2` step 1's selection rule (1=process, 2=measurement, 3=stop-the-bleeding, 4=diagnostic, 5=benchmark-impact, 6=hygiene).
- **`primary_axis`** (string) — the axis with the largest absolute value among the ticket's `axes:` frontmatter (`pass_rate`, `tokens_pct`, `latency_pct`). Use `n/a` when all three are 0 (typical for tier-1, tier-2, tier-6 tickets).
- **`first_touched_file_pattern`** (glob) — derived from the ticket body. Take the first inline-backticked file path the body cites and reduce it to its directory-glob shape (e.g. `task2/scripts/score.py` → `task2/scripts/score.py`; `agent/locate.py` → `task2/agent/locate.py`; multiple files in same directory → `task2/agent/*.py`).

A signature matches a template when **all three fields equal-match or glob-match** the template's declared signature. Closest match wins; tied matches are an error (surface to user, do not auto-pick).

## Directory layout

Each template lives under its own subdirectory:

```
.claude/skills/opsx/templates/
├── README.md                             # this file
├── INDEX.md                              # signature → template registry
└── <signature-slug>/
    ├── META.yaml                         # signature, version, when-to-use
    ├── proposal.md                       # skeleton with {{placeholders}}
    ├── design.md                         # skeleton
    ├── tasks.md                          # skeleton (delta-checkbox format)
    └── specs/
        └── <capability>/
            └── spec.md                   # delta-format skeleton
```

`<signature-slug>` is a short kebab-case label (e.g. `tier2-scoreboard-math-tweak`, `tier5-agent-dispatch-tool`) that names the recurring pattern.

## `META.yaml` fields

```yaml
signature:
  tier: 2
  primary_axis: n/a
  first_touched_file_pattern: task2/scripts/{score,eval}.py
version: 1
description: >
  Tier-2 measurement ticket adding a new per-case field to eval.py and
  rendering it through score.py's per-case status cell.
when_to_use: >
  Ticket frontmatter has tier=2 and the body's first backticked file is
  task2/scripts/score.py or task2/scripts/eval.py. Typical pattern: add
  CaseResult field, helper, propagate to scoreboard render.
when_not_to_use: >
  Ticket touches multiple unrelated scripts; ticket changes scoreboard
  layout (column add/remove) — needs richer scaffolding than the skeleton
  provides.
```

The `version` integer increments on any breaking change to the skeleton. `/new_task2` step 4 passes the version to the subagent in its prompt; if `/opsx:ff` evolves and the template is no longer compatible (e.g. a required artifact gained new sections), the subagent surfaces a version-mismatch error rather than silently producing stale-shaped artifacts.

## Placeholder format

Skeletons use `{{double_brace}}` placeholders for ticket-specific values. Conventional names:

- `{{ticket_number}}`, `{{ticket_title}}`, `{{ticket_slug}}`
- `{{capability}}` (e.g. `eval-runner`, `score-script`)
- `{{symbols}}` (the dataclass / function names being added or modified)
- `{{file_path}}` (the primary file the change lives in)
- `{{rationale_one_liner}}` (subagent fills from the ticket's *Why useful* paragraph)

The subagent is instructed to fill every `{{...}}` placeholder before writing the artifact; a leftover `{{` in the final file is a bug and `openspec validate --strict` will not catch it (placeholders are not OpenSpec syntax errors).

## Validation gate (mandatory before commit)

When a template is used, the subagent MUST run `openspec validate --strict` against the rendered artifacts before reporting back. Validation failure means the template's assumptions did not hold for this ticket; the subagent must discard the templated output and fall back to from-scratch generation. This is the safety net that prevents a wrong-shape template from corrupting the artifact stream.

## Validate-against-archive discipline

When adding or modifying a template, run the retroactive check on every archived change whose signature matches: re-render the template against the archived ticket's frontmatter and body, then confirm the resulting `proposal.md` / `design.md` / `tasks.md` / `specs/<cap>/spec.md` pass `openspec validate --strict` and structurally resemble the archived artifacts. A new template is only approved when at least 2 archived signature-matching changes validate clean. Tracked separately as a future tooling ticket.

## Adding a new template

1. Survey 3+ archived changes under `openspec/changes/archive/` whose signatures match.
2. Extract the common skeleton — bullets that recur across every archived `proposal.md` become skeleton lines; per-ticket specifics become `{{placeholders}}`.
3. Write `META.yaml` with `version: 1` and a precise `when_not_to_use` that distinguishes the template from neighboring patterns.
4. Add the entry to `INDEX.md` with the signature triple and the template directory.
5. Run the retroactive validation against every archived signature-match.
6. Commit as `chore(skills): add opsx:ff template for <pattern>`.
