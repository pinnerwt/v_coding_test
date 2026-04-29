---
id: 50
slug: per-repeat-cache-semantics-when-shared
status: active
tier: 5
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 37
- 75
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #75 (iteration 1).'
---

50. **Per-repeat cache semantics when `shared_cache=True and variants and --repeats > 1`.** `task2/scripts/benchmark.py::aggregate_repeats` shares a single `LocatorCache` across all N repeats of each variant when `parent_case.shared_cache=True`. Combined with the variant loop, that means a fixture like `eval/cases/maintenance-drift-rename.yaml` (the only current `shared_cache: true` case) runs `len(variants) × N` times against a single warm cache, biasing latency and USD downward versus the `--repeats 1` contract (where the cache is shared across variants but each variant runs once cold). Decision needed: (a) reset the cache between repeats (cold-start each repeat for the same variant), (b) document the warm-cache choice as intentional and add a test fixing the semantics, or (c) parametrize with a `--cold-cache` flag. Tests: an `aggregate_repeats(case_with_shared_cache, repeats=3, cache=<spy>, ...)` call records the chosen semantics (e.g. spy is reset 3 times for option (a), once for option (b)). *Why useful:* current behavior makes flake-detection less reliable for the only `shared_cache` case, which is exactly the maintenance-drift case the canary suite (#37) will likely include. *Trigger:* surfaced by review subagent on PR #75 (iteration 1).
