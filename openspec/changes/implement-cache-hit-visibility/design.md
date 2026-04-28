## Context

`scripts/score.py::generate_scoreboard` renders a per-case markdown table with columns including `Cache Inv.` (sourced from `cache_events.invalidations`). The `cache_events` dict already carries `hits` and `misses` alongside `invalidations` — produced by `_aggregate_diagnostics` in `scripts/eval.py` and stored in `CaseResult.cache_events` since ticket #29. The data is present in every results JSON; it is simply not surfaced in the table.

Current per-case table header:
`| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |`

## Goals / Non-Goals

**Goals:**

- Add `Cache Hits` and `Cache Misses` columns to the per-case table, immediately left of `Cache Inv.`, reading from `cache_events.hits` and `cache_events.misses`.
- Keep full backward-compatibility: results JSON files missing `cache_events` keys default to `0` for both new columns (matching existing `Cache Inv.` behavior).
- Add tests asserting the new columns appear in the header and contain correct values.
- Regenerate the golden snapshot `tests/fixtures/results/sample_results_scoreboard.md` as part of implementation.

**Non-Goals:**

- Changing `CaseResult`, `_aggregate_diagnostics`, `eval.py`, `baseline_diff.py`, or any agent code.
- Adding cache-related rows to the Mechanism firing rates block (only invalidations appear there; hits/misses are per-case).
- Adding a `Cache Hits` / `Cache Misses` firing-rate row to the mechanism block (invalidations are already the relevant signal there).

## Decisions

**Decision 1: Column order — hits / misses / invalidations.**

Convention matches the logical flow of a locator cache lookup: first a hit is attempted (hit or miss), then the cache may be invalidated on a fingerprint change. This ordering also matches the dict key order `{"hits": ..., "misses": ..., "invalidations": ...}` already produced by `_aggregate_diagnostics`. Alternative (invalidations first) was considered but rejected as it breaks the cache-lookup narrative.

**Decision 2: MODIFIED requirement, not a new requirement.**

The existing requirement "score.py reads a results JSON and emits a markdown scoreboard" governs the per-case table column list. Adding two columns changes that contract, making this a MODIFIED delta — the title already exists in `openspec/specs/score-script/spec.md`. A brand-new requirement titled "Cache hits and misses surfaced in scoreboard" would be correct structure only if the column list were not already specified there.

**Decision 3: Backward-compat default of 0.**

`case.get("cache_events", {}).get("hits", 0)` mirrors the pattern already used for `cache_inv`. No schema migration needed; old result files render `0` for both new columns.

**Decision 4: No change to baseline_diff.py.**

`baseline_diff.py` computes aggregate deltas (pass-rate, USD, latency). Cache hit/miss counts are per-case detail, not an aggregate metric suitable for a diff block. The diff block already omits `Cache Inv.`; adding hits/misses there is out of scope for this ticket.

## Risks / Trade-offs

- **Golden snapshot breakage**: The golden snapshot `sample_results_scoreboard.md` will differ after the header widens. Implementer must regenerate it as part of the green phase. Risk is low — it is a known, expected artifact update.
- **Test assertions on the old header string**: Any test asserting the exact header string `"| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |"` will fail. Review `test_score.py` and update those assertions. The existing `test_generate_scoreboard_mechanism_columns_in_header` asserts `"Cache Inv." in output` — this still passes (the column stays, just two new ones are added left of it).

## Open Questions

_(none — the data is available, the design is unambiguous)_
