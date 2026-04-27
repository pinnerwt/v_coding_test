from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agent.loop import RunResult
from agent.trace import (
    LocateEvent,
    PlanEvent,
    SupervisorEvent,
    TraceWriter,
)
from scripts.eval import (
    CaseResult,
    _aggregate_diagnostics,
    _run_case,
    load_cases,
    run_suite,
    run_validators,
)

_FIXTURE_CASE = {
    "id": "fixture-heading",
    "domain": "fixture",
    "category": "read-and-summarize",
    "task": "Read the page heading and return it as title",
    "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}

_CANNED_RESULT = RunResult(
    status="succeeded",
    result={"title": "Hello"},
    evidence={"url": "http://x", "text_snippet": "Hello"},
    verifier={"ok": True, "reasons": []},
)

_FIXTURE_CASE_2 = {
    "id": "fixture-count",
    "domain": "fixture",
    "category": "search-and-extract",
    "task": "Return items",
    "expect": {"schema": {"items": "list[str]"}, "validators": ["items.len_gte: 1"]},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}

_CANNED_RESULT_2 = RunResult(
    status="succeeded",
    result={"items": ["a"]},
    evidence={"url": "http://x", "text_snippet": "a"},
    verifier={"ok": True, "reasons": []},
)


def test_run_case_captures_exception_as_failed(tmp_path):
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    with patch("scripts.eval.loop", side_effect=_boom):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.status == "failed"
    assert result.id == "fixture-heading"


def test_results_json_shape(tmp_path):
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[_FIXTURE_CASE], results_dir=tmp_path)
    assert out.exists()
    data = json.loads(out.read_text())
    assert "run_at" in data
    assert "cases" in data
    assert len(data["cases"]) == 1
    case = data["cases"][0]
    for key in ("id", "status", "steps", "usd", "l_tier_counts", "validators"):
        assert key in case, f"missing key: {key}"


