## Context

`task2/scripts/score.py` already emits a full markdown scoreboard from a results JSON. The existing `generate_scoreboard()` function renders: header line, per-case table, summary line, latency percentiles, totals, locator-tier mix, and mechanism firing rates. The Done-bar thresholds (drift 100%, fixture 80%, live 60%) are defined in `task2/plan.md` but are invisible in the scoreboard output. Ticket #33 requires surfacing them as a category summary table above the per-case table so suite health is immediately visible.

## Goals / Non-Goals

**Goals:**

- Add a module-level `SUITE_THRESHOLDS` config block in `score.py` (no magic numbers in logic).
- Derive suite membership from case `id` prefix matching (not the YAML `category` field, which `score.py` does not see).
- Prepend a category summary table to the scoreboard output, before the existing per-case table.
- Emit traffic-light glyphs: ✅ (met, at least one ran), ❌ (missed, at least one ran), ⏭️ (zero ran).
- Test with a hand-authored vendored fixture covering all three traffic-light states.

**Non-Goals:**

- Changing the per-case table, summary line, percentiles, totals, tier mix, or mechanism rates.
- Reading the YAML `category` field at scoreboard time.
- Modifying the CLI interface or README sentinel format.
- Dynamic threshold configuration (file-based or env-based) — module-level constant is sufficient.

## Decisions

### Suite derivation: id prefix matching, not YAML category field

`score.py` only sees the results JSON; it has no access to case YAML at scoreboard time. Case IDs already carry suite information in their prefixes (`drift-`, `fixture-`, `live-`, `maintenance-drift-`, `correction-`). Prefix matching against `SUITE_THRESHOLDS[suite]["id_prefixes"]` is O(n·p) and deterministic. Cases not matching any prefix fall into an "other" bucket with no threshold, rendered without a traffic-light glyph.

**Alternative considered**: encoding suite in the results JSON at eval time. Rejected — it would require touching the eval pipeline and the results schema, adding scope beyond ticket #33.

### Correction cases → drift suite

The brief's "drift suite 100%" target covers self-correction and self-maintenance cases. `correction-*` cases are diagnostic for the self-repair capability and count toward the same 100% target. Including them in drift via `id_prefixes: ["drift-", "maintenance-drift-", "correction-"]` keeps the denominator honest and matches the spirit of the Done bar.

### Summary table placement: above per-case table

The summary table is the first thing a reviewer needs to know. Placing it immediately after the run header (before the per-case table) matches the ticket's described output format and makes the traffic lights the first visual element.

### Traffic-light symbols: ✅ / ❌ / ⏭️

- ✅ Unicode U+2705 — universally rendered on GitHub, terminals, and markdown previewers.
- ❌ Unicode U+274C — visually unambiguous failure.
- ⏭️ Unicode U+23ED — skip/fast-forward; conveys "nothing ran" without implying pass or fail.

The "ran" denominator excludes `status == "skipped"` cases, consistent with the existing per-case table treatment.

### Config block shape: module-level `SUITE_THRESHOLDS` dict

A `dict[str, dict]` keyed by suite identifier makes it easy to iterate in a stable order (Python 3.7+ insertion order) and to look up or extend suites without scattering literals through the logic. Each entry carries `name` (display string), `id_prefixes` (list of strings), and `target_pct` (int). This is the shape specified in ticket #33.

## Risks / Trade-offs

- [Risk] A new case id that doesn't follow existing prefix conventions will silently land in "other" with no threshold. → Mitigation: "other" bucket is visible in the summary table; implementers will see it in test output.
- [Risk] The category summary table is rendered as plain text lines (not a markdown table) per the ticket's example format. If reviewers prefer a markdown table, the format will need revisiting. → Mitigation: the spec scenario tests the exact rendered lines; changing format requires updating the spec first.
- [Risk] Unicode glyphs may not render in some CI log environments. → Acceptable: GitHub markdown and the Zeabur-hosted README render them correctly.

## Open Questions

None — all design decisions are resolved above.
