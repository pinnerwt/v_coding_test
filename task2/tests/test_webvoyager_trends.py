from __future__ import annotations

import json
from pathlib import Path


def _case(
    *,
    cid: str = "c",
    status: str = "succeeded",
    usd: float = 0.0,
    prompt: int = 0,
    completion: int = 0,
    latency_ms: int = 0,
    failure_class: str | None = None,
) -> dict:
    return {
        "id": cid,
        "status": status,
        "steps": 1,
        "usd": usd,
        "l_tier_counts": {},
        "validators": [],
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "latency_ms_total": latency_ms,
        "latency_ms_per_step": [latency_ms] if latency_ms else [],
        "step_breakdown": [],
        "failure_class": failure_class,
    }


def _write_run(path: Path, run_at: str, cases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_at": run_at, "cases": cases}))


def test_iter_webvoyager_runs_picks_latest_per_branch(tmp_path):
    from scripts.webvoyager_trends import iter_webvoyager_runs

    root = tmp_path / "benchmark"
    _write_run(
        root / "branch-a" / "webvoyager" / "20260101_000000.json",
        "2026-01-01T00:00:00+00:00",
        [_case()],
    )
    _write_run(
        root / "branch-a" / "webvoyager" / "20260102_000000.json",
        "2026-01-02T00:00:00+00:00",
        [_case(cid="newer")],
    )
    _write_run(
        root / "branch-b" / "webvoyager" / "20260103_000000.json",
        "2026-01-03T00:00:00+00:00",
        [_case()],
    )

    items = iter_webvoyager_runs(root)

    branches = [branch for branch, _, _ in items]
    assert branches == ["branch-a", "branch-b"]
    branch_a_data = next(data for branch, data, _ in items if branch == "branch-a")
    assert branch_a_data["cases"][0]["id"] == "newer"


def test_iter_webvoyager_runs_skips_branches_without_webvoyager_dir(tmp_path):
    from scripts.webvoyager_trends import iter_webvoyager_runs

    root = tmp_path / "benchmark"
    (root / "branch-without-webvoyager").mkdir(parents=True)
    (root / "branch-without-webvoyager" / "results.json").write_text(
        json.dumps({"run_at": "2026-01-01T00:00:00+00:00", "cases": []})
    )
    _write_run(
        root / "branch-with" / "webvoyager" / "20260102_000000.json",
        "2026-01-02T00:00:00+00:00",
        [_case()],
    )

    items = iter_webvoyager_runs(root)

    assert [branch for branch, _, _ in items] == ["branch-with"]


def test_iter_webvoyager_runs_skips_underscore_dirs(tmp_path):
    from scripts.webvoyager_trends import iter_webvoyager_runs

    root = tmp_path / "benchmark"
    _write_run(
        root / "_webvoyager_trends" / "webvoyager" / "20260101_000000.json",
        "2026-01-01T00:00:00+00:00",
        [_case()],
    )
    _write_run(
        root / "real-branch" / "webvoyager" / "20260102_000000.json",
        "2026-01-02T00:00:00+00:00",
        [_case()],
    )

    items = iter_webvoyager_runs(root)

    assert [branch for branch, _, _ in items] == ["real-branch"]


def test_write_webvoyager_trends_writes_all_four_svgs(tmp_path):
    from scripts.webvoyager_trends import write_webvoyager_trends

    root = tmp_path / "benchmark"
    _write_run(
        root / "branch-a" / "webvoyager" / "20260101_000000.json",
        "2026-01-01T00:00:00+00:00",
        [
            _case(cid="ok", status="succeeded", usd=0.05, latency_ms=5000),
            _case(
                cid="bad", status="failed", usd=0.01, latency_ms=2000, failure_class="tool_error"
            ),
        ],
    )

    write_webvoyager_trends(benchmark_root=root, readme_path=None)

    out_dir = root / "_webvoyager_trends"
    assert (out_dir / "pass_rate.svg").exists()
    assert (out_dir / "latency.svg").exists()
    assert (out_dir / "cost.svg").exists()
    assert (out_dir / "failure_classes.svg").exists()
    assert (out_dir / "pass_rate.svg").read_text().startswith("<svg")


def test_write_webvoyager_trends_updates_readme_block(tmp_path):
    from scripts.webvoyager_trends import write_webvoyager_trends

    root = tmp_path / "benchmark"
    _write_run(
        root / "branch-a" / "webvoyager" / "20260101_000000.json",
        "2026-01-01T00:00:00+00:00",
        [_case(cid="ok", status="succeeded", usd=0.05, latency_ms=5000)],
    )

    readme = tmp_path / "README.md"
    readme.write_text(
        "before\n<!-- WEBVOYAGER_TRENDS:BEGIN -->\nstale\n<!-- WEBVOYAGER_TRENDS:END -->\nafter\n"
    )

    write_webvoyager_trends(benchmark_root=root, readme_path=readme)

    text = readme.read_text()
    assert "before" in text
    assert "after" in text
    assert "stale" not in text
    assert "_webvoyager_trends/pass_rate.svg" in text
    assert "branch-a" in text


def test_write_webvoyager_trends_no_runs_writes_empty_svgs(tmp_path):
    from scripts.webvoyager_trends import write_webvoyager_trends

    root = tmp_path / "benchmark"
    root.mkdir()

    write_webvoyager_trends(benchmark_root=root, readme_path=None)

    out_dir = root / "_webvoyager_trends"
    assert (out_dir / "pass_rate.svg").exists()
    assert "no data" in (out_dir / "pass_rate.svg").read_text()
