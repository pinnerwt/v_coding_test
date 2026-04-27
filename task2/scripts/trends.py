from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_BENCHMARK_ROOT = Path("benchmark")
_TRENDS_SUBDIR = "_trends"


@dataclass(frozen=True)
class Run:
    branch: str
    run_at: datetime
    pass_rate: float
    total_usd: float
    p50_ms: int
    p95_ms: int
    total_tokens: int
    total_cases: int


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = max(0, int((pct / 100) * len(sorted_vals) + 0.5) - 1)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def summarize_run(branch: str, data: dict) -> Run:
    cases = data.get("cases", [])
    non_skipped = [c for c in cases if c.get("status") != "skipped"]
    passed = sum(1 for c in non_skipped if c.get("status") in ("succeeded", "unverified"))
    total = len(non_skipped)
    pass_rate = passed / total if total else 0.0
    total_usd = sum(c.get("usd", 0.0) for c in non_skipped)
    total_tokens = sum(
        c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in non_skipped
    )
    latencies = [c.get("latency_ms_total", 0) for c in non_skipped]
    return Run(
        branch=branch,
        run_at=datetime.fromisoformat(data["run_at"]),
        pass_rate=pass_rate,
        total_usd=total_usd,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        total_tokens=total_tokens,
        total_cases=total,
    )


def collect_runs(benchmark_root: Path) -> list[Run]:
    runs: list[Run] = []
    if not benchmark_root.exists():
        return runs
    for d in benchmark_root.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        results = d / "results.json"
        if not results.exists():
            continue
        try:
            data = json.loads(results.read_text())
            runs.append(summarize_run(d.name, data))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    runs.sort(key=lambda r: r.run_at)
    return runs


# ---------------------------- SVG rendering ---------------------------- #

_W = 720
_H = 220
_PAD_L = 60
_PAD_R = 20
_PAD_T = 30
_PAD_B = 60


