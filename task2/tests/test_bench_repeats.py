from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_case_result(status: str = "succeeded", **kwargs):
    from scripts.eval import CaseResult

    defaults = dict(
        id="test-case",
        status=status,
        steps=1,
        usd=0.01,
        l_tier_counts={},
        validators=[],
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms_total=100,
        latency_ms_per_step=[100],
        step_breakdown=[],
        escalations=[],
        replans=0,
        cache_events={"hits": 0, "invalidations": 0, "misses": 0},
        failure_class=None,
        failure_detail=None,
        skip_reason=None,
    )
    defaults.update(kwargs)
    return CaseResult(**defaults)


_SAMPLE_CASE = {
    "id": "test-case",
    "domain": "example.com",
    "category": "fixture",
    "task": "do something",
    "expect": {},
    "budget": {"steps": 10, "usd": 1.0, "seconds": 60},
    "fixture": True,
}


def test_aggregate_repeats_all_pass():
    from scripts.benchmark import aggregate_repeats

    passing = _make_case_result("succeeded")
    with patch("scripts.benchmark._run_case", return_value=passing):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=3, llm_client=None, browser=None)

    assert result.passed_runs == 3
    assert result.repeats == 3
    assert result.repeat_status == "all_pass"


def test_aggregate_repeats_partial():
    from scripts.benchmark import aggregate_repeats

    statuses = ["succeeded", "failed", "failed"]
    side_effects = [_make_case_result(s) for s in statuses]
    with patch("scripts.benchmark._run_case", side_effect=side_effects):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=3, llm_client=None, browser=None)

    assert result.passed_runs == 1
    assert result.repeats == 3
    assert result.repeat_status == "partial"


def test_repeats_zero_exits_nonzero(tmp_path, monkeypatch):
    from scripts.benchmark import main

    monkeypatch.setenv("GITHUB_HEAD_REF", "test-branch")
    monkeypatch.chdir(tmp_path)
    rc = main(["--repeats", "0"])
    assert rc != 0


def test_aggregated_case_result_rejects_unknown_status():
    from scripts.benchmark import AggregatedCaseResult

    with pytest.raises(ValueError):
        AggregatedCaseResult(
            id="c1",
            repeat_status="unknown",
            repeats=3,
            passed_runs=0,
            median_latency_ms=0,
            p95_latency_ms=0,
            stddev_usd=0.0,
            avg_mechanism_firings=0.0,
            status="failed",
            steps=0,
            usd=0.0,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms_total=0,
            escalations=[],
            replans=0,
            cache_events={},
            failure_class=None,
            skip_reason=None,
        )


def test_render_case_status_all_pass():
    from scripts.score import _render_case_status

    case = {"repeats": 3, "passed_runs": 3, "status": "succeeded"}
    assert _render_case_status(case) == "3/3 ✓"


def test_render_case_status_partial():
    from scripts.score import _render_case_status

    case = {"repeats": 3, "passed_runs": 2, "status": "failed"}
    assert _render_case_status(case) == "2/3 ✗"


def test_aggregate_repeats_all_fail():
    from scripts.benchmark import aggregate_repeats

    failing = _make_case_result("failed")
    with patch("scripts.benchmark._run_case", return_value=failing):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=3, llm_client=None, browser=None)

    assert result.passed_runs == 0
    assert result.repeat_status == "all_fail"


def test_aggregate_repeats_median_latency():
    from scripts.benchmark import aggregate_repeats

    results = [_make_case_result("succeeded", latency_ms_total=lat) for lat in [100, 200, 300]]
    with patch("scripts.benchmark._run_case", side_effect=results):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=3, llm_client=None, browser=None)

    assert result.median_latency_ms == 200


def test_aggregated_case_result_valid_status():
    from scripts.benchmark import AggregatedCaseResult

    r = AggregatedCaseResult(
        id="c1",
        repeat_status="all_pass",
        repeats=3,
        passed_runs=3,
        median_latency_ms=100,
        p95_latency_ms=100,
        stddev_usd=0.0,
        avg_mechanism_firings=0.0,
        status="succeeded",
        steps=1,
        usd=0.01,
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms_total=100,
        escalations=[],
        replans=0,
        cache_events={},
        failure_class=None,
        skip_reason=None,
    )
    assert r.repeat_status == "all_pass"


def test_render_case_status_single_run_plain():
    from scripts.score import _render_case_status

    case = {"status": "succeeded"}
    assert _render_case_status(case) == "succeeded"


def test_render_case_status_missing_passed_runs_no_error():
    from scripts.score import _render_case_status

    case = {"repeats": 3, "status": "failed"}
    result = _render_case_status(case)
    assert isinstance(result, str)
    assert "3" in result
