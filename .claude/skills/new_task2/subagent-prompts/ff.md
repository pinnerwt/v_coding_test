# Subagent prompt — opsx:ff (artifact generation)

Pass this verbatim to a `general-purpose` subagent (`model: sonnet`) at Step 4 of `/new_task2`. The orchestrator substitutes the placeholders (`{{...}}`) before sending.

Description for the Agent call: `Generate opsx artifacts for {{change-name}}`.

---

You are generating OpenSpec artifacts for change `{{change-name}}` in the `vici` repo. You have no prior conversation context — everything you need is below.

**Ticket**

- Number: {{ticket-number}}
- Title: {{ticket-title}}

Full ticket text from `task2/plan.md`:

```
{{ticket-text}}
```

**Task**

Invoke the `/opsx:ff` skill on `{{change-name}}`. This produces every artifact required for `/opsx:apply` — typically `proposal.md`, `design.md`, `tasks.md`, and one or more `specs/<capability>/spec.md` deltas.

**Hard constraints**

- Do not commit, push, or open a PR.
- Do not implement code — artifacts only.
- Stay on the current branch.

**Grounding sources to read before drafting**

- `task2/plan.md` — full ticket text and acceptance criteria.
- `task2/CLAUDE.md` and the rest of `task2/` — code conventions, directory layout, and existing module shapes.
- Repo-root `CLAUDE.md` — TDD non-negotiable, `uv` + `ruff` tooling, no hardcoded LLM provider.

**Report back**

- List every file you created under `openspec/changes/{{change-name}}/` (path + one-line purpose).
- Any open questions or assumptions you made when the ticket text was ambiguous.
