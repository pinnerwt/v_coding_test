from __future__ import annotations

import json
from pathlib import Path

_FIXTURES = Path(__file__).parent / "fixtures" / "results"
_MASTER = _FIXTURES / "master_results.json"
_BRANCH = _FIXTURES / "branch_results.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# generate_diff_markdown — unit tests
# ---------------------------------------------------------------------------


def test_regression_marker_present():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    branch = _load(_BRANCH)
    out = generate_diff_markdown(master, branch)
    assert "⚠️ REGRESSION" in out


def test_improvement_marker_present():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    branch = _load(_BRANCH)
    out = generate_diff_markdown(master, branch)
    assert "✅ IMPROVEMENT" in out


def test_new_case_row_present():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    branch = _load(_BRANCH)
    out = generate_diff_markdown(master, branch)
    assert "fixture-c" in out
    assert "new" in out


def test_no_op_branch_produces_no_regression_or_improvement():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    out = generate_diff_markdown(master, master)
    assert "⚠️ REGRESSION" not in out
    assert "✅ IMPROVEMENT" not in out


def test_no_op_branch_all_unchanged():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    out = generate_diff_markdown(master, master)
    assert "unchanged" in out


def test_no_op_branch_pass_rate_delta_zero():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    out = generate_diff_markdown(master, master)
    assert "Δ pass-rate: +0%" in out


def test_aggregate_pass_rate_signed_correctly():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "c2", "status": "succeeded", "usd": 0.01, "latency_ms_total": 2000},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "failed", "usd": 0.02, "latency_ms_total": 500},
            {"id": "c2", "status": "succeeded", "usd": 0.02, "latency_ms_total": 1500},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "Δ pass-rate: -50%" in out


def test_aggregate_usd_delta_positive():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "c2", "status": "succeeded", "usd": 0.01, "latency_ms_total": 2000},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "succeeded", "usd": 0.02, "latency_ms_total": 500},
            {"id": "c2", "status": "succeeded", "usd": 0.02, "latency_ms_total": 1500},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "Δ total USD: +$0.0200" in out


def test_aggregate_latency_delta_negative():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "c2", "status": "succeeded", "usd": 0.01, "latency_ms_total": 2000},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "succeeded", "usd": 0.02, "latency_ms_total": 500},
            {"id": "c2", "status": "succeeded", "usd": 0.02, "latency_ms_total": 1500},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "Δ p50 latency: -500ms" in out
    assert "Δ p95 latency: -500ms" in out


def test_header_contains_run_at_timestamps():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    branch = _load(_BRANCH)
    out = generate_diff_markdown(master, branch)
    assert master["run_at"] in out
    assert branch["run_at"] in out


def test_delta_vs_master_heading():
    from scripts.baseline_diff import generate_diff_markdown

    master = _load(_MASTER)
    branch = _load(_BRANCH)
    out = generate_diff_markdown(master, branch)
    assert "Δ vs master" in out


# ---------------------------------------------------------------------------
# write_diff — integration tests
# ---------------------------------------------------------------------------


def test_write_diff_writes_diff_md_for_non_master_branch(tmp_path):
    from scripts.benchmark import write_diff

    master_dir = tmp_path / "master"
    master_dir.mkdir()
    (master_dir / "results.json").write_text(json.dumps(_load(_MASTER)))

    branch_dir = tmp_path / "my-feature"
    branch_dir.mkdir()

    branch_data = _load(_BRANCH)
    write_diff("my-feature", branch_data, benchmark_root=tmp_path)

    diff_path = tmp_path / "my-feature" / "diff.md"
    assert diff_path.exists()
    content = diff_path.read_text()
    assert "Δ vs master" in content


def test_write_diff_skips_master_branch(tmp_path):
    from scripts.benchmark import write_diff

    master_dir = tmp_path / "master"
    master_dir.mkdir()
    (master_dir / "results.json").write_text(json.dumps(_load(_MASTER)))

    branch_data = _load(_BRANCH)
    write_diff("master", branch_data, benchmark_root=tmp_path)

    diff_path = tmp_path / "master" / "diff.md"
    assert not diff_path.exists()


def test_write_diff_missing_baseline_skips_gracefully(tmp_path, capsys):
    from scripts.benchmark import write_diff

    branch_dir = tmp_path / "my-feature"
    branch_dir.mkdir()
    branch_data = _load(_BRANCH)

    write_diff("my-feature", branch_data, benchmark_root=tmp_path)

    diff_path = tmp_path / "my-feature" / "diff.md"
    assert not diff_path.exists()
    captured = capsys.readouterr()
    assert captured.err != ""


def test_per_case_table_order_is_deterministic():
    from scripts.baseline_diff import generate_diff_markdown

    master_abc = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "b", "status": "failed", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
        ],
    }
    master_cba = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "b", "status": "failed", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "b", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
        ],
    }
    out_abc = generate_diff_markdown(master_abc, branch)
    out_cba = generate_diff_markdown(master_cba, branch)
    assert out_abc == out_cba


def test_dropped_case_row_present():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "x", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "y", "status": "failed", "usd": 0.005, "latency_ms_total": 500},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "x", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "y" in out
    assert "dropped" in out


def test_latency_delta_uses_intersection_of_case_ids():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 100},
            {"id": "b", "status": "succeeded", "usd": 0.01, "latency_ms_total": 200},
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 300},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 100},
            {"id": "b", "status": "succeeded", "usd": 0.01, "latency_ms_total": 200},
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 300},
            {"id": "d", "status": "succeeded", "usd": 0.01, "latency_ms_total": 50},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "Δ p50 latency: +0ms" in out
    assert "Δ p95 latency: +0ms" in out


def test_cases_annotation_reflects_added_case():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 100},
            {"id": "b", "status": "succeeded", "usd": 0.01, "latency_ms_total": 200},
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 300},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 100},
            {"id": "b", "status": "succeeded", "usd": 0.01, "latency_ms_total": 200},
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 300},
            {"id": "d", "status": "succeeded", "usd": 0.01, "latency_ms_total": 50},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "Cases: 3 common, +1 added, -0 dropped" in out


def test_cases_annotation_all_zeros_for_identical_runs():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "c1", "status": "succeeded", "usd": 0.01, "latency_ms_total": 1000},
            {"id": "c2", "status": "succeeded", "usd": 0.01, "latency_ms_total": 2000},
        ],
    }
    out = generate_diff_markdown(master, master)
    assert "Cases: 2 common, +0 added, -0 dropped" in out


def test_latency_delta_empty_intersection_renders_dash():
    from scripts.baseline_diff import generate_diff_markdown

    master = {
        "run_at": "2026-04-20T00:00:00+00:00",
        "cases": [
            {"id": "a", "status": "succeeded", "usd": 0.01, "latency_ms_total": 100},
            {"id": "b", "status": "succeeded", "usd": 0.01, "latency_ms_total": 200},
        ],
    }
    branch = {
        "run_at": "2026-04-28T00:00:00+00:00",
        "cases": [
            {"id": "c", "status": "succeeded", "usd": 0.01, "latency_ms_total": 300},
            {"id": "d", "status": "succeeded", "usd": 0.01, "latency_ms_total": 400},
        ],
    }
    out = generate_diff_markdown(master, branch)
    assert "Δ p50 latency: —" in out
    assert "Δ p95 latency: —" in out
    assert "Cases: 0 common, +2 added, -2 dropped" in out
