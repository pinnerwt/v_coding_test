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


def test_repeats_zero_exits_nonzero(tmp_path, monkeypatch, capsys):
    from scripts.benchmark import main

    monkeypatch.setenv("GITHUB_HEAD_REF", "test-branch")
    monkeypatch.chdir(tmp_path)
    rc = main(["--repeats", "0"])
    captured = capsys.readouterr()
    assert rc != 0
    assert "--repeats" in captured.err


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


def test_render_case_status_skipped_case_does_not_render_as_failure():
    from scripts.score import _render_case_status

    case = {"repeats": 3, "passed_runs": 0, "status": "skipped", "repeat_status": "skipped"}
    assert _render_case_status(case) == "skipped"


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
    import json
    from unittest.mock import MagicMock

    from scripts.benchmark import main
    from scripts.eval import CaseResult

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

    stub_result = CaseResult(
        id="fixture-single-test",
        status="succeeded",
        steps=1,
        usd=0.001,
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

    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)

    with (
        patch("scripts.eval._run_case", return_value=stub_result) as mock_run_case,
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
        patch("scripts.benchmark.aggregate_repeats") as mock_aggregate,
    ):
        rc = main([])

    assert rc == 0
    assert mock_aggregate.call_count == 0
    assert mock_run_case.call_count >= 1
    data = json.loads((tmp_path / "benchmark" / "test-branch" / "results.json").read_text())
    case = data["cases"][0]
    assert case["id"] == "fixture-single-test"
    assert "repeats" not in case
    assert "repeat_status" not in case


