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


def test_summarize_run_splits_passed_and_failed():
    from scripts.trends import summarize_run

    data = {
        "run_at": "2026-04-26T00:00:00+00:00",
        "cases": [
            _case(cid="a", status="succeeded", usd=0.03, latency_ms=400),
            _case(cid="b", status="succeeded", usd=0.05, latency_ms=600),
            _case(cid="c", status="failed", usd=0.01, latency_ms=100),
            _case(cid="d", status="failed", usd=0.02, latency_ms=200),
            _case(cid="e", status="skipped"),
        ],
    }
    s = summarize_run("feat", data)
    assert s.passed_count == 2
    assert s.failed_count == 2
    assert s.usd_passed == 0.08
    assert s.usd_failed == 0.03
    # passed median is one of (400, 600); failed median is one of (100, 200)
    assert s.p50_passed_ms in (400, 600)
    assert s.p50_failed_ms in (100, 200)


def test_summarize_run_handles_zero_passed_or_failed():
    from scripts.trends import summarize_run

    only_failed = summarize_run(
        "x",
        {
            "run_at": "2026-04-26T00:00:00+00:00",
            "cases": [_case(cid="a", status="failed", usd=0.01, latency_ms=100)],
        },
    )
    assert only_failed.passed_count == 0
    assert only_failed.usd_passed == 0.0
    assert only_failed.p50_passed_ms == 0


def test_render_cost_svg_splits_passed_and_failed():
    from datetime import UTC, datetime

    from scripts.trends import Run, render_cost_svg

    run = Run(
        branch="b1",
        run_at=datetime(2026, 4, 26, 1, tzinfo=UTC),
        pass_rate=0.5,
        total_usd=0.05,
        p50_ms=0,
        p95_ms=0,
        total_tokens=0,
        total_cases=2,
        passed_count=1,
        failed_count=1,
        usd_passed=0.04,
        usd_failed=0.01,
        p50_passed_ms=400,
        p50_failed_ms=100,
    )
    svg = render_cost_svg([run])
    assert "passed" in svg.lower()
    assert "failed" in svg.lower()
    # both totals are shown as labels
    assert "$0.04" in svg
    assert "$0.01" in svg


def test_render_latency_svg_splits_passed_and_failed():
    from datetime import UTC, datetime

    from scripts.trends import Run, render_latency_svg

    run = Run(
        branch="b1",
        run_at=datetime(2026, 4, 26, 1, tzinfo=UTC),
        pass_rate=0.5,
        total_usd=0.0,
        p50_ms=0,
        p95_ms=0,
        total_tokens=0,
        total_cases=2,
        passed_count=1,
        failed_count=1,
        usd_passed=0.0,
        usd_failed=0.0,
        p50_passed_ms=420,
        p50_failed_ms=110,
    )
    svg = render_latency_svg([run])
    assert "passed" in svg.lower()
    assert "failed" in svg.lower()


def test_render_latest_run_table_emits_markdown():
    from scripts.trends import render_latest_run_table

    data = {
        "run_at": "2026-04-26T12:34:56+00:00",
        "cases": [
            {
                "id": "case-a",
                "status": "succeeded",
                "steps": 5,
                "usd": 0.012,
                "prompt_tokens": 800,
                "completion_tokens": 200,
                "latency_ms_total": 12345,
            },
            {
                "id": "case-b",
                "status": "failed",
                "steps": 1,
                "usd": 0.001,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "latency_ms_total": 2000,
            },
            {
                "id": "case-c",
                "status": "skipped",
                "steps": 0,
                "usd": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms_total": 0,
            },
        ],
    }
    md = render_latest_run_table("my-branch", data)
    assert "my-branch" in md
    assert "2026-04-26" in md
    assert "case-a" in md
    assert "case-b" in md
    # skipped cases excluded
    assert "case-c" not in md
    # totals row
    assert "Total" in md
    # markdown table header present
    assert "| Case" in md
    assert "USD" in md


def test_write_trends_updates_readme_block(tmp_path):
    from scripts.trends import collect_runs, write_trends

    _write_run(
        tmp_path / "bench" / "feat" / "results.json",
        "2026-04-26T01:00:00+00:00",
        [
            _case(cid="a", status="succeeded", latency_ms=400, usd=0.04, prompt=300, completion=80),
            _case(cid="b", status="failed", latency_ms=100, usd=0.01, prompt=50, completion=10),
        ],
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Title\n\n"
        "<!-- TRENDS:BEGIN -->\n"
        "old content\n"
        "<!-- TRENDS:END -->\n\n"
        "## Other section\nkeep me\n"
    )

    runs = collect_runs(tmp_path / "bench")
    write_trends(
        runs,
        out_dir=tmp_path / "bench" / "_trends",
        readme_path=readme,
        benchmark_root=tmp_path / "bench",
    )

    text = readme.read_text()
    # block was replaced
    assert "old content" not in text
    # markers preserved
    assert "<!-- TRENDS:BEGIN -->" in text
    assert "<!-- TRENDS:END -->" in text
    # surrounding sections preserved
    assert "# Title" in text
    assert "keep me" in text
    # latest-run table is inside the block
    assert "case-a".replace("-", "") not in text  # sanity for the next assertion
    assert "| Case" in text
    # SVG image refs still present
    assert "pass_rate.svg" in text
    assert "latency.svg" in text
    assert "cost.svg" in text
