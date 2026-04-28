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
    assert _render_case_status(case) == "0/3 ✗"


def test_stddev_usd_is_zero_for_single_run():
    from scripts.benchmark import aggregate_repeats

    single = _make_case_result("succeeded", usd=0.5)
    with patch("scripts.benchmark._run_case", return_value=single):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=1, llm_client=None, browser=None)

    assert result.stddev_usd == 0.0


def test_aggregated_status_succeeded_for_all_pass():
    from scripts.benchmark import aggregate_repeats

    passing = _make_case_result("succeeded")
    with patch("scripts.benchmark._run_case", return_value=passing):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=2, llm_client=None, browser=None)

    assert result.status == "succeeded"


def test_aggregated_status_failed_for_partial():
    from scripts.benchmark import aggregate_repeats

    side_effects = [_make_case_result("succeeded"), _make_case_result("failed")]
    with patch("scripts.benchmark._run_case", side_effect=side_effects):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=2, llm_client=None, browser=None)

    assert result.repeat_status == "partial"
    assert result.status == "failed"


def test_results_json_with_repeats_contains_aggregation_fields(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from scripts.benchmark import main

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "case.yaml").write_text(
        "id: fixture-repeat-test\n"
        "domain: example.com\n"
        "category: fixture\n"
        "task: do something\n"
        "expect: {}\n"
        "budget: {steps: 5, usd: 1.0, seconds: 30}\n"
        "fixture: true\n"
    )

    monkeypatch.setenv("EVAL_CASES_DIR", str(cases_dir))
    monkeypatch.setenv("GITHUB_HEAD_REF", "test-branch")
    monkeypatch.chdir(tmp_path)

    passing = _make_case_result("succeeded")
    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)

    with (
        patch("scripts.benchmark._run_case", return_value=passing),
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
    ):
        rc = main(["--repeats", "3"])

    assert rc == 0
    import json

    results_path = tmp_path / "benchmark" / "test-branch" / "results.json"
    assert results_path.exists()
    data = json.loads(results_path.read_text())
    case = data["cases"][0]
    for key in (
        "repeats",
        "passed_runs",
        "repeat_status",
        "median_latency_ms",
        "p95_latency_ms",
        "stddev_usd",
        "avg_mechanism_firings",
    ):
        assert key in case, f"Missing key: {key}"
    assert case["repeats"] == 3
    assert case["passed_runs"] == 3
    assert case["repeat_status"] == "all_pass"


def test_results_json_with_repeats_1_has_no_aggregation_fields(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from scripts.benchmark import main

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "case.yaml").write_text(
        "id: fixture-single-test\n"
        "domain: example.com\n"
        "category: fixture\n"
        "task: do something\n"
        "expect: {}\n"
        "budget: {steps: 5, usd: 1.0, seconds: 30}\n"
        "fixture: true\n"
    )

    monkeypatch.setenv("EVAL_CASES_DIR", str(cases_dir))
    monkeypatch.setenv("GITHUB_HEAD_REF", "test-branch")
    monkeypatch.chdir(tmp_path)

    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)

    with (
        patch("scripts.benchmark.run_suite") as mock_run_suite,
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
    ):
        import json

        results_file = tmp_path / "out.json"
        results_file.write_text(
            json.dumps(
                {
                    "run_at": "2026-04-28T00:00:00+00:00",
                    "cases": [
                        {
                            "id": "fixture-single-test",
                            "status": "succeeded",
                            "steps": 1,
                            "usd": 0.001,
                            "l_tier_counts": {},
                            "validators": [],
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "latency_ms_total": 100,
                            "latency_ms_per_step": [100],
                            "step_breakdown": [],
                        }
                    ],
                }
            )
        )
        mock_run_suite.return_value = results_file
        rc = main([])

    assert rc == 0
    data = json.loads((tmp_path / "benchmark" / "test-branch" / "results.json").read_text())
    case = data["cases"][0]
    assert "repeats" not in case
    assert "repeat_status" not in case


