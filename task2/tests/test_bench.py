from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.loop import RunResult

_WEBVOYAGER_FIXTURE = Path(__file__).parent / "fixtures/benchmarks/webvoyager/tasks_sample.json"
_BRIEF_PATH = Path(__file__).parents[2] / "prompts/task2/web-benchmarks.md"
_TIER1_PATH = Path(__file__).parents[1] / "eval/bench/data/webvoyager/tier1.json"

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


def test_loader_fixture_is_false():
    from eval.bench.webvoyager_loader import load_webvoyager

    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    for item in cases:
        assert item["fixture"] is False, f"expected fixture=False, got {item['fixture']!r}"


def test_loader_id_prefix():
    from eval.bench.webvoyager_loader import load_webvoyager

    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    assert cases[0]["id"].startswith("webvoyager-")


def test_loader_maps_ques_to_task():
    from eval.bench.webvoyager_loader import load_webvoyager

    with _WEBVOYAGER_FIXTURE.open() as f:
        raw = json.load(f)
    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    assert raw[0]["ques"] in cases[0]["task"]


def test_loader_task_includes_start_url():
    from eval.bench.webvoyager_loader import load_webvoyager

    with _WEBVOYAGER_FIXTURE.open() as f:
        raw = json.load(f)
    cases = load_webvoyager(str(_WEBVOYAGER_FIXTURE))
    for entry, case in zip(raw, cases, strict=True):
        assert entry["web"] in case["task"], f"start URL missing from task: {case['task']!r}"


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
        patch("scripts.eval.Browser") as mock_browser,
        patch("scripts.eval.LLMClient"),
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
        patch("scripts.eval.Browser") as mock_browser,
        patch("scripts.eval.LLMClient"),
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


def test_runner_honors_llm_base_url(tmp_path, monkeypatch):
    from scripts.bench import main

    monkeypatch.setenv("WEBVOYAGER_TASKS", str(_WEBVOYAGER_FIXTURE))
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BASE_URL", "http://custom:9999/v1")

    with (
        patch("scripts.eval.Browser") as mock_browser,
        patch("scripts.eval.LLMClient") as mock_llm,
    ):
        mock_browser.return_value.__enter__ = MagicMock(return_value=mock_browser.return_value)
        mock_browser.return_value.__exit__ = MagicMock(return_value=False)
        main(["--suite", "webvoyager"])

    mock_llm.assert_called_once()
    call_kwargs = mock_llm.call_args
    assert call_kwargs.kwargs.get("base_url") == "http://custom:9999/v1" or (
        len(call_kwargs.args) > 0 and call_kwargs.args[0] == "http://custom:9999/v1"
    ), f"LLMClient not called with base_url=http://custom:9999/v1, got: {call_kwargs}"


_EXCLUDED_DOMAINS = ["Allrecipes", "Apple", "Coursera", "Google", "Booking", "Amazon"]


def test_tier1_fixture_exists():
    assert _TIER1_PATH.exists(), f"Tier-1 fixture not found at {_TIER1_PATH}"


def test_tier1_loader_returns_12_cases():
    from eval.bench.webvoyager_loader import load_webvoyager

    cases = load_webvoyager(str(_TIER1_PATH))
    assert len(cases) == 12
    for case in cases:
        for key in ("task", "domain", "category", "id"):
            assert key in case, f"case missing key: {key}"


def test_tier1_no_excluded_domains():
    from eval.bench.webvoyager_loader import load_webvoyager

    cases = load_webvoyager(str(_TIER1_PATH))
    for case in cases:
        category = case["category"]
        for excl in _EXCLUDED_DOMAINS:
            assert excl not in category, f"excluded domain '{excl}' found in category '{category}'"


def _make_mock_browser():
    mock_browser = MagicMock()
    mock_browser.__enter__ = MagicMock(return_value=mock_browser)
    mock_browser.__exit__ = MagicMock(return_value=False)
    return mock_browser


def _capture_loader_paths(tmp_path, argv):
    from scripts.bench import main

    captured: list[str] = []

    def fake_loader(path):
        captured.append(path)
        return []

    result_file = tmp_path / "result.json"
    result_file.write_text('{"cases": []}')

    with (
        patch("scripts.bench._LOADERS", {"webvoyager": fake_loader}),
        patch("scripts.bench.build_clients") as mock_clients,
        patch("scripts.bench.run_suite") as mock_suite,
    ):
        mock_clients.return_value = (MagicMock(), _make_mock_browser())
        mock_suite.return_value = result_file
        main(argv)

    return captured


def test_bench_tier_flag_default_selects_tier0(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.delenv("WEBVOYAGER_TASKS", raising=False)

    captured = _capture_loader_paths(tmp_path, ["--suite", "webvoyager"])

    assert len(captured) == 1
    assert captured[0].endswith("tasks_sample.json"), captured[0]


def test_bench_tier1_flag_selects_tier1_path(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.delenv("WEBVOYAGER_TASKS", raising=False)

    captured = _capture_loader_paths(tmp_path, ["--suite", "webvoyager", "--tier", "1"])

    assert len(captured) == 1
    assert captured[0].endswith("tier1.json"), captured[0]


def test_bench_webvoyager_tasks_env_overrides_tier1(tmp_path, monkeypatch):
    custom_path = "/custom/path/my_tasks.json"
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.setenv("WEBVOYAGER_TASKS", custom_path)

    captured = _capture_loader_paths(tmp_path, ["--suite", "webvoyager", "--tier", "1"])

    assert captured == [custom_path]


def test_bench_sets_llm_temperature_to_zero_by_default(tmp_path, monkeypatch):
    """Bench runs are reproducibility-first: force greedy decoding so apparent
    pass/fail flips reflect agent/page changes, not LLM sampling noise."""
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.delenv("WEBVOYAGER_TASKS", raising=False)
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)

    _capture_loader_paths(tmp_path, ["--suite", "webvoyager"])

    assert os.environ.get("LLM_TEMPERATURE") == "0.0"


def test_bench_respects_explicit_llm_temperature_env(tmp_path, monkeypatch):
    """A user who deliberately sets LLM_TEMPERATURE keeps their value — bench
    only fills in 0.0 when the env is unset."""
    monkeypatch.setenv("EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.delenv("WEBVOYAGER_TASKS", raising=False)
    monkeypatch.setenv("LLM_TEMPERATURE", "0.3")

    _capture_loader_paths(tmp_path, ["--suite", "webvoyager"])

    assert os.environ.get("LLM_TEMPERATURE") == "0.3"
