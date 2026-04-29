import json
from pathlib import Path


def test_step_breakdown_per_step_llm_dominance_in_run_json():
    """Assert LLM-per-step dominance on webvoyager-1 and encode lever ranking.

    Diagnostic: webvoyager-1 exits reason="seconds_budget" at step 13 (127s wall-clock).
    Per-step latency_breakdown_ms in the run JSON shows LLM time dominates dispatch time
    by >5x on every non-goto-initial step (steps 2-13, indices 1-12).

    Lever ranking (highest ROI first):
      (a) prompt-trim  — prompt_tokens grow 1084 → 21522 over 13 steps (20x accumulation).
          Step 13 alone takes 29.9s of LLM time on 21522 prompt tokens.
          Trimming stale tool-result messages + AX-tree noise saves ~30% of prompt tokens,
          cutting ~28s of LLM time (0.30 × 94s total LLM), bringing 127s → ~99s. WINNER.
      (b) path-shorten — saving 3 steps × 6.5s avg LLM/step saves ~20s → 127s → ~107s.
          Borderline under 120s with no margin.
      (c) observation-trim — step 1 observation_ms=12380ms; trimming AX-tree at load saves ~6s
          on the first step only → 127s → ~121s. Insufficient on its own.

    Winner: prompt-trim (lever a). Follow-up ticket #97.
    Evidence artifact:
    task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json
    """
    artifact = (
        Path(__file__).parents[1]
        / "benchmark"
        / "task2-propagate-runresult-reason-to-caseresult"
        / "webvoyager"
        / "20260429_203237.json"
    )
    data = json.loads(artifact.read_text())
    case = data["cases"][0]
    step_breakdown = case["step_breakdown"]

    assert case["reason"] == "seconds_budget"
    assert len(step_breakdown) == 13

    for step in step_breakdown[1:]:
        lb = step["latency_breakdown_ms"]
        assert lb["llm_ms"] > 5 * lb["dispatch_ms"]

    assert step_breakdown[-1]["prompt_tokens"] >= 10 * step_breakdown[0]["prompt_tokens"]
