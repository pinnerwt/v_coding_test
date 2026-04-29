# Template registry

Lookup table for `/new_task2` step 4's template-cache step. Each row maps a ticket signature to a template directory. See `README.md` for the signature scheme and template format.

## Format

| signature.tier | signature.primary_axis | signature.first_touched_file_pattern | template_dir | version | description |
|---|---|---|---|---|---|

- `signature.tier` — exact match on the ticket's `tier:` frontmatter (1–6).
- `signature.primary_axis` — exact match on `pass_rate`, `tokens_pct`, `latency_pct`, or `n/a`.
- `signature.first_touched_file_pattern` — fnmatch-style glob; matches against the first inline-backticked file path in the ticket body, reduced to its directory shape. Use `*` for "any file in this directory", `**` for "any file under this subtree".
- `template_dir` — relative path under `.claude/skills/opsx/templates/`.
- `version` — integer matching `META.yaml`'s `version` field.
- `description` — one-line summary.

## Lookup procedure

1. Read the ticket's frontmatter; extract `tier`, the dominant `axes` field (largest absolute value, or `n/a` if all zero).
2. Grep the ticket body for the first inline-backticked file path; reduce to glob shape.
3. Walk the table top-to-bottom; the first row whose three signature fields all match wins.
4. If multiple rows tie at the same specificity, the lookup is ambiguous — surface to the user, do not auto-pick.
5. If no row matches, fall through to from-scratch artifact generation (current `/opsx:ff` behavior).

## Active templates

| signature.tier | signature.primary_axis | signature.first_touched_file_pattern | template_dir | version | description |
|---|---|---|---|---|---|
| 5 | n/a | task2/agent/*.py | tier5-agent-module | 1 | Tier-5 ticket adding a new module or extending one module under task2/agent/ (e.g. new tool branch in loop.py, new helper module like observe / supervisor, single-capability extension). |
| 2 | n/a | task2/scripts/*.py | tier2-scoreboard-math | 1 | Tier-2 ticket adding or extending a scoreboard / baseline-diff / trends / failure-classification field rendered by task2/scripts/*.py (helper-then-render pattern with backward-compatible defaults). |
