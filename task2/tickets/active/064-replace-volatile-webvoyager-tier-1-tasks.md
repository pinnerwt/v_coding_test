---
id: 64
slug: replace-volatile-webvoyager-tier-1-tasks
status: active
tier: 2
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 63
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #98 on 2026-04-28; deferred because the
  swap requires Tier-1 baseline data to identify which originals actually flake.'
---

64. **Replace volatile WebVoyager Tier-1 tasks with stable alternatives once baseline data is in hand.** The Tier-1 dataset vendored under #63 (`task2/eval/bench/data/webvoyager/tier1.json`) includes several tasks whose ground-truth answers drift over time: id 102 Wikipedia Tokyo population, id 105 GitHub pytorch/pytorch open-issue count, id 107 HuggingFace bert-base-uncased download count, id 108 HuggingFace Mistral-7B-v0.1 license (license fields on HF model cards are mutable when upstream relicenses), id 109 BBC News top headline, id 110 BBC News Science & Environment first article. The current `answer.nonempty` validator (added by `load_webvoyager` to every case as part of the `expect` block — the field is loader-derived, not present in the vendored JSON) accepts any non-empty answer, so the cases pass for "agent reached `done` with text" rather than "agent extracted the right value" — the cases lose specificity as a regression signal. Once the Tier-1 `--live` baseline runs (deferred from #63 task 6.1) reveal which cases consistently *fail* on volatility (e.g. headline rotation between request and validation), swap them for stable alternatives that exercise the same locator-pipeline patterns: e.g. id 102 → "What year was Tokyo officially declared the capital of Japan?" (immutable historical fact), id 105 → "What is the default branch name of pytorch/pytorch?" (stable repo metadata), id 107 → "What architecture family does bert-base-uncased belong to?" (stable model card field), id 108 → architecture family or original release date instead of license, id 109/110 → permalinked BBC article URLs whose body answers a fixed question. The swap requires extending the loader (`task2/eval/bench/webvoyager_loader.py`) to read a per-entry validator hint from the JSON (e.g. an optional `validator` key) and override the default `answer.nonempty`; alternatively, vendor the per-task `expect` block alongside the upstream schema. Acceptance: each replaced task's answer is a static string verifiable by `answer.contains("...")` or `answer.equals("...")` validator instead of `answer.nonempty`; Tier-1 baseline pass-rate on the swapped tasks is ≥ pass-rate on the originals across 3 consecutive runs. Tests: a unit test asserting each swapped task's loader-output `expect.validators` does NOT contain `"answer.nonempty"` (the test inspects the dict returned by `load_webvoyager`, not the raw JSON, since `expect` is loader-derived). *Why useful:* volatile-answer tasks pass mechanically (`done` with any text) and add noise to the regression signal; stable-answer tasks let the validator catch real extraction failures, which is the actual point of a benchmark gate. *Trigger:* surfaced by review subagent on PR #98 on 2026-04-28; deferred because the swap requires Tier-1 baseline data to identify which originals actually flake.