def test_results_json_l_tier_counts_is_dict(tmp_path):
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[_FIXTURE_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert isinstance(data["cases"][0]["l_tier_counts"], dict)


def test_results_json_validators_list(tmp_path):
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[_FIXTURE_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    validators = data["cases"][0]["validators"]
    assert isinstance(validators, list)
    assert len(validators) == 1
    assert validators[0] == {"name": "title.nonempty", "ok": True}


def test_skipped_case_has_correct_shape(tmp_path):
    live_case = {**_FIXTURE_CASE, "fixture": False}
    out = run_suite(cases=[live_case], results_dir=tmp_path, live=False)
    data = json.loads(out.read_text())
    case = data["cases"][0]
    assert case["status"] == "skipped"
    assert case["steps"] == 0
    assert case["usd"] == 0.0
    assert case["l_tier_counts"] == {}
    assert case["validators"] == []


def test_load_cases_valid_yaml(tmp_path):
    p = tmp_path / "case.yaml"
    p.write_text(
        yaml.dump(
            [
                {
                    "id": "test-case",
                    "domain": "example.com",
                    "category": "search-and-extract",
                    "task": "Find something",
                    "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
                    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
                }
            ]
        )
    )
    cases = load_cases(p)
    assert len(cases) == 1
    c = cases[0]
    for field in ("id", "domain", "category", "task", "expect", "budget"):
        assert field in c, f"missing field: {field}"


def test_load_cases_missing_required_field_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        yaml.dump(
            [
                {
                    "id": "test-case",
                    "domain": "example.com",
                    "category": "search-and-extract",
                    "expect": {"schema": {}, "validators": []},
                    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="task"):
        load_cases(p)


def test_fixture_heading_yaml_loads():
    cases = load_cases("eval/cases/fixture-heading.yaml")
    assert len(cases) == 1
    assert cases[0]["id"] == "fixture-heading"
    assert cases[0]["fixture"] is True


def test_fixture_count_yaml_loads():
    cases = load_cases("eval/cases/fixture-count.yaml")
    assert len(cases) == 1
    assert cases[0]["id"] == "fixture-count"
    assert cases[0]["fixture"] is True


def test_validator_nonempty_passes():
    assert run_validators(["title.nonempty"], {"title": "Hello"}) == [
        {"name": "title.nonempty", "ok": True}
    ]


def test_validator_nonempty_fails_empty_string():
    result = run_validators(["title.nonempty"], {"title": ""})
    assert result[0]["ok"] is False


def test_validator_nonempty_fails_missing_key():
    result = run_validators(["title.nonempty"], {})
    assert result[0]["ok"] is False


def test_validator_len_gte_passes():
    result = run_validators(["items.len_gte: 1"], {"items": ["a", "b"]})
    assert result[0]["ok"] is True


def test_validator_len_gte_fails_empty_list():
    result = run_validators(["items.len_gte: 1"], {"items": []})
    assert result[0]["ok"] is False


def test_validator_len_gte_fails_missing_key():
    result = run_validators(["items.len_gte: 1"], {})
    assert result[0]["ok"] is False


def test_run_suite_two_fixture_cases_both_included(tmp_path):
    with patch("scripts.eval.loop", side_effect=[_CANNED_RESULT, _CANNED_RESULT_2]):
        out = run_suite(cases=[_FIXTURE_CASE, _FIXTURE_CASE_2], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert len(data["cases"]) == 2


def test_compute_exit_code_all_pass():
    from scripts.eval import compute_exit_code

    cases = [{"status": "succeeded"}, {"status": "unverified"}, {"status": "skipped"}]
    assert compute_exit_code(cases) == 0


def test_compute_exit_code_one_failed():
    from scripts.eval import compute_exit_code

    cases = [{"status": "succeeded"}, {"status": "failed"}]
    assert compute_exit_code(cases) == 1


def test_compute_exit_code_blocked():
    from scripts.eval import compute_exit_code

    cases = [{"status": "blocked"}]
    assert compute_exit_code(cases) == 1


def test_compute_exit_code_timeout():
    from scripts.eval import compute_exit_code

    cases = [{"status": "timeout"}]
    assert compute_exit_code(cases) == 1


def test_build_clients_uses_llm_base_url_env(monkeypatch):
    from scripts.eval import build_clients

    monkeypatch.setenv("LLM_BASE_URL", "http://custom:9999/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    with (
        patch("scripts.eval.LLMClient") as mock_llm,
        patch("scripts.eval.Browser") as mock_browser,
    ):
        mock_llm.return_value = MagicMock()
        mock_browser.return_value = MagicMock()
        build_clients()
        mock_llm.assert_called_once_with(
            base_url="http://custom:9999/v1",
            model="test-model",
            api_key="test-key",
        )


def test_main_opens_browser_as_context_manager(monkeypatch, tmp_path):
    from scripts.eval import main

    (tmp_path / "eval" / "cases").mkdir(parents=True)
    (tmp_path / "eval" / "results").mkdir(parents=True)
    case_yaml = tmp_path / "eval" / "cases" / "fixture-heading.yaml"
    case_yaml.write_text(yaml.dump([_FIXTURE_CASE]))
    monkeypatch.chdir(tmp_path)

    mock_browser = MagicMock()
    mock_browser.return_value.__enter__.return_value = mock_browser.return_value

    with (
        patch("scripts.eval.LLMClient", MagicMock()),
        patch("scripts.eval.Browser", mock_browser),
        patch("scripts.eval.loop", return_value=_CANNED_RESULT),
    ):
        main([])

    mock_browser.return_value.__enter__.assert_called_once()
    mock_browser.return_value.__exit__.assert_called_once()


def test_run_suite_prints_per_case_progress_inline(tmp_path, capsys):
    stdout_at_call: list[str] = []

    def side_effect_fn(*args, **kwargs):
        stdout_at_call.append(capsys.readouterr().out)
        return _CANNED_RESULT if len(stdout_at_call) == 1 else _CANNED_RESULT_2

    with patch("scripts.eval.loop", side_effect=side_effect_fn):
        run_suite(cases=[_FIXTURE_CASE, _FIXTURE_CASE_2], results_dir=tmp_path)

    assert "[PASS] fixture-heading" in stdout_at_call[1]


def test_results_filename_matches_spec_format(tmp_path):
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[_FIXTURE_CASE], results_dir=tmp_path)
    assert re.fullmatch(r"\d{8}_\d{6}\.json", out.name) is not None


_DRIFT_CASE = {
    "id": "drift-submit-form",
    "domain": "fixture",
    "category": "drift",
    "task": "Click the submit button and return submitted as status",
    "expect": {"schema": {"status": "str"}, "validators": ["status.nonempty"]},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
    "variants": ["v1", "v2"],
}

_DRIFT_CANNED_RESULT = RunResult(
    status="succeeded",
    result={"status": "submitted"},
    evidence={"url": "http://x", "text_snippet": "submitted"},
    verifier={"ok": True, "reasons": []},
)


def test_drift_case_yaml_loads():
    cases = load_cases("eval/cases/drift-submit-form.yaml")
    assert cases[0]["id"] == "drift-submit-form"
    assert cases[0]["variants"] == ["v1", "v2"]
    assert cases[0]["fixture"] is True


def test_variant_expansion_produces_two_results(tmp_path):
    with patch("scripts.eval.loop", side_effect=[_DRIFT_CANNED_RESULT, _DRIFT_CANNED_RESULT]):
        out = run_suite(cases=[_DRIFT_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert len(data["cases"]) == 2
    assert data["cases"][0]["id"] == "drift-submit-form-v1"
    assert data["cases"][1]["id"] == "drift-submit-form-v2"


def test_variant_expansion_mixed_suite(tmp_path):
    non_variant_case = {**_FIXTURE_CASE}
    with patch(
        "scripts.eval.loop",
        side_effect=[_CANNED_RESULT, _DRIFT_CANNED_RESULT, _DRIFT_CANNED_RESULT],
    ):
        out = run_suite(cases=[non_variant_case, _DRIFT_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert len(data["cases"]) == 3


def test_empty_variants_list_runs_as_single_case(tmp_path):
    case_with_empty_variants = {**_FIXTURE_CASE, "variants": []}
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[case_with_empty_variants], results_dir=tmp_path)
    data = json.loads(out.read_text())
    assert len(data["cases"]) == 1
    assert data["cases"][0]["id"] == _FIXTURE_CASE["id"]


# ---------------------------------------------------------------------------
# CaseResult quantitative fields (eval-metrics spec)
# ---------------------------------------------------------------------------

_METRICS_RUN_RESULT = RunResult(
    status="succeeded",
    result={},
    evidence={"url": "u", "text_snippet": "t"},
    verifier={"ok": True, "reasons": []},
    steps=3,
    prompt_tokens=400,
    completion_tokens=60,
    usd=0.0009,
    latency_ms_total=1200,
    latency_ms_per_step=[400, 400, 400],
    step_breakdown=[
        {
            "step": 1,
            "latency_ms": 400,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "usd": 0.0003,
            "tool_calls": ["goto"],
        },
        {
            "step": 2,
            "latency_ms": 400,
            "prompt_tokens": 150,
            "completion_tokens": 20,
            "usd": 0.0003,
            "tool_calls": ["read"],
        },
        {
            "step": 3,
            "latency_ms": 400,
            "prompt_tokens": 150,
            "completion_tokens": 20,
            "usd": 0.0003,
            "tool_calls": ["done"],
        },
    ],
)


def test_run_case_populates_metrics_from_run_result():
    with patch("scripts.eval.loop", return_value=_METRICS_RUN_RESULT):
        result = _run_case(_FIXTURE_CASE, llm_client=None, browser=None)
    assert result.steps == 3
    assert result.usd == 0.0009
    assert result.prompt_tokens == 400
    assert result.completion_tokens == 60
    assert result.latency_ms_total == 1200
    assert result.latency_ms_per_step == [400, 400, 400]
    assert len(result.step_breakdown) == 3


def test_case_result_default_has_zero_quantitative_fields():
    cr = CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])
    assert cr.prompt_tokens == 0
    assert cr.completion_tokens == 0
    assert cr.latency_ms_total == 0
    assert cr.latency_ms_per_step == []
    assert cr.step_breakdown == []


def test_case_result_serialises_with_quantitative_fields():
    cr = CaseResult(
        id="x",
        status="succeeded",
        steps=2,
        usd=0.0005,
        l_tier_counts={},
        validators=[],
        prompt_tokens=100,
        completion_tokens=30,
        latency_ms_total=500,
        latency_ms_per_step=[200, 300],
        step_breakdown=[
            {
                "step": 1,
                "latency_ms": 200,
                "prompt_tokens": 50,
                "completion_tokens": 15,
                "usd": 0.00025,
                "tool_calls": ["goto"],
            },
        ],
    )
    serialized = json.dumps(asdict(cr))
    data = json.loads(serialized)
    assert data["prompt_tokens"] == 100
    assert data["latency_ms_per_step"] == [200, 300]


# ---------------------------------------------------------------------------
# Task 1.1: CaseResult diagnostic fields — default values (RED until 4.1)
# ---------------------------------------------------------------------------


def test_case_result_default_diagnostic_fields():
    cr = CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])
    assert cr.escalations == []
    assert cr.replans == 0
    assert cr.cache_events == {}


# ---------------------------------------------------------------------------
# Task 1.2: _aggregate_diagnostics escalation from SupervisorEvent (RED until 4.2)
# ---------------------------------------------------------------------------


def _make_run_id() -> str:
    return str(uuid.uuid4())


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _writer_with_run(run_id: str) -> TraceWriter:
    from agent.trace import Run, RunBudget, RunLLM

    writer = TraceWriter(path=":memory:")
    run = Run(
        run_id=run_id,
        task="test",
        expect_schema=None,
        budget=RunBudget(steps=5, usd=0.1, seconds=30),
        llm=RunLLM(base_url="http://x", model="m", temperature=0.0, seed=None),
        agent_version="test",
        started_at=_ts(),
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    writer.open_run(run)
    return writer


def test_aggregate_diagnostics_escalation_from_supervisor_event():
    run_id = _make_run_id()
    writer = _writer_with_run(run_id)

    locate_miss = LocateEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        intent="Submit button",
        tier="L1_ax",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=10,
    )
    writer.append_event(locate_miss)

    supervisor_ev = SupervisorEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        trigger_event_seq=locate_miss.seq,
        classified_as="LocatorMiss",
        policy="next_tier",
        attempt=1,
    )
    writer.append_event(supervisor_ev)

    locate_hit = LocateEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        intent="Submit button",
        tier="L2_dom",
        outcome="hit",
        candidates=[],
        chosen={"selector": ".btn"},
        cache_action="write",
        ms=15,
    )
    writer.append_event(locate_hit)

    escalations, replans, cache_events = _aggregate_diagnostics(writer, run_id)
    assert len(escalations) == 1
    assert escalations[0]["from_tier"] == "L1_ax"
    assert escalations[0]["to_tier"] == "L2_dom"


# ---------------------------------------------------------------------------
# Task 1.3: _aggregate_diagnostics counts PlanEvent(reason="replan") (RED until 4.2)
# ---------------------------------------------------------------------------


def test_aggregate_diagnostics_counts_replan():
    run_id = _make_run_id()
    writer = _writer_with_run(run_id)

    plan_initial = PlanEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id=None,
        reason="initial",
        steps=["step 1"],
        llm_call_id="c1",
    )
    writer.append_event(plan_initial)

    plan_replan = PlanEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id=None,
        reason="replan",
        steps=["step 2"],
        llm_call_id="c2",
    )
    writer.append_event(plan_replan)

    _, replans, _ = _aggregate_diagnostics(writer, run_id)
    assert replans == 1


