from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts.eval import load_cases, run_suite, run_validators
from agent.loop import RunResult


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


# ---------- results JSON shape ----------


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


# ---------- case loader ----------


def test_load_cases_valid_yaml(tmp_path):
    p = tmp_path / "case.yaml"
    p.write_text(yaml.dump([{
        "id": "test-case",
        "domain": "example.com",
        "category": "search-and-extract",
        "task": "Find something",
        "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
        "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    }]))
    cases = load_cases(p)
    assert len(cases) == 1
    c = cases[0]
    for field in ("id", "domain", "category", "task", "expect", "budget"):
        assert field in c, f"missing field: {field}"


def test_load_cases_missing_required_field_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.dump([{
        "id": "test-case",
        "domain": "example.com",
        "category": "search-and-extract",
        "expect": {"schema": {}, "validators": []},
        "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    }]))
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


# ---------- validator runner ----------


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
