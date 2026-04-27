from __future__ import annotations

import json
from pathlib import Path


def _write_run(path: Path, run_at: str, cases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_at": run_at, "cases": cases}))


def _case(
    *,
    cid: str = "c",
    status: str = "succeeded",
    usd: float = 0.0,
    prompt: int = 0,
    completion: int = 0,
    latency_ms: int = 0,
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
    }


def test_summarize_run_computes_pass_rate_and_totals():
    from scripts.trends import summarize_run

    data = {
        "run_at": "2026-04-26T00:00:00+00:00",
        "cases": [
            _case(cid="a", status="succeeded", usd=0.01, prompt=10, completion=2, latency_ms=100),
            _case(cid="b", status="failed", usd=0.02, prompt=20, completion=4, latency_ms=300),
            _case(cid="c", status="skipped"),
        ],
    }
    summary = summarize_run("feature-x", data)
    assert summary.branch == "feature-x"
    assert summary.run_at.isoformat().startswith("2026-04-26")
    # 1 of 2 non-skipped passed
    assert summary.pass_rate == 0.5
    assert summary.total_usd == 0.03
    assert summary.total_tokens == 36
    assert summary.p50_ms in (100, 300)
    assert summary.p95_ms == 300
    assert summary.total_cases == 2


def test_collect_runs_sorts_by_run_at_and_skips_underscore(tmp_path):
    from scripts.trends import collect_runs

    _write_run(tmp_path / "a" / "results.json", "2026-04-26T03:00:00+00:00", [_case()])
    _write_run(tmp_path / "b" / "results.json", "2026-04-26T01:00:00+00:00", [_case()])
    _write_run(tmp_path / "_trends" / "results.json", "2026-04-26T02:00:00+00:00", [_case()])
    # dir without results.json should be ignored
    (tmp_path / "empty").mkdir()

    runs = collect_runs(tmp_path)
    assert [r.branch for r in runs] == ["b", "a"]


def test_render_pass_rate_chart_returns_svg_with_data():
    from datetime import UTC, datetime

    from scripts.trends import Run, render_pass_rate_svg

    runs = [
        Run(
            branch="b1",
            run_at=datetime(2026, 4, 26, 1, tzinfo=UTC),
            pass_rate=0.25,
            total_usd=0.0,
            p50_ms=0,
            p95_ms=0,
            total_tokens=0,
            total_cases=4,
        ),
        Run(
            branch="b2",
            run_at=datetime(2026, 4, 26, 2, tzinfo=UTC),
            pass_rate=0.75,
            total_usd=0.0,
            p50_ms=0,
            p95_ms=0,
            total_tokens=0,
            total_cases=4,
        ),
    ]
    svg = render_pass_rate_svg(runs)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "b1" in svg
    assert "b2" in svg
    assert "Pass rate" in svg


def test_render_handles_empty_runs():
    from scripts.trends import render_cost_svg, render_latency_svg, render_pass_rate_svg

    for fn in (render_pass_rate_svg, render_latency_svg, render_cost_svg):
        svg = fn([])
        assert svg.startswith("<svg")
        assert "no data" in svg.lower()


def test_write_trends_creates_three_svgs(tmp_path):
    from scripts.trends import collect_runs, write_trends

    _write_run(
        tmp_path / "bench" / "a" / "results.json",
        "2026-04-26T01:00:00+00:00",
        [_case(latency_ms=100, usd=0.01, prompt=10, completion=2)],
    )
    _write_run(
        tmp_path / "bench" / "b" / "results.json",
        "2026-04-26T02:00:00+00:00",
        [_case(latency_ms=200, usd=0.02, prompt=20, completion=4)],
    )

    out_dir = tmp_path / "bench" / "_trends"
    runs = collect_runs(tmp_path / "bench")
    write_trends(runs, out_dir=out_dir)

    assert (out_dir / "pass_rate.svg").exists()
    assert (out_dir / "latency.svg").exists()
    assert (out_dir / "cost.svg").exists()