# ---------------------------------------------------------------------------
# Task 1.4: _aggregate_diagnostics cache events from LocateEvent (RED until 4.2)
# ---------------------------------------------------------------------------


def test_aggregate_diagnostics_cache_events():
    run_id = _make_run_id()
    writer = _writer_with_run(run_id)

    cache_hit = LocateEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        intent="Submit",
        tier="L1_ax",
        outcome="hit",
        candidates=[],
        chosen={"selector": ".btn"},
        cache_action="read",
        ms=5,
    )
    writer.append_event(cache_hit)

    cache_invalidate = LocateEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        intent="Submit",
        tier="L1_ax",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action="invalidate",
        ms=5,
    )
    writer.append_event(cache_invalidate)

    cache_miss = LocateEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        intent="Submit",
        tier="L1_ax",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=5,
    )
    writer.append_event(cache_miss)

    _, _, cache_events = _aggregate_diagnostics(writer, run_id)
    assert cache_events["hits"] == 1
    assert cache_events["invalidations"] == 1
    assert cache_events["misses"] == 1


# ---------------------------------------------------------------------------
# Task 2.1: correction-l1-miss-l2-hit eval case assertion (RED until 5+6 green)
# ---------------------------------------------------------------------------

_L1_MISS_L2_HIT_CASE = {
    "id": "correction-l1-miss-l2-hit",
    "domain": "fixture",
    "category": "correction",
    "task": "Click the Submit button",
    "expect": {"schema": {}, "validators": []},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}


