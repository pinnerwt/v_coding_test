from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from scripts.trends import (
    Run,
    render_cost_svg,
    render_failure_classes_svg,
    render_latency_svg,
    render_latest_run_table,
    render_pass_rate_svg,
    summarize_run,
)

_BENCHMARK_ROOT = Path("benchmark")
_TRENDS_SUBDIR = "_webvoyager_trends"
_README_BEGIN = "<!-- WEBVOYAGER_TRENDS:BEGIN -->"
_README_END = "<!-- WEBVOYAGER_TRENDS:END -->"


def iter_webvoyager_runs(benchmark_root: Path) -> list[tuple[str, dict, datetime]]:
    items: list[tuple[str, dict, datetime]] = []
    if not benchmark_root.exists():
        return items
    for branch_dir in benchmark_root.iterdir():
        if not branch_dir.is_dir() or branch_dir.name.startswith("_"):
            continue
        wv_dir = branch_dir / "webvoyager"
        if not wv_dir.is_dir():
            continue
        latest: tuple[dict, datetime] | None = None
        for json_file in wv_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text())
                run_at = datetime.fromisoformat(data["run_at"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if latest is None or run_at > latest[1]:
                latest = (data, run_at)
        if latest is not None:
            items.append((branch_dir.name, latest[0], latest[1]))
    items.sort(key=lambda t: t[2])
    return items


def _failure_class_counts(data: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in data.get("cases", []):
        if case.get("status") in ("succeeded", "unverified", "skipped"):
            continue
        fc = case.get("failure_class")
        if fc is None:
            continue
        counts[fc] = counts.get(fc, 0) + 1
    return counts


def _render_readme_block(latest: tuple[str, dict] | None) -> str:
    body = [
        "### WebVoyager trends",
        "",
        "![Pass rate over time](benchmark/_webvoyager_trends/pass_rate.svg)",
        "",
        "![Latency by status (p50 solid, p95 dashed)](benchmark/_webvoyager_trends/latency.svg)",
        "",
        "![Cost by status](benchmark/_webvoyager_trends/cost.svg)",
        "",
        "![Failure classes over time](benchmark/_webvoyager_trends/failure_classes.svg)",
        "",
        (
            "Each branch contributes its most recent WebVoyager run "
            "(`benchmark/<branch>/webvoyager/<timestamp>.json`). Pass-rate, latency, and "
            "cost are split into passed vs. failed cases; failure-class counts come from "
            "the `failure_class` field on each non-passed case."
        ),
    ]
    if latest is not None:
        branch, data = latest
        body.extend(["", render_latest_run_table(branch, data)])
    return "\n".join(body)


def _update_readme(readme_path: Path, block: str) -> None:
    if not readme_path.exists():
        return
    text = readme_path.read_text()
    begin = text.find(_README_BEGIN)
    end = text.find(_README_END)
    if begin == -1 or end == -1 or end < begin:
        return
    new_text = text[: begin + len(_README_BEGIN)] + "\n" + block + "\n" + text[end:]
    if new_text != text:
        readme_path.write_text(new_text)


def write_webvoyager_trends(*, benchmark_root: Path, readme_path: Path | None) -> None:
    items = iter_webvoyager_runs(benchmark_root)
    runs: list[Run] = [summarize_run(branch, data) for branch, data, _ in items]
    class_counts = [_failure_class_counts(data) for _, data, _ in items]

    out_dir = benchmark_root / _TRENDS_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pass_rate.svg").write_text(render_pass_rate_svg(runs))
    (out_dir / "latency.svg").write_text(render_latency_svg(runs))
    (out_dir / "cost.svg").write_text(render_cost_svg(runs))
    (out_dir / "failure_classes.svg").write_text(render_failure_classes_svg(runs, class_counts))

    if readme_path is not None:
        latest = (items[-1][0], items[-1][1]) if items else None
        _update_readme(readme_path, _render_readme_block(latest))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render WebVoyager trend charts")
    parser.add_argument("--benchmark-root", default=str(_BENCHMARK_ROOT))
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args(argv)

    bench_root = Path(args.benchmark_root)
    readme_path = Path(args.readme) if args.readme else None
    write_webvoyager_trends(benchmark_root=bench_root, readme_path=readme_path)

    items = iter_webvoyager_runs(bench_root)
    print(f"wrote webvoyager trends for {len(items)} runs to {bench_root / _TRENDS_SUBDIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