def _empty_svg(title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}">'
        f'<text x="{_W / 2}" y="{_H / 2}" text-anchor="middle" font-family="sans-serif" '
        f'font-size="14" fill="#666">{title}: no data</text>'
        "</svg>"
    )


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bar_chart_svg(
    *,
    title: str,
    runs: list[Run],
    values: list[float],
    y_max: float,
    y_label: str,
    value_format,
    color: str,
) -> str:
    if not runs:
        return _empty_svg(title)

    n = len(runs)
    plot_w = _W - _PAD_L - _PAD_R
    plot_h = _H - _PAD_T - _PAD_B
    bar_w = plot_w / n * 0.7
    gap = plot_w / n

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}" font-family="sans-serif">'
    )
    parts.append(f'<text x="{_PAD_L}" y="18" font-size="13" font-weight="600">{title}</text>')

    # axes
    axis_y = _PAD_T + plot_h
    parts.append(f'<line x1="{_PAD_L}" y1="{_PAD_T}" x2="{_PAD_L}" y2="{axis_y}" stroke="#999"/>')
    parts.append(
        f'<line x1="{_PAD_L}" y1="{axis_y}" x2="{_W - _PAD_R}" y2="{axis_y}" stroke="#999"/>'
    )

    # y ticks (3 levels)
    for frac in (0.0, 0.5, 1.0):
        y = axis_y - frac * plot_h
        label = value_format(frac * y_max) if y_max else "0"
        parts.append(f'<line x1="{_PAD_L - 3}" y1="{y}" x2="{_PAD_L}" y2="{y}" stroke="#999"/>')
        parts.append(
            f'<text x="{_PAD_L - 6}" y="{y + 4}" font-size="10" '
            f'text-anchor="end" fill="#444">{label}</text>'
        )
        if frac > 0:
            parts.append(
                f'<line x1="{_PAD_L}" y1="{y}" x2="{_W - _PAD_R}" y2="{y}" '
                f'stroke="#eee" stroke-dasharray="2,2"/>'
            )

    parts.append(
        f'<text x="14" y="{_PAD_T + plot_h / 2}" font-size="11" fill="#444" '
        f'transform="rotate(-90 14 {_PAD_T + plot_h / 2})" text-anchor="middle">{y_label}</text>'
    )

    # bars + x labels
    for i, (run, val) in enumerate(zip(runs, values, strict=True)):
        h = (val / y_max * plot_h) if y_max else 0
        x = _PAD_L + i * gap + (gap - bar_w) / 2
        y = axis_y - h
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{h:.2f}" fill="{color}"/>'
        )
        # value above bar
        parts.append(
            f'<text x="{x + bar_w / 2:.2f}" y="{y - 4:.2f}" font-size="10" '
            f'text-anchor="middle" fill="#222">{value_format(val)}</text>'
        )
        # branch label (truncated, rotated)
        label = _xml_escape(run.branch)
        if len(label) > 22:
            label = label[:21] + "…"
        cx = x + bar_w / 2
        parts.append(
            f'<text x="{cx:.2f}" y="{axis_y + 12}" font-size="10" fill="#333" '
            f'text-anchor="end" transform="rotate(-35 {cx:.2f} {axis_y + 12})">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def render_pass_rate_svg(runs: list[Run]) -> str:
    return _bar_chart_svg(
        title="Pass rate over time",
        runs=runs,
        values=[r.pass_rate * 100 for r in runs],
        y_max=100.0,
        y_label="pass %",
        value_format=lambda v: f"{v:.0f}%",
        color="#2ca02c",
    )


def _line_chart_svg(
    *,
    title: str,
    runs: list[Run],
    series: list[tuple[str, list[float], str]],
    y_label: str,
    value_format,
) -> str:
    if not runs:
        return _empty_svg(title)

    n = len(runs)
    plot_w = _W - _PAD_L - _PAD_R
    plot_h = _H - _PAD_T - _PAD_B
    y_max = max((max(vals) for _, vals, _ in series if vals), default=0.0) or 1.0
    # round up a bit
    y_max = y_max * 1.15

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}" font-family="sans-serif">'
    )
    parts.append(f'<text x="{_PAD_L}" y="18" font-size="13" font-weight="600">{title}</text>')

    axis_y = _PAD_T + plot_h
    parts.append(f'<line x1="{_PAD_L}" y1="{_PAD_T}" x2="{_PAD_L}" y2="{axis_y}" stroke="#999"/>')
    parts.append(
        f'<line x1="{_PAD_L}" y1="{axis_y}" x2="{_W - _PAD_R}" y2="{axis_y}" stroke="#999"/>'
    )

    for frac in (0.0, 0.5, 1.0):
        y = axis_y - frac * plot_h
        label = value_format(frac * y_max)
        parts.append(
            f'<text x="{_PAD_L - 6}" y="{y + 4}" font-size="10" '
            f'text-anchor="end" fill="#444">{label}</text>'
        )
        if frac > 0:
            parts.append(
                f'<line x1="{_PAD_L}" y1="{y}" x2="{_W - _PAD_R}" y2="{y}" '
                f'stroke="#eee" stroke-dasharray="2,2"/>'
            )

    parts.append(
        f'<text x="14" y="{_PAD_T + plot_h / 2}" font-size="11" fill="#444" '
        f'transform="rotate(-90 14 {_PAD_T + plot_h / 2})" text-anchor="middle">{y_label}</text>'
    )

    def x_at(i: int) -> float:
        if n == 1:
            return _PAD_L + plot_w / 2
        return _PAD_L + (i / (n - 1)) * plot_w

    for _label, vals, color in series:
        if not vals:
            continue
        pts = " ".join(
            f"{x_at(i):.2f},{axis_y - (v / y_max) * plot_h:.2f}" for i, v in enumerate(vals)
        )
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
        for i, v in enumerate(vals):
            cx = x_at(i)
            cy = axis_y - (v / y_max) * plot_h
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="2.5" fill="{color}"/>')

    # legend
    lx = _W - _PAD_R - 120
    ly = _PAD_T - 4
    for j, (label, _, color) in enumerate(series):
        ox = lx + j * 70
        parts.append(f'<rect x="{ox}" y="{ly - 8}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{ox + 14}" y="{ly}" font-size="10" fill="#333">{label}</text>')

    # x labels
    for i, run in enumerate(runs):
        label = _xml_escape(run.branch)
        if len(label) > 22:
            label = label[:21] + "…"
        cx = x_at(i)
        parts.append(
            f'<text x="{cx:.2f}" y="{axis_y + 12}" font-size="10" fill="#333" '
            f'text-anchor="end" transform="rotate(-35 {cx:.2f} {axis_y + 12})">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def render_latency_svg(runs: list[Run]) -> str:
    return _line_chart_svg(
        title="Latency over time",
        runs=runs,
        series=[
            ("p50", [r.p50_ms for r in runs], "#1f77b4"),
            ("p95", [r.p95_ms for r in runs], "#d62728"),
        ],
        y_label="ms",
        value_format=lambda v: f"{int(v)}",
    )


def render_cost_svg(runs: list[Run]) -> str:
    if not runs:
        return _empty_svg("Cost & tokens over time")
    y_max_usd = max(r.total_usd for r in runs) or 1.0
    return _bar_chart_svg(
        title="Cost (USD) per run",
        runs=runs,
        values=[r.total_usd for r in runs],
        y_max=y_max_usd * 1.15,
        y_label="USD",
        value_format=lambda v: f"${v:.4f}",
        color="#ff7f0e",
    )


# ---------------------------- file IO ---------------------------- #


def write_trends(runs: list[Run], *, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pass_rate.svg").write_text(render_pass_rate_svg(runs))
    (out_dir / "latency.svg").write_text(render_latency_svg(runs))
    (out_dir / "cost.svg").write_text(render_cost_svg(runs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render benchmark trend charts")
    parser.add_argument("--benchmark-root", default=str(_BENCHMARK_ROOT))
    args = parser.parse_args(argv)

    bench_root = Path(args.benchmark_root)
    runs = collect_runs(bench_root)
    out_dir = bench_root / _TRENDS_SUBDIR
    write_trends(runs, out_dir=out_dir)

    print(f"wrote trends for {len(runs)} runs to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