def test_generate_scoreboard_renders_fractional_all_pass():
    from scripts.score import generate_scoreboard

    data = {
        "run_at": "2026-01-01T00:00:00",
        "cases": [
            {
                "id": "fixture-a",
                "status": "succeeded",
                "repeats": 3,
                "passed_runs": 3,
                "steps": 1,
                "usd": 0.01,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 100,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
        ],
    }
    out = generate_scoreboard(data)
    assert "3/3 ✓" in out


def test_aggregate_repeats_skips_live_disabled_without_calling_run_case():
    from scripts.benchmark import aggregate_repeats

    live_only_case = {**_SAMPLE_CASE, "id": "live-x", "fixture": False}
    with patch("scripts.benchmark._run_case") as mock_run:
        result = aggregate_repeats(
            live_only_case,
            repeats=3,
            llm_client=None,
            browser=None,
            live=False,
        )

    assert mock_run.call_count == 0
    assert result.repeat_status == "skipped"
    assert result.skip_reason == "live_disabled"
    assert result.repeats == 3
    assert result.passed_runs == 0


def test_aggregate_repeats_skips_fixture_missing_without_calling_run_case(tmp_path):
    from scripts.benchmark import aggregate_repeats

    missing_path = tmp_path / "does_not_exist.html"
    case = {**_SAMPLE_CASE, "id": "fixture-missing-x", "fixture_path": str(missing_path)}
    with patch("scripts.benchmark._run_case") as mock_run:
        result = aggregate_repeats(
            case,
            repeats=3,
            llm_client=None,
            browser=None,
            live=False,
        )

    assert mock_run.call_count == 0
    assert result.repeat_status == "skipped"
    assert result.skip_reason == "fixture_missing"


def test_aggregate_repeats_forwards_cache_to_run_case():
    from scripts.benchmark import aggregate_repeats

    sentinel_cache = object()
    passing = _make_case_result("succeeded")
    with patch("scripts.benchmark._run_case", return_value=passing) as mock_run:
        aggregate_repeats(
            _SAMPLE_CASE,
            repeats=2,
            llm_client="L",
            browser="B",
            cache=sentinel_cache,
        )

    assert mock_run.call_count == 2
    for call in mock_run.call_args_list:
        assert call.kwargs.get("cache") is sentinel_cache


def test_aggregate_repeats_latency_ms_total_is_sum_not_median():
    from scripts.benchmark import aggregate_repeats

    results = [_make_case_result("succeeded", latency_ms_total=lat) for lat in [100, 200, 300]]
    with patch("scripts.benchmark._run_case", side_effect=results):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=3, llm_client=None, browser=None)

    assert result.latency_ms_total == 600
    assert result.median_latency_ms == 200


def test_main_repeats_expands_variants(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from scripts.benchmark import main

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "case.yaml").write_text(
        "id: fixture-variants\n"
        "domain: example.com\n"
        "category: fixture\n"
        "task: do something\n"
        "expect: {}\n"
        "budget: {steps: 5, usd: 1.0, seconds: 30}\n"
        "fixture: true\n"
        "variants: [v1, v2]\n"
    )

    monkeypatch.setenv("EVAL_CASES_DIR", str(cases_dir))
    monkeypatch.setenv("GITHUB_HEAD_REF", "test-branch")
    monkeypatch.chdir(tmp_path)

    passing = _make_case_result("succeeded")
    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)

    with (
        patch("scripts.benchmark._run_case", return_value=passing),
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
    ):
        rc = main(["--repeats", "2"])

    assert rc == 0
    import json

    data = json.loads((tmp_path / "benchmark" / "test-branch" / "results.json").read_text())
    case_ids = sorted(c["id"] for c in data["cases"])
    assert case_ids == ["fixture-variants-v1", "fixture-variants-v2"]
    for case in data["cases"]:
        assert case["repeats"] == 2
        assert case["passed_runs"] == 2


def test_main_repeats_skips_live_disabled_without_running_n_times(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from scripts.benchmark import main

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "case.yaml").write_text(
        "id: live-only-case\n"
        "domain: example.com\n"
        "category: live\n"
        "task: do something\n"
        "expect: {}\n"
        "budget: {steps: 5, usd: 1.0, seconds: 30}\n"
        "fixture: false\n"
    )

    monkeypatch.setenv("EVAL_CASES_DIR", str(cases_dir))
    monkeypatch.setenv("GITHUB_HEAD_REF", "test-branch")
    monkeypatch.chdir(tmp_path)

    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)

    with (
        patch("scripts.benchmark._run_case") as mock_run,
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
    ):
        rc = main(["--repeats", "3"])

    assert rc == 0
    assert mock_run.call_count == 0
    import json

    data = json.loads((tmp_path / "benchmark" / "test-branch" / "results.json").read_text())
    assert data["cases"][0]["repeat_status"] == "skipped"
    assert data["cases"][0]["skip_reason"] == "live_disabled"


def test_generate_scoreboard_renders_fractional_partial():
    from scripts.score import generate_scoreboard

    data = {
        "run_at": "2026-01-01T00:00:00",
        "cases": [
            {
                "id": "fixture-b",
                "status": "failed",
                "repeats": 3,
                "passed_runs": 2,
                "steps": 1,
                "usd": 0.01,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 100,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
        ],
    }
    out = generate_scoreboard(data)
    assert "2/3 ✗" in out
