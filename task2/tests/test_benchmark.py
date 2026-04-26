from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_resolve_branch_prefers_explicit_arg(monkeypatch):
    from scripts.benchmark import resolve_branch

    monkeypatch.setenv("GITHUB_HEAD_REF", "from-env")
    assert resolve_branch("explicit") == "explicit"


def test_resolve_branch_uses_github_head_ref_env(monkeypatch):
    from scripts.benchmark import resolve_branch

    monkeypatch.setenv("GITHUB_HEAD_REF", "feature/x")
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    assert resolve_branch(None) == "feature/x"


def test_resolve_branch_uses_github_ref_name_when_no_head_ref(monkeypatch):
    from scripts.benchmark import resolve_branch

    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF_NAME", "master")
    assert resolve_branch(None) == "master"


def test_sanitize_branch_strips_unsafe_chars():
    from scripts.benchmark import sanitize_branch

    assert sanitize_branch("feature/x") == "feature-x"
    assert sanitize_branch("foo bar") == "foo-bar"
    assert sanitize_branch("ok_name.1") == "ok_name.1"
    assert sanitize_branch("../escape") == "escape"


def test_sanitize_branch_rejects_empty():
    from scripts.benchmark import sanitize_branch

    with pytest.raises(ValueError):
        sanitize_branch("")
    with pytest.raises(ValueError):
        sanitize_branch("///")


def test_write_outputs_writes_results_and_scoreboard(tmp_path):
    from scripts.benchmark import write_outputs

    results = {
        "run_at": "2026-04-26T00:00:00+00:00",
        "cases": [
            {
                "id": "c1",
                "status": "succeeded",
                "steps": 1,
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "latency_ms_total": 200,
                "latency_ms_per_step": [200],
                "step_breakdown": [],
            }
        ],
    }
    out_dir = tmp_path / "benchmark" / "master"
    write_outputs(results, out_dir=out_dir)

    assert (out_dir / "results.json").exists()
    assert (out_dir / "scoreboard.md").exists()
    saved = json.loads((out_dir / "results.json").read_text())
    assert saved["cases"][0]["id"] == "c1"
    md = (out_dir / "scoreboard.md").read_text()
    assert "succeeded" in md
    assert "1/1" in md


def test_output_dir_for_branch_under_task2_benchmark(tmp_path, monkeypatch):
    from scripts.benchmark import output_dir_for_branch

    monkeypatch.chdir(tmp_path)
    p = output_dir_for_branch("feature/x")
    assert p == Path("benchmark") / "feature-x"


def _write_results(path: Path, run_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_at": run_at,
                "cases": [
                    {
                        "id": "c1",
                        "status": "succeeded",
                        "steps": 1,
                        "usd": 0.0,
                        "l_tier_counts": {},
                        "validators": [],
                    }
                ],
            }
        )
    )


def test_verify_passes_when_results_fresh(tmp_path, monkeypatch):
    from scripts.benchmark import verify_benchmark

    monkeypatch.chdir(tmp_path)
    _write_results(
        tmp_path / "benchmark" / "feature-x" / "results.json",
        "2026-04-26T12:00:00+00:00",
    )
    verify_benchmark(branch="feature/x", base_date="2026-04-26T11:00:00+00:00")


def test_verify_fails_when_results_missing(tmp_path, monkeypatch):
    from scripts.benchmark import BenchmarkVerificationError, verify_benchmark

    monkeypatch.chdir(tmp_path)
    with pytest.raises(BenchmarkVerificationError, match="missing"):
        verify_benchmark(branch="feature/x", base_date="2026-04-26T11:00:00+00:00")


def test_verify_fails_when_results_older_than_base(tmp_path, monkeypatch):
    from scripts.benchmark import BenchmarkVerificationError, verify_benchmark

    monkeypatch.chdir(tmp_path)
    _write_results(
        tmp_path / "benchmark" / "feature-x" / "results.json",
        "2026-04-26T10:00:00+00:00",
    )
    with pytest.raises(BenchmarkVerificationError, match="stale"):
        verify_benchmark(branch="feature/x", base_date="2026-04-26T11:00:00+00:00")
