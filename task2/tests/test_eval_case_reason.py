from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent.loop import RunResult
from scripts.eval import _run_case, run_suite

_FIXTURE_CASE = {
    "id": "fixture-heading",
    "domain": "fixture",
    "category": "read-and-summarize",
    "task": "Read the page heading and return it as title",
    "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}


def test_run_case_propagates_reason_seconds_budget():
    canned = RunResult(
        status="timeout",
        result=None,
        evidence=None,
        verifier=None,
        reason="seconds_budget",
        steps=15,
        prompt_tokens=100,
        completion_tokens=50,
        usd=0.05,
        latency_ms_total=120000,
    )
    with patch("scripts.eval.loop", return_value=canned):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.reason == "seconds_budget"


def test_run_case_propagates_reason_no_progress():
    canned = RunResult(
        status="failed",
        result=None,
        evidence=None,
        verifier=None,
        reason="no_progress",
        steps=4,
        prompt_tokens=100,
        completion_tokens=50,
        usd=0.005,
        latency_ms_total=2000,
    )
    with patch("scripts.eval.loop", return_value=canned):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.reason == "no_progress"


def test_run_case_propagates_reason_no_tool_call_repeat():
    canned = RunResult(
        status="failed",
        result=None,
        evidence=None,
        verifier=None,
        reason="no_tool_call_repeat",
        steps=3,
        prompt_tokens=100,
        completion_tokens=50,
        usd=0.005,
        latency_ms_total=1500,
    )
    with patch("scripts.eval.loop", return_value=canned):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.reason == "no_tool_call_repeat"


def test_run_case_propagates_reason_stuck_repeat():
    canned = RunResult(
        status="failed",
        result=None,
        evidence=None,
        verifier=None,
        reason="stuck_repeat",
        steps=3,
        prompt_tokens=100,
        completion_tokens=50,
        usd=0.005,
        latency_ms_total=1500,
    )
    with patch("scripts.eval.loop", return_value=canned):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.reason == "stuck_repeat"


def test_run_case_succeeded_has_reason_none():
    canned = RunResult(
        status="succeeded",
        result={"title": "x"},
        evidence={"url": "http://x", "text_snippet": "x"},
        verifier={"ok": True, "reasons": []},
        reason=None,
        steps=1,
        prompt_tokens=10,
        completion_tokens=5,
        usd=0.001,
        latency_ms_total=100,
    )
    with patch("scripts.eval.loop", return_value=canned):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.status == "succeeded"
    assert result.reason is None


def test_bench_json_includes_reason_field_on_every_case(tmp_path):
    canned = RunResult(
        status="failed",
        result=None,
        evidence=None,
        verifier=None,
        reason="no_progress",
        steps=4,
        prompt_tokens=100,
        completion_tokens=50,
        usd=0.005,
        latency_ms_total=2000,
    )
    with patch("scripts.eval.loop", return_value=canned):
        out = run_suite(cases=[_FIXTURE_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert len(data["cases"]) == 1
    for case in data["cases"]:
        assert "reason" in case, f"case {case.get('id')} missing 'reason' key"
    assert data["cases"][0]["reason"] == "no_progress"


def test_bench_json_reason_is_null_on_succeeded(tmp_path):
    canned = RunResult(
        status="succeeded",
        result={"title": "Hello"},
        evidence={"url": "http://x", "text_snippet": "Hello"},
        verifier={"ok": True, "reasons": []},
        reason=None,
        steps=1,
        prompt_tokens=10,
        completion_tokens=5,
        usd=0.001,
        latency_ms_total=100,
    )
    with patch("scripts.eval.loop", return_value=canned):
        out = run_suite(cases=[_FIXTURE_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert data["cases"][0]["reason"] is None


def test_skipped_result_has_reason_none():
    from scripts.eval import _skipped_result

    skipped = _skipped_result(_FIXTURE_CASE, "live_disabled")
    assert skipped.status == "skipped"
    assert skipped.reason is None


def test_run_case_exception_path_has_reason_none():
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    with patch("scripts.eval.loop", side_effect=_boom):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.status == "failed"
    assert result.reason is None
