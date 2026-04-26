from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.loop import RunResult
from scripts.eval import load_cases, run_suite

_LIVE_CASE = {
    "id": "live-test",
    "domain": "example.com",
    "category": "search-and-extract",
    "task": "Return something as summary",
    "expect": {"schema": {"summary": "str"}, "validators": ["summary.nonempty"]},
    "budget": {"steps": 20, "usd": 0.25, "seconds": 120},
    "live": True,
}

_FIXTURE_CASE = {
    "id": "fixture-test",
    "domain": "fixture",
    "category": "read-and-summarize",
    "task": "Read the page heading and return it as title",
    "expect": {"schema": {"title": "str"}, "validators": ["title.nonempty"]},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
    "fixture": True,
}

_CANNED_RESULT = RunResult(
    status="succeeded",
    result={"summary": "Hello", "title": "Hello"},
    evidence={"url": "http://x", "text_snippet": "Hello"},
    verifier={"ok": True, "reasons": []},
)

_REQUIRED_FIELDS = ("id", "domain", "category", "task", "expect", "budget")
_LIVE_YAML_PATHS = sorted((Path(__file__).parent.parent / "eval" / "cases").glob("live-*.yaml"))


@pytest.mark.parametrize(
    ("live", "expected_status"),
    [(False, "skipped"), (True, "succeeded")],
)
def test_live_flag_gates_execution(tmp_path, live, expected_status):
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[_LIVE_CASE], results_dir=tmp_path, live=live)
    data = json.loads(out.read_text())
    assert data["cases"][0]["status"] == expected_status


def test_mixed_suite_gating(tmp_path):
    with patch("scripts.eval.loop", return_value=_CANNED_RESULT):
        out = run_suite(cases=[_FIXTURE_CASE, _LIVE_CASE], results_dir=tmp_path, live=False)
    data = json.loads(out.read_text())
    assert len(data["cases"]) == 2
    assert data["cases"][0]["status"] == "succeeded"
    assert data["cases"][1]["status"] == "skipped"


def test_all_live_yaml_files_load():
    assert len(_LIVE_YAML_PATHS) == 5, f"expected 5 live YAML files, found {len(_LIVE_YAML_PATHS)}"
    for path in _LIVE_YAML_PATHS:
        cases = load_cases(path)
        assert len(cases) == 1, f"{path}: expected 1 case, got {len(cases)}"
        case = cases[0]
        for field in _REQUIRED_FIELDS:
            assert field in case, f"{path}: missing required field {field!r}"
        assert case.get("fixture", False) is False, f"{path}: must not have fixture: true"
