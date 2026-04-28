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
    Run,
    RunBudget,
    RunLLM,
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


def test_run_case_navigates_to_fixture_url_before_loop():
    case = {**_FIXTURE_CASE, "fixture_url": "data:text/html,<h1>Hi</h1>"}
    browser = MagicMock()
    goto_called_before_loop = False

    def _loop_spy(*args, **kwargs):
        nonlocal goto_called_before_loop
        goto_called_before_loop = browser.goto.called
        return _CANNED_RESULT

    with patch("scripts.eval.loop", side_effect=_loop_spy):
        _run_case(case, llm_client=MagicMock(), browser=browser)
    browser.goto.assert_called_once_with("data:text/html,<h1>Hi</h1>")
    assert goto_called_before_loop


def test_run_case_skips_navigation_when_no_fixture_url():
    browser = MagicMock()
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=browser)
    browser.goto.assert_not_called()


def test_run_case_captures_exception_as_failed(tmp_path):
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    with patch("scripts.eval.loop", side_effect=_boom):
        result = _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.status == "failed"
    assert result.id == "fixture-heading"


def test_run_case_captures_goto_exception_as_failed():
    browser = MagicMock()
    browser.goto.side_effect = RuntimeError("nav fail")
    case = {**_FIXTURE_CASE, "fixture_url": "data:text/html,<h1>x</h1>"}
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        result = _run_case(case, llm_client=MagicMock(), browser=browser)
    assert result.status == "failed"
    assert result.failure_class == "tool_error"
    assert "nav fail" in result.failure_detail


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


def test_fixture_heading_yaml_is_canary():
    cases = load_cases("eval/cases/fixture-heading.yaml")
    assert cases[0]["canary"] is True


def test_fixture_count_yaml_loads():
    cases = load_cases("eval/cases/fixture-count.yaml")
    assert len(cases) == 1
    assert cases[0]["id"] == "fixture-count"
    assert cases[0]["fixture"] is True


def test_fixture_count_yaml_is_canary():
    cases = load_cases("eval/cases/fixture-count.yaml")
    assert cases[0]["canary"] is True


def test_canary_read_h1_yaml_loads_as_fixture_canary():
    cases = load_cases("eval/cases/canary-read-h1.yaml")
    assert len(cases) == 1
    c = cases[0]
    assert c["id"] == "canary-read-h1"
    assert c["canary"] is True
    assert c["fixture"] is True
    assert c["budget"]["steps"] == 5
    assert c["fixture_url"].startswith("data:text/html,")


def test_load_cases_accepts_canary_field(tmp_path):
    p = tmp_path / "case.yaml"
    p.write_text(
        yaml.dump(
            [
                {
                    "id": "canary-case",
                    "domain": "fixture",
                    "category": "read-and-summarize",
                    "task": "Read the H1",
                    "canary": True,
                    "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
                    "budget": {"steps": 1, "usd": 0.02, "seconds": 15},
                }
            ]
        )
    )
    cases = load_cases(p)
    assert len(cases) == 1
    assert cases[0]["canary"] is True


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
    assert result.failure_class is None


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


def test_case_result_default_diagnostic_fields():
    cr = CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])
    assert cr.escalations == []
    assert cr.replans == 0
    assert cr.cache_events == {}


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

    _, escalations, replans, cache_events = _aggregate_diagnostics(writer, run_id)
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

    _, _, replans, _ = _aggregate_diagnostics(writer, run_id)
    assert replans == 1


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

    _, _, _, cache_events = _aggregate_diagnostics(writer, run_id)
    assert cache_events["hits"] == 1
    assert cache_events["invalidations"] == 1
    assert cache_events["misses"] == 1


def test_aggregate_diagnostics_empty_trace_returns_zero_values():
    run_id = _make_run_id()
    writer = _writer_with_run(run_id)

    _, escalations, replans, cache_events = _aggregate_diagnostics(writer, run_id)
    assert escalations == []
    assert replans == 0
    assert cache_events == {"hits": 0, "invalidations": 0, "misses": 0}


