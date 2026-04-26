from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agent.loop import RunResult
from scripts.eval import load_cases, run_suite, run_validators

_FIXTURE_CASE = {
    "id": "fixture-heading",
    "domain": "fixture",
    "category": "read-and-summarize",
    "task": "Read the page heading and return it as title",
    "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
    "fixture_url": "http://localhost/index.html",
}

_CANNED_RESULT = RunResult(
    status="succeeded",
    result={"title": "Hello"},
    evidence={"url": "http://x", "text_snippet": "Hello"},
    verifier={"ok": True, "reasons": []},
)


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
    case2 = {
        "id": "fixture-count",
        "domain": "fixture",
        "category": "search-and-extract",
        "task": "Return items",
        "expect": {"schema": {"items": "list[str]"}, "validators": ["items.len_gte: 1"]},
        "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
        "fixture": True,
    }
    canned2 = RunResult(
        status="succeeded",
        result={"items": ["a"]},
        evidence={"url": "http://x", "text_snippet": "a"},
        verifier={"ok": True, "reasons": []},
    )
    with patch("scripts.eval.loop", side_effect=[_CANNED_RESULT, canned2]):
        out = run_suite(cases=[_FIXTURE_CASE, case2], results_dir=tmp_path)
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
    from scripts.eval import _build_clients

    monkeypatch.setenv("LLM_BASE_URL", "http://custom:9999/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    with (
        patch("scripts.eval.LLMClient") as mock_llm,
        patch("scripts.eval.Browser") as mock_browser,
    ):
        mock_llm.return_value = MagicMock()
        mock_browser.return_value = MagicMock()
        _build_clients()
        mock_llm.assert_called_once_with(
            base_url="http://custom:9999/v1",
            model="test-model",
            api_key="test-key",
        )