def test_results_json_with_repeats_2_does_call_aggregate_repeats(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from scripts.benchmark import AggregatedCaseResult, main

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

    stub_agg = AggregatedCaseResult(
        id="fixture-single-test",
        repeat_status="all_pass",
        repeats=2,
        passed_runs=2,
        median_latency_ms=0,
        p95_latency_ms=0,
        stddev_usd=0.0,
        avg_mechanism_firings=0.0,
        status="succeeded",
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

    with (
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
        patch("scripts.benchmark.aggregate_repeats", return_value=stub_agg) as mock_aggregate,
    ):
        rc = main(["--repeats", "2"])

    assert rc == 0
    assert mock_aggregate.call_count == 1


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


def test_aggregated_case_result_rejects_unknown_derived_status():
    from scripts.benchmark import AggregatedCaseResult

    with pytest.raises(ValueError):
        AggregatedCaseResult(
            id="c1",
            repeat_status="all_pass",
            repeats=3,
            passed_runs=3,
            median_latency_ms=0,
            p95_latency_ms=0,
            stddev_usd=0.0,
            avg_mechanism_firings=0.0,
            status="bogus_status",
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


def test_aggregate_repeats_p95_with_three_runs_uses_max_run():
    from unittest.mock import MagicMock

    from scripts.benchmark import aggregate_repeats

    latencies = [100, 200, 300]
    side_effects = [_make_case_result("succeeded", latency_ms_total=lat) for lat in latencies]
    with patch("scripts.benchmark._run_case", side_effect=side_effects):
        result = aggregate_repeats(
            _SAMPLE_CASE,
            repeats=3,
            llm_client=MagicMock(),
            browser=MagicMock(),
        )

    assert result.p95_latency_ms == 300
    assert result.median_latency_ms == 200


def test_main_repeats_3_calls_run_case_three_times_per_case(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from scripts.benchmark import main
    from scripts.eval import CaseResult

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "case.yaml").write_text(
        "id: fixture-callcount-test\n"
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

    stub_result = CaseResult(
        id="fixture-callcount-test",
        status="succeeded",
        steps=1,
        usd=0.001,
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

    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)

    with (
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
        patch("scripts.benchmark._run_case", return_value=stub_result) as mock_run_case,
    ):
        rc = main(["--repeats", "3"])

    assert mock_run_case.call_count == 3
    assert rc == 0


def test_aggregate_repeats_avg_mechanism_firings_is_mean_of_per_run_total():
    from unittest.mock import MagicMock

    from scripts.benchmark import aggregate_repeats

    side_effects = [
        _make_case_result("succeeded", escalations=[{"tier": "L2"}], replans=0),
        _make_case_result("succeeded", escalations=[{"tier": "L2"}, {"tier": "L3"}], replans=1),
        _make_case_result("succeeded", escalations=[], replans=2),
    ]
    with patch("scripts.benchmark._run_case", side_effect=side_effects):
        result = aggregate_repeats(
            _SAMPLE_CASE,
            repeats=3,
            llm_client=MagicMock(),
            browser=MagicMock(),
        )

    assert result.repeat_status == "all_pass"
    assert result.avg_mechanism_firings == 2.0


def test_main_repeats_shared_cache_forwarded_to_all_variants(tmp_path, monkeypatch):
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
        "shared_cache: true\n"
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
        patch("scripts.benchmark._run_case", return_value=passing) as mock_run_case,
        patch("scripts.benchmark.build_clients", return_value=(MagicMock(), mock_browser)),
    ):
        rc = main(["--repeats", "2"])

    assert rc == 0

    caches = [call.kwargs["cache"] for call in mock_run_case.call_args_list]
    assert len(caches) == 4
    assert caches[0] is not None
    assert all(c is caches[0] for c in caches)


def test_aggregate_repeats_mixed_pass_and_skip_classifies_as_partial():
    from unittest.mock import MagicMock

    from scripts.benchmark import aggregate_repeats

    side_effects = [
        _make_case_result("succeeded"),
        _make_case_result("skipped", skip_reason="live_disabled"),
        _make_case_result("skipped", skip_reason="live_disabled"),
    ]
    with patch("scripts.benchmark._run_case", side_effect=side_effects):
        result = aggregate_repeats(
            _SAMPLE_CASE,
            repeats=3,
            llm_client=MagicMock(),
            browser=MagicMock(),
        )

    assert result.repeat_status == "partial"
    assert result.status == "failed"
    assert result.passed_runs == 1


def test_aggregate_repeats_usd_is_sum_across_runs():
    from scripts.benchmark import aggregate_repeats

    side_effects = [_make_case_result("succeeded", usd=0.01) for _ in range(3)]
    with patch("scripts.benchmark._run_case", side_effect=side_effects):
        result = aggregate_repeats(_SAMPLE_CASE, repeats=3, llm_client=None, browser=None)

    assert result.usd == pytest.approx(0.03)


def test_scoreboard_latency_percentiles_with_repeats():
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
                "latency_ms_total": 300,
                "median_latency_ms": 100,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
            {
                "id": "fixture-b",
                "status": "succeeded",
                "repeats": 3,
                "passed_runs": 3,
                "steps": 1,
                "usd": 0.01,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 600,
                "median_latency_ms": 200,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
            {
                "id": "fixture-c",
                "status": "succeeded",
                "repeats": 3,
                "passed_runs": 3,
                "steps": 1,
                "usd": 0.01,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 2400,
                "median_latency_ms": 800,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
        ],
    }
    out = generate_scoreboard(data)
    assert "p50: 200ms" in out
    assert "p95: 800ms" in out


def test_generate_scoreboard_total_usd_under_repeats():
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
                "usd": 0.03,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 300,
                "median_latency_ms": 100,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
            {
                "id": "fixture-b",
                "status": "succeeded",
                "repeats": 3,
                "passed_runs": 3,
                "steps": 1,
                "usd": 0.03,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 300,
                "median_latency_ms": 100,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
        ],
    }
    out = generate_scoreboard(data)
    assert "Total USD: $0.0600" in out


def test_generate_scoreboard_latency_percentiles_fallback():
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
            {
                "id": "fixture-b",
                "status": "succeeded",
                "repeats": 3,
                "passed_runs": 3,
                "steps": 1,
                "usd": 0.01,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 200,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
            {
                "id": "fixture-c",
                "status": "succeeded",
                "repeats": 3,
                "passed_runs": 3,
                "steps": 1,
                "usd": 0.01,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "latency_ms_total": 800,
                "escalations": [],
                "replans": 0,
                "cache_events": {"invalidations": 0},
            },
        ],
    }
    out = generate_scoreboard(data)
    assert "p50: 200ms" in out
    assert "p95: 800ms" in out
