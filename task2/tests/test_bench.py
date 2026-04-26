from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.loop import RunResult

_WEBVOYAGER_FIXTURE = Path(__file__).parent / "fixtures/benchmarks/webvoyager/tasks_sample.json"
_BRIEF_PATH = Path(__file__).parents[2] / "prompts/task2/web-benchmarks.md"

_CANNED_RESULT = RunResult(
    status="succeeded",
    result={"answer": "hello"},
    evidence={"url": "http://x", "text_snippet": "hello"},
    verifier={"ok": True, "reasons": []},
)


def test_brief_exists():
    assert _BRIEF_PATH.exists()


def test_brief_names_selected_benchmark():
    text = _BRIEF_PATH.read_text()
    assert "WebVoyager" in text
    assert any(w in text for w in ("selected", "Selected", "SELECTED"))


def test_brief_lists_all_benchmarks():
    text = _BRIEF_PATH.read_text()
    for name in (
        "WebArena",
        "Mind2Web",
        "BrowserGym",
        "WebVoyager",
        "MiniWoB++",
        "WebShop",
        "GAIA",
    ):
        assert name in text, f"brief missing: {name}"


def test_fixture_file_exists():
    assert _WEBVOYAGER_FIXTURE.exists()


def test_fixture_parses_as_json():
    with _WEBVOYAGER_FIXTURE.open() as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert 3 <= len(data) <= 5
    for entry in data:
        for key in ("id", "web_name", "ques", "web"):
            assert key in entry, f"entry missing key: {key}"


def test_loader_returns_case_dicts():
    from eval.bench.webvoyager_loader import load_webvoyager

    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    assert isinstance(cases, list)
    for item in cases:
        for key in ("id", "task", "domain", "category", "expect", "budget", "fixture"):
            assert key in item, f"case missing key: {key}"


def test_loader_id_prefix():
    from eval.bench.webvoyager_loader import load_webvoyager

    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    assert cases[0]["id"].startswith("webvoyager-")


def test_loader_maps_ques_to_task():
    from eval.bench.webvoyager_loader import load_webvoyager

    with _WEBVOYAGER_FIXTURE.open() as f:
        raw = json.load(f)
    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    assert cases[0]["task"] == raw[0]["ques"]


def test_loader_maps_web_to_domain():
    from eval.bench.webvoyager_loader import load_webvoyager

    with _WEBVOYAGER_FIXTURE.open() as f:
        raw = json.load(f)
    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    assert cases[0]["domain"] == raw[0]["web"]


def test_runner_smoke_no_live(tmp_path, monkeypatch):
    from scripts.bench import main

    monkeypatch.setenv("WEBVOYAGER_TASKS", str(_WEBVOYAGER_FIXTURE))
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))

    with (
        patch("scripts.bench.Browser") as mock_browser,
        patch("scripts.bench.LLMClient"),
    ):
        mock_browser.return_value.__enter__ = MagicMock(return_value=mock_browser.return_value)
        mock_browser.return_value.__exit__ = MagicMock(return_value=False)
        main(["--suite", "webvoyager"])

    result_files = list(tmp_path.glob("*.json"))
    assert len(result_files) == 1
    data = json.loads(result_files[0].read_text())
    assert "run_at" in data
    assert "cases" in data
    for case in data["cases"]:
        assert case["status"] == "skipped"


def test_runner_smoke_result_shape(tmp_path, monkeypatch):
    from scripts.bench import main

    monkeypatch.setenv("WEBVOYAGER_TASKS", str(_WEBVOYAGER_FIXTURE))
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))

    with (
        patch("scripts.eval.loop", return_value=_CANNED_RESULT),
        patch("scripts.bench.Browser") as mock_browser,
        patch("scripts.bench.LLMClient"),
    ):
        mock_browser.return_value.__enter__ = MagicMock(return_value=mock_browser.return_value)
        mock_browser.return_value.__exit__ = MagicMock(return_value=False)
        main(["--suite", "webvoyager", "--live"])

    result_files = list(tmp_path.glob("*.json"))
    assert len(result_files) == 1
    data = json.loads(result_files[0].read_text())
    assert "run_at" in data
    assert "cases" in data
    assert len(data["cases"]) >= 1
    case = data["cases"][0]
    for key in ("id", "status", "steps", "usd", "l_tier_counts", "validators"):
        assert key in case, f"case missing key: {key}"
