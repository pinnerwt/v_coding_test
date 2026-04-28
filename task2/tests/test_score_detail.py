from __future__ import annotations

from scripts.score import _render_step_breakdown, generate_scoreboard

_STEP1 = {
    "step": 1,
    "tool_calls": ["goto"],
    "prompt_tokens": 100,
    "completion_tokens": 10,
    "latency_ms": 500,
}
_STEP2 = {
    "step": 2,
    "tool_calls": ["click"],
    "prompt_tokens": 120,
    "completion_tokens": 15,
    "latency_ms": 300,
}
_STEP3 = {
    "step": 3,
    "tool_calls": ["done"],
    "prompt_tokens": 80,
    "completion_tokens": 8,
    "latency_ms": 200,
}

_HEADER = "| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |"


def _make_data(status: str, steps: list[dict]) -> dict:
    return {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {
                "id": "test-case-v1",
                "status": status,
                "steps": len(steps),
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": sum(s.get("prompt_tokens", 0) for s in steps),
                "completion_tokens": sum(s.get("completion_tokens", 0) for s in steps),
                "latency_ms_total": sum(s.get("latency_ms", 0) for s in steps),
                "latency_ms_per_step": [s.get("latency_ms", 0) for s in steps],
                "step_breakdown": steps,
                "escalations": [],
                "replans": 0,
                "cache_events": {"hits": 0, "invalidations": 0, "misses": 0},
            }
        ],
    }


def test_detail_flag_emits_step_table_for_failing_case():
    data = _make_data("failed", [_STEP1, _STEP2])
    output = generate_scoreboard(data, detail=True)
    assert _HEADER in output
    assert "| 1 | goto | 100 | 10 | 500 |" in output
    assert "| 2 | click | 120 | 15 | 300 |" in output


def test_detail_flag_no_table_for_passing_case():
    data = _make_data("succeeded", [_STEP1, _STEP2])
    output = generate_scoreboard(data, detail=True)
    assert "Prompt Tokens" not in output


def test_default_mode_emits_details_block_for_failing_case():
    data = _make_data("failed", [_STEP1, _STEP2, _STEP3])
    output = generate_scoreboard(data)
    assert "<details><summary>step breakdown (3 steps)</summary>" in output
    assert "</details>" in output


def test_default_mode_no_details_block_for_passing_case():
    data = _make_data("succeeded", [_STEP1, _STEP2])
    output = generate_scoreboard(data)
    assert "<details>" not in output


def test_render_step_breakdown_empty_returns_empty_string():
    assert _render_step_breakdown([]) == ""


def test_render_step_breakdown_single_step_contains_columns():
    step = {
        "step": 1,
        "tool_calls": ["goto"],
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "latency_ms": 500,
    }
    result = _render_step_breakdown([step])
    assert _HEADER in result
    assert "| 1 | goto | 100 | 10 | 500 |" in result