def _mock_loop_emit_escalation(task, browser, llm_client, **kwargs):
    writer = kwargs.get("trace_writer")
    rid = kwargs.get("run_id")
    if writer is not None and rid is not None:
        locate_miss = LocateEvent(
            run_id=rid,
            seq=writer.next_seq(rid),
            ts=_ts(),
            step_id="s1",
            intent="Submit button",
            tier="L1_ax",
            outcome="miss",
            candidates=[],
            chosen=None,
            cache_action=None,
            ms=10,
        )
        writer.append_event(locate_miss)
        sup_ev = SupervisorEvent(
            run_id=rid,
            seq=writer.next_seq(rid),
            ts=_ts(),
            step_id="s1",
            trigger_event_seq=locate_miss.seq,
            classified_as="LocatorMiss",
            policy="next_tier",
            attempt=1,
        )
        writer.append_event(sup_ev)
        locate_hit = LocateEvent(
            run_id=rid,
            seq=writer.next_seq(rid),
            ts=_ts(),
            step_id="s1",
            intent="Submit button",
            tier="L2_dom",
            outcome="hit",
            candidates=[],
            chosen={"selector": ".btn"},
            cache_action="write",
            ms=15,
        )
        writer.append_event(locate_hit)
    return RunResult(
        status="succeeded",
        result={},
        evidence={"url": "http://x", "text_snippet": "ok"},
        verifier={"ok": True, "reasons": []},
    )


