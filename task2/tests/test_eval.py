from __future__ import annotations

import json
import re
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