def test_aggregate_diagnostics_does_not_import_any_event_adapter():
    import ast
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "scripts" / "eval.py"
    src_text = src.read_text()
    tree = ast.parse(src_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "agent.trace":
            names = [alias.name for alias in node.names]
            assert "_any_event_adapter" not in names, (
                "eval.py must not import _any_event_adapter from agent.trace"
            )
    assert "_any_event_adapter" not in src_text, (
        "eval.py must not reference _any_event_adapter in any form"
        " (import, attribute access, comment, etc.)"
    )


_CANNED_SUCCESS = RunResult(
    status="succeeded",
    result={},
    evidence={"url": "http://x", "text_snippet": "ok"},
    verifier={"ok": True, "reasons": []},
)


def _emit_events(kwargs: dict, build_events) -> RunResult:
    writer = kwargs.get("trace_writer")
    rid = kwargs.get("run_id")
    if writer is not None and rid is not None:
        for ev in build_events(writer, rid):
            writer.append_event(ev)
    return _CANNED_SUCCESS


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
    def build(writer, rid):
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
        sup_ev = SupervisorEvent(
            run_id=rid,
            seq=locate_miss.seq + 1,
            ts=_ts(),
            step_id="s1",
            trigger_event_seq=locate_miss.seq,
            classified_as="LocatorMiss",
            policy="next_tier",
            attempt=1,
        )
        locate_hit = LocateEvent(
            run_id=rid,
            seq=sup_ev.seq + 1,
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
        return [locate_miss, sup_ev, locate_hit]

    return _emit_events(kwargs, build)


def test_run_case_escalations_for_l1_miss_l2_hit(tmp_path):
    with patch("scripts.eval.loop", side_effect=_mock_loop_emit_escalation):
        result = _run_case(_L1_MISS_L2_HIT_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert len(result.escalations) == 1
    assert result.escalations[0]["from_tier"] == "L1_ax"
    assert result.escalations[0]["to_tier"] == "L2_dom"


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
    def build(writer, rid):
        return [
            PlanEvent(
                run_id=rid,
                seq=writer.next_seq(rid),
                ts=_ts(),
                step_id=None,
                reason="replan",
                steps=["call done"],
                llm_call_id="c1",
            )
        ]

    return _emit_events(kwargs, build)


def test_run_case_replans_for_replan_case(tmp_path):
    with patch("scripts.eval.loop", side_effect=_mock_loop_emit_replan):
        result = _run_case(_REPLAN_CASE, llm_client=MagicMock(), browser=MagicMock())
    assert result.replans == 1
    assert result.status == "succeeded"


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


def _mock_loop_emit_cache_invalidation(task, browser, llm_client, **kwargs):
    def build(writer, rid):
        return [
            LocateEvent(
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
        ]

    return _emit_events(kwargs, build)


def test_run_suite_shared_cache_v2_invalidation(tmp_path):
    call_count = {"n": 0}

    def mock_loop(task, browser, llm_client, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            return _mock_loop_emit_cache_invalidation(task, browser, llm_client, **kwargs)
        return _CANNED_SUCCESS

    with patch("scripts.eval.loop", side_effect=mock_loop):
        out = run_suite(cases=[_DRIFT_RENAME_CASE], results_dir=tmp_path)
    data = json.loads(out.read_text())
    v2_case = next(c for c in data["cases"] if c["id"] == "maintenance-drift-rename-v2")
    assert v2_case["cache_events"].get("invalidations", 0) >= 1
    assert v2_case["status"] == "succeeded"


def _capture_run_case_caches():
    import scripts.eval as eval_mod

    received: list = []
    original = eval_mod._run_case

    def capture(case, llm_client, browser, cache=None, canary=False):
        received.append(cache)
        return original(case, llm_client, browser, cache=cache, canary=canary)

    return received, capture


def test_run_suite_shared_cache_same_instance_passed_to_variants(tmp_path):
    received_caches, capture = _capture_run_case_caches()
    with (
        patch("scripts.eval.loop", return_value=_CANNED_SUCCESS),
        patch("scripts.eval._run_case", side_effect=capture),
    ):
        run_suite(cases=[_DRIFT_RENAME_CASE], results_dir=tmp_path)

    assert len(received_caches) == 2
    assert received_caches[0] is not None
    assert received_caches[0] is received_caches[1]


def test_run_suite_no_shared_cache_when_absent(tmp_path):
    case_no_shared_cache = {**_DRIFT_RENAME_CASE}
    case_no_shared_cache.pop("shared_cache", None)

    received_caches, capture = _capture_run_case_caches()
    with (
        patch("scripts.eval.loop", return_value=_CANNED_SUCCESS),
        patch("scripts.eval._run_case", side_effect=capture),
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


def test_aggregate_diagnostics_escalation_to_tier_scoped_to_step_id():
    run_id = _make_run_id()
    writer = _writer_with_run(run_id)

    locate_miss_s1 = LocateEvent(
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
    writer.append_event(locate_miss_s1)

    sup_s1 = SupervisorEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s1",
        trigger_event_seq=locate_miss_s1.seq,
        classified_as="LocatorMiss",
        policy="next_tier",
        attempt=1,
    )
    writer.append_event(sup_s1)

    locate_hit_s2 = LocateEvent(
        run_id=run_id,
        seq=writer.next_seq(run_id),
        ts=_ts(),
        step_id="s2",
        intent="Cancel link",
        tier="L4_vision",
        outcome="hit",
        candidates=[],
        chosen={"selector": "a"},
        cache_action="write",
        ms=20,
    )
    writer.append_event(locate_hit_s2)

    _, escalations, _, _ = _aggregate_diagnostics(writer, run_id)
    assert len(escalations) == 1
    assert escalations[0]["from_tier"] == "L1_ax"
    assert escalations[0]["to_tier"] is None


# ---------------------------------------------------------------------------
# locator_cache forwarding tests
# ---------------------------------------------------------------------------


def test_run_case_forwards_cache_to_loop():
    """_run_case must pass its cache argument as locator_cache= to loop()."""
    from agent.locator_cache import LocatorCache

    captured: list[dict] = []

    def _side_effect(task, browser, llm_client, **kwargs):
        captured.append(kwargs)
        return _CANNED_RESULT

    mock_cache = MagicMock(spec=LocatorCache)

    with patch("scripts.eval.loop", side_effect=_side_effect):
        _run_case(_FIXTURE_CASE, llm_client=MagicMock(), browser=MagicMock(), cache=mock_cache)

    assert len(captured) == 1
    assert captured[0].get("locator_cache") is mock_cache, (
        f"loop() was not called with locator_cache=<mock_cache>; got kwargs: {captured[0]}"
    )


def test_maintenance_drift_rename_real_loop_cache_invalidation(playwright_chromium, fixture_server):
    """Real loop run with shared LocatorCache: v2 page causes cache invalidation >= 1."""
    from agent.browser import Browser
    from agent.llm import ChatResponse, ToolCall, Usage
    from agent.locator_cache import LocatorCache
    from agent.loop import loop as real_loop

    _usage = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    def _tc(name: str, args: dict, call_id: str) -> ToolCall:
        return ToolCall(id=call_id, name=name, arguments=json.dumps(args))

    def _resp(tc: ToolCall) -> ChatResponse:
        return ChatResponse(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
            model="fake",
            usage=_usage,
            raw={},
        )

    def _text_resp(content: str) -> ChatResponse:
        return ChatResponse(
            content=content,
            tool_calls=[],
            finish_reason="stop",
            model="fake",
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            raw={},
            usd=0.0,
        )

    plan_stub = '{"steps": ["read submit button"], "expected_end_state": "done"}'

    def _make_llm(version_url: str):
        class _ScopedLLM:
            def __init__(self):
                self._call_index = 0

            def chat(self, messages, *, tools=None, **_):
                if tools is None:
                    return _text_resp(plan_stub)
                idx = self._call_index
                self._call_index += 1
                if idx == 0:
                    return _resp(_tc("read", {"intent": "Submit button"}, "tc-read"))
                return _resp(
                    _tc(
                        "done",
                        {
                            "result": {"ok": True},
                            "evidence": {"url": version_url, "text_snippet": "Submit"},
                        },
                        "tc-done",
                    )
                )

        return _ScopedLLM()

    cache = LocatorCache(path=":memory:")

    v1_url = f"{fixture_server}/drift/rename/v1/index.html"
    v2_url = f"{fixture_server}/drift/rename/v2/index.html"

    def _open_run(writer, run_id, task_str):
        run = Run(
            run_id=run_id,
            task=task_str,
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

    import uuid

    run_id_v1 = str(uuid.uuid4())
    with TraceWriter(path=":memory:") as writer_v1:
        _open_run(writer_v1, run_id_v1, "click Submit")
        with Browser(playwright_browser=playwright_chromium) as browser:
            browser.goto(v1_url)
            result_v1 = real_loop(
                "click Submit",
                browser,
                _make_llm(v1_url),
                max_steps=5,
                trace_writer=writer_v1,
                run_id=run_id_v1,
                locator_cache=cache,
            )

    run_id_v2 = str(uuid.uuid4())
    with TraceWriter(path=":memory:") as writer_v2:
        _open_run(writer_v2, run_id_v2, "click Submit")
        with Browser(playwright_browser=playwright_chromium) as browser:
            browser.goto(v2_url)
            result_v2 = real_loop(
                "click Submit",
                browser,
                _make_llm(v2_url),
                max_steps=5,
                trace_writer=writer_v2,
                run_id=run_id_v2,
                locator_cache=cache,
            )
        _, _, _, cache_events = _aggregate_diagnostics(writer_v2, run_id_v2)

    assert cache_events["invalidations"] >= 1, (
        f"Expected at least 1 cache invalidation on v2, got: {cache_events}"
    )
    assert result_v1.status in {"succeeded", "unverified"}, f"v1 status: {result_v1.status}"
    assert result_v2.status in {"succeeded", "unverified"}, f"v2 status: {result_v2.status}"


_FAILED_RUN_RESULT = RunResult(
    status="failed",
    result=None,
    evidence=None,
    verifier=None,
)


def test_run_case_failure_class_is_none_for_succeeded():
    with patch("scripts.eval.loop", return_value=_METRICS_RUN_RESULT):
        result = _run_case(_FIXTURE_CASE, llm_client=None, browser=None)
    assert result.failure_class is None


_NO_VALIDATOR_CASE = {
    "id": "no-validator-case",
    "domain": "fixture",
    "category": "read-and-summarize",
    "task": "Read the page heading",
    "expect": {"schema": {}, "validators": []},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}


def test_run_case_failure_class_no_done_emitted_when_loop_returns_failed():
    def _failing_loop_with_event(task, browser, llm_client, **kwargs):
        writer = kwargs.get("trace_writer")
        rid = kwargs.get("run_id")
        if writer is not None and rid is not None:
            writer.append_event(
                PlanEvent(
                    run_id=rid,
                    seq=writer.next_seq(rid),
                    ts=_ts(),
                    step_id=None,
                    reason="initial",
                    steps=["step 1"],
                    llm_call_id="c1",
                )
            )
        return _FAILED_RUN_RESULT

    with patch("scripts.eval.loop", side_effect=_failing_loop_with_event):
        result = _run_case(_NO_VALIDATOR_CASE, llm_client=None, browser=None)
    assert result.status == "failed"
    assert result.failure_class == "no_done_emitted"


# ---------------------------------------------------------------------------
# Phase 1 (Red): CaseResult failure_class / failure_detail fields
# ---------------------------------------------------------------------------


def test_case_result_failure_class_defaults_to_none():
    cr = CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])
    assert cr.failure_class is None
    assert cr.failure_detail is None


def test_case_result_failure_fields_serialise_to_json():
    cr = CaseResult(
        id="x",
        status="failed",
        steps=0,
        usd=0.0,
        l_tier_counts={},
        validators=[],
        failure_class="no_done_emitted",
        failure_detail=None,
    )
    serialized = json.dumps(asdict(cr))
    assert '"failure_class": "no_done_emitted"' in serialized
    assert '"failure_detail": null' in serialized


# ---------------------------------------------------------------------------
# Phase 2 (Red): _classify_failure synthetic trace tests
# ---------------------------------------------------------------------------


def _make_base_fields(run_id: str, seq: int) -> dict:
    return {"run_id": run_id, "seq": seq, "ts": _ts(), "step_id": "s1"}


def test_classify_failure_passing_status_returns_none():
    from scripts.eval import _classify_failure

    assert _classify_failure([], [], "succeeded") == (None, None)
    assert _classify_failure([], [], "unverified") == (None, None)
    assert _classify_failure([], [], "skipped") == (None, None)


def test_classify_failure_supervisor_halt():
    from agent.trace import SupervisorEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = SupervisorEvent(
        **_make_base_fields(rid, 1),
        trigger_event_seq=0,
        classified_as="Blocked",
        policy="halt",
        attempt=1,
    )
    fc, detail = _classify_failure([ev], [], "failed")
    assert fc == "supervisor_halt"
    assert "Blocked" in detail


def test_classify_failure_locator_miss():
    from agent.trace import LocateEvent, SupervisorEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    sup_ev = SupervisorEvent(
        **_make_base_fields(rid, 1),
        trigger_event_seq=0,
        classified_as="LocatorMiss",
        policy="next_tier",
        attempt=1,
    )
    loc_miss = LocateEvent(
        run_id=rid,
        seq=2,
        ts=_ts(),
        step_id="s1",
        intent="button",
        tier="L1_ax",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=5,
    )
    fc, _detail = _classify_failure([sup_ev, loc_miss], [], "failed")
    assert fc == "locator_miss"


def test_classify_failure_tool_error():
    from agent.trace import ActEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = ActEvent(
        **_make_base_fields(rid, 1),
        tool="click",
        args={},
        outcome="error",
        diff={"error": "TimeoutError"},
        ms=100,
    )
    fc, detail = _classify_failure([ev], [], "failed")
    assert fc == "tool_error"
    assert "TimeoutError" in detail


def test_classify_failure_tool_error_timeout():
    from agent.trace import ActEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = ActEvent(
        **_make_base_fields(rid, 1),
        tool="click",
        args={},
        outcome="timeout",
        diff={"error": "TimeoutError on selector X"},
        ms=100,
    )
    fc, detail = _classify_failure([ev], [], "failed")
    assert fc == "tool_error"
    assert "TimeoutError on selector X" in detail


def test_classify_failure_validator_fail():
    from agent.trace import DoneEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = DoneEvent(
        **_make_base_fields(rid, 1),
        result={},
        evidence={"url": "u", "text_snippet": "t"},
        verifier={"ok": True},
    )
    validators = [{"name": "title.nonempty", "ok": False}]
    fc, detail = _classify_failure([ev], validators, "failed")
    assert fc == "validator_fail"
    assert "title.nonempty" in detail


def test_classify_failure_schema_error():
    from agent.trace import DoneEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = DoneEvent(
        **_make_base_fields(rid, 1),
        result={},
        evidence={"url": "u", "text_snippet": "t"},
        verifier={"ok": False, "reasons": ["missing field: title"]},
    )
    fc, detail = _classify_failure([ev], [], "failed")
    assert fc == "schema_error"
    assert "missing field" in detail


def test_classify_failure_no_done_emitted():
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = PlanEvent(
        **_make_base_fields(rid, 1),
        reason="initial",
        steps=["step 1"],
        llm_call_id="c1",
    )
    fc, _detail = _classify_failure([ev], [], "failed")
    assert fc == "no_done_emitted"


def test_classify_failure_other():
    from agent.trace import DoneEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = DoneEvent(
        **_make_base_fields(rid, 1),
        result={},
        evidence={"url": "u", "text_snippet": "t"},
        verifier={"ok": True},
    )
    validators = [{"name": "title.nonempty", "ok": True}]
    fc, _detail = _classify_failure([ev], validators, "failed")
    assert fc == "other"


def test_classify_failure_skips_exception_named_validators_for_validator_fail():
    from agent.trace import DoneEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    ev = DoneEvent(
        **_make_base_fields(rid, 1),
        result={},
        evidence={"url": "u", "text_snippet": "t"},
        verifier={"ok": True},
    )
    validators = [
        {"name": "exception", "ok": False, "error": "RuntimeError(...)"},
    ]
    fc, fd = _classify_failure([ev], validators, "failed")
    assert fc != "validator_fail"
    assert fc == "other"


def test_classify_failure_supervisor_halt_beats_tool_error():
    from agent.trace import ActEvent, SupervisorEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    sup_ev = SupervisorEvent(
        **_make_base_fields(rid, 1),
        trigger_event_seq=0,
        classified_as="Blocked",
        policy="halt",
        attempt=1,
    )
    act_ev = ActEvent(
        **_make_base_fields(rid, 2),
        tool="click",
        args={},
        outcome="error",
        diff={"error": "boom"},
        ms=10,
    )
    fc, _detail = _classify_failure([sup_ev, act_ev], [], "failed")
    assert fc == "supervisor_halt"


def test_classify_failure_validator_fail_requires_done_event():
    from scripts.eval import _classify_failure

    validators = [{"name": "title.nonempty", "ok": False}]
    fc, _detail = _classify_failure([], validators, "failed")
    assert fc == "no_done_emitted"


def test_classify_failure_validator_fail_beats_schema_error():
    from agent.trace import DoneEvent
    from scripts.eval import _classify_failure

    rid = _make_run_id()
    done_ev = DoneEvent(
        **_make_base_fields(rid, 1),
        result={},
        evidence={"url": "u", "text_snippet": "t"},
        verifier={"ok": False, "reasons": ["missing field: title"]},
    )
    validators = [{"name": "title.nonempty", "ok": False}]
    fc, detail = _classify_failure([done_ev], validators, "failed")
    assert fc == "validator_fail"
    assert "title.nonempty" in detail


def test_run_case_failure_class_tool_error_when_loop_raises():
    case = {
        "id": "boom",
        "task": "do something",
        "budget": {"steps": 1, "usd": 1.0, "seconds": 30},
        "expect": {},
    }

    def _raising_loop(*args, **kwargs):
        raise RuntimeError("kaboom")

    with patch("scripts.eval.loop", _raising_loop):
        result = _run_case(case, llm_client=object(), browser=object())

    assert result.status == "failed"
    assert result.failure_class == "tool_error"
    assert result.failure_detail is not None
    assert "kaboom" in result.failure_detail


# ---------------------------------------------------------------------------
# implement-skip-reason-tagging (Red phase)
# ---------------------------------------------------------------------------


def test_skip_reason_required_when_skipped():
    with pytest.raises(ValueError):
        CaseResult(
            id="x",
            status="skipped",
            steps=0,
            usd=0.0,
            l_tier_counts={},
            validators=[],
            skip_reason=None,
        )


def test_skip_reason_rejects_unknown_value():
    with pytest.raises(ValueError):
        CaseResult(
            id="x",
            status="skipped",
            steps=0,
            usd=0.0,
            l_tier_counts={},
            validators=[],
            skip_reason="bogus",
        )


def test_live_disabled_skip_reason(tmp_path):
    live_case = {**_FIXTURE_CASE, "fixture": False}
    out = run_suite(cases=[live_case], results_dir=tmp_path, live=False)
    data = json.loads(out.read_text())
    assert data["cases"][0]["status"] == "skipped"
    assert data["cases"][0]["skip_reason"] == "live_disabled"


def test_fixture_missing_skip_reason(tmp_path):
    case_with_missing_fixture = {
        **_FIXTURE_CASE,
        "fixture": True,
        "fixture_path": "/nonexistent/path/to/fixture.html",
    }
    out = run_suite(cases=[case_with_missing_fixture], results_dir=tmp_path, live=True)
    data = json.loads(out.read_text())
    assert data["cases"][0]["status"] == "skipped"
    assert data["cases"][0]["skip_reason"] == "fixture_missing"


def test_existing_fixture_path_does_not_skip(tmp_path, monkeypatch):
    fixture_file = tmp_path / "fixture.html"
    fixture_file.write_text("<html></html>")
    case = {**_FIXTURE_CASE, "fixture": True, "fixture_path": str(fixture_file)}

    stub = CaseResult(
        id=case["id"],
        status="succeeded",
        steps=1,
        usd=0.0,
        l_tier_counts={},
        validators=[],
    )
    monkeypatch.setattr("scripts.eval._run_case", lambda *a, **kw: stub)

    out = run_suite(cases=[case], results_dir=tmp_path, live=True)
    data = json.loads(out.read_text())
    assert data["cases"][0]["status"] == "succeeded"
    assert data["cases"][0].get("skip_reason") is None


def test_all_valid_skip_reasons_accepted():
    for reason in (
        "live_disabled",
        "infra_unavailable",
        "fixture_missing",
        "feature_not_implemented",
    ):
        r = CaseResult(
            id="x",
            status="skipped",
            steps=0,
            usd=0.0,
            l_tier_counts={},
            validators=[],
            skip_reason=reason,
        )
        assert r.skip_reason == reason


def test_pass_statuses_is_public_module_attribute():
    from scripts.eval import PASS_STATUSES

    assert PASS_STATUSES == frozenset({"succeeded", "unverified"})


def test_fail_statuses_is_public_module_attribute():
    from scripts.eval import FAIL_STATUSES, PASS_STATUSES

    assert isinstance(FAIL_STATUSES, frozenset)
    assert FAIL_STATUSES == frozenset({"failed", "blocked", "timeout"})
    assert not FAIL_STATUSES & PASS_STATUSES


# canary field on CaseResult (eval-runner canary spec)


def test_case_result_canary_defaults_to_false():
    cr = CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])
    assert cr.canary is False


def test_case_result_canary_true_accepted():
    cr = CaseResult(
        id="x",
        status="succeeded",
        steps=0,
        usd=0.0,
        l_tier_counts={},
        validators=[],
        canary=True,
    )
    assert cr.canary is True


def test_case_result_canary_serialized_in_json():
    cr = CaseResult(
        id="fixture-heading",
        status="succeeded",
        steps=0,
        usd=0.0,
        l_tier_counts={},
        validators=[],
        canary=True,
    )
    data = json.loads(json.dumps(asdict(cr)))
    assert data["canary"] is True


def test_case_result_non_canary_serialized_as_false():
    cr = CaseResult(
        id="live-x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[]
    )
    data = json.loads(json.dumps(asdict(cr)))
    assert data["canary"] is False


# ---------------------------------------------------------------------------
# Integration test: fixture-count with stubbed LLM emitting listitem intent
# ---------------------------------------------------------------------------


def test_fixture_count_with_listitem_intent_stub_llm(playwright_chromium):
    from agent.browser import Browser
    from agent.llm import ChatResponse, ToolCall, Usage
    from scripts.eval import PASS_STATUSES, _run_case, load_cases

    cases = load_cases("eval/cases/fixture-count.yaml")
    case = cases[0]

    _usage = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    def _tc(name: str, args: dict, call_id: str) -> ToolCall:
        return ToolCall(id=call_id, name=name, arguments=json.dumps(args))

    def _resp(tc: ToolCall) -> ChatResponse:
        return ChatResponse(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
            model="fake",
            usage=_usage,
            raw={},
        )

    def _text_resp(content: str) -> ChatResponse:
        return ChatResponse(
            content=content,
            tool_calls=[],
            finish_reason="stop",
            model="fake",
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            raw={},
            usd=0.0,
        )

    plan_stub = '{"steps": ["read list items", "return items"], "expected_end_state": "done"}'
    fixture_url = case["fixture_url"]

    class _StubLLM:
        def __init__(self):
            self._call_index = 0

        def chat(self, messages, *, tools=None, **_):
            if tools is None:
                return _text_resp(plan_stub)
            idx = self._call_index
            self._call_index += 1
            if idx == 0:
                return _resp(_tc("read", {"intent": "list items"}, "tc-read"))
            return _resp(
                _tc(
                    "done",
                    {
                        "result": {"items": ["Item One", "Item Two", "Item Three"]},
                        "evidence": {"url": fixture_url, "text_snippet": "Item One"},
                    },
                    "tc-done",
                )
            )

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = _run_case(case, llm_client=_StubLLM(), browser=browser)

    assert result.status in PASS_STATUSES, (
        f"Expected status in PASS_STATUSES, got {result.status!r} "
        f"(failure_class={result.failure_class!r}, failure_detail={result.failure_detail!r})"
    )