def test_run_case_escalations_for_l1_miss_l2_hit(tmp_path):
    with patch("scripts.eval.loop", side_effect=_mock_loop_emit_escalation):
        result = _run_case(_L1_MISS_L2_HIT_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert len(result.escalations) == 1
    assert result.escalations[0]["from_tier"] == "L1_ax"
    assert result.escalations[0]["to_tier"] == "L2_dom"


# ---------------------------------------------------------------------------
# Task 2.2: correction-replan eval case assertion (RED until 5+6 green)
# ---------------------------------------------------------------------------

_REPLAN_CASE = {
    "id": "correction-replan",
    "domain": "fixture",
    "category": "correction",
    "task": "Read the heading on this page",
    "expect": {"schema": {}, "validators": []},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}


def _mock_loop_emit_replan(task, browser, llm_client, **kwargs):
    writer = kwargs.get("trace_writer")
    rid = kwargs.get("run_id")
    if writer is not None and rid is not None:
        plan_replan = PlanEvent(
            run_id=rid,
            seq=writer.next_seq(rid),
            ts=_ts(),
            step_id=None,
            reason="replan",
            steps=["call done"],
            llm_call_id="c1",
        )
        writer.append_event(plan_replan)
    return RunResult(
        status="succeeded",
        result={},
        evidence={"url": "http://x", "text_snippet": "ok"},
        verifier={"ok": True, "reasons": []},
    )


def test_run_case_replans_for_replan_case(tmp_path):
    with patch("scripts.eval.loop", side_effect=_mock_loop_emit_replan):
        result = _run_case(_REPLAN_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.replans == 1
    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Task 2.3: maintenance-drift-rename v2 cache invalidation (RED until 5+6 green)
# ---------------------------------------------------------------------------

_DRIFT_RENAME_CASE = {
    "id": "maintenance-drift-rename",
    "domain": "fixture",
    "category": "drift",
    "task": "Click the Submit button",
    "expect": {"schema": {}, "validators": []},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
    "variants": ["v1", "v2"],
    "shared_cache": True,
}

_DRIFT_RENAME_CANNED_V1 = RunResult(
    status="succeeded",
    result={},
    evidence={"url": "http://x", "text_snippet": "ok"},
    verifier={"ok": True, "reasons": []},
)


def _mock_loop_emit_cache_invalidation(task, browser, llm_client, **kwargs):
    writer = kwargs.get("trace_writer")
    rid = kwargs.get("run_id")
    if writer is not None and rid is not None:
        invalidate_ev = LocateEvent(
            run_id=rid,
            seq=writer.next_seq(rid),
            ts=_ts(),
            step_id="s1",
            intent="Submit button",
            tier="L1_ax",
            outcome="miss",
            candidates=[],
            chosen=None,
            cache_action="invalidate",
            ms=5,
        )
        writer.append_event(invalidate_ev)
    return RunResult(
        status="succeeded",
        result={},
        evidence={"url": "http://x", "text_snippet": "ok"},
        verifier={"ok": True, "reasons": []},
    )


def test_run_suite_shared_cache_v2_invalidation(tmp_path):
    call_count = {"n": 0}

    def mock_loop(task, browser, llm_client, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            return _mock_loop_emit_cache_invalidation(task, browser, llm_client, **kwargs)
        return _DRIFT_RENAME_CANNED_V1

    with patch("scripts.eval.loop", side_effect=mock_loop):
        out = run_suite(cases=[_DRIFT_RENAME_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    v2_case = next(c for c in data["cases"] if c["id"] == "maintenance-drift-rename-v2")
    assert v2_case["cache_events"].get("invalidations", 0) >= 1
    assert v2_case["status"] == "succeeded"


def test_run_suite_shared_cache_same_instance_passed_to_variants(tmp_path):
    import scripts.eval as eval_mod

    received_caches: list = []
    original_run_case = eval_mod._run_case

    def capture_run_case(case, llm_client, browser, cache=None):
        received_caches.append(cache)
        return original_run_case(case, llm_client, browser, cache=cache)

    with (
        patch("scripts.eval.loop", return_value=_DRIFT_RENAME_CANNED_V1),
        patch("scripts.eval._run_case", side_effect=capture_run_case),
    ):
        run_suite(cases=[_DRIFT_RENAME_CASE], results_dir=tmp_path)

    assert len(received_caches) == 2
    assert received_caches[0] is not None
    assert received_caches[0] is received_caches[1]


def test_run_suite_no_shared_cache_when_absent(tmp_path):
    case_no_shared_cache = {**_DRIFT_RENAME_CASE}
    case_no_shared_cache.pop("shared_cache", None)

    import scripts.eval as eval_mod

    received_caches: list = []
    original_run_case = eval_mod._run_case

    def capture_run_case(case, llm_client, browser, cache=None):
        received_caches.append(cache)
        return original_run_case(case, llm_client, browser, cache=cache)

    with (
        patch("scripts.eval.loop", return_value=_DRIFT_RENAME_CANNED_V1),
        patch("scripts.eval._run_case", side_effect=capture_run_case),
    ):
        run_suite(cases=[case_no_shared_cache], results_dir=tmp_path)

    assert all(c is None for c in received_caches)


def test_maintenance_drift_rename_yaml_loads():
    cases = load_cases("eval/cases/maintenance-drift-rename.yaml")
    assert len(cases) == 1
    c = cases[0]
    assert c["fixture"] is True
    assert c["category"] == "drift"
    assert c["variants"] == ["v1", "v2"]
    assert c["shared_cache"] is True


def test_correction_l1_miss_l2_hit_yaml_loads():
    cases = load_cases("eval/cases/correction-l1-miss-l2-hit.yaml")
    assert len(cases) == 1
    c = cases[0]
    assert c["fixture"] is True
    assert c["category"] == "correction"
    assert c["budget"]["steps"] >= 3


def test_correction_replan_yaml_loads():
    cases = load_cases("eval/cases/correction-replan.yaml")
    assert len(cases) == 1
    c = cases[0]
    assert c["fixture"] is True
    assert c["category"] == "correction"
