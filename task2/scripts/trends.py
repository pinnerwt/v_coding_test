from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REGRESSION_THRESHOLD_PP: int = 5

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
    passed_count: int = 0
    failed_count: int = 0
    usd_passed: float = 0.0
    usd_failed: float = 0.0
    p50_passed_ms: int = 0
    p50_failed_ms: int = 0
    p95_passed_ms: int = 0
    p95_failed_ms: int = 0


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = max(0, int((pct / 100) * len(sorted_vals) + 0.5) - 1)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def _is_passed(case: dict) -> bool:
    return case.get("status") in ("succeeded", "unverified")


def summarize_run(branch: str, data: dict) -> Run:
    cases = data.get("cases", [])
    non_skipped = [c for c in cases if c.get("status") != "skipped"]
    passed_cases = [c for c in non_skipped if _is_passed(c)]
    failed_cases = [c for c in non_skipped if not _is_passed(c)]
    total = len(non_skipped)
    pass_rate = len(passed_cases) / total if total else 0.0
    total_usd = sum(c.get("usd", 0.0) for c in non_skipped)
    total_tokens = sum(
        c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in non_skipped
    )
    latencies = [c.get("latency_ms_total", 0) for c in non_skipped]
    passed_lat = [c.get("latency_ms_total", 0) for c in passed_cases]
    failed_lat = [c.get("latency_ms_total", 0) for c in failed_cases]
    return Run(
        branch=branch,
        run_at=datetime.fromisoformat(data["run_at"]),
        pass_rate=pass_rate,
        total_usd=total_usd,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        total_tokens=total_tokens,
        total_cases=total,
        passed_count=len(passed_cases),
        failed_count=len(failed_cases),
        usd_passed=sum(c.get("usd", 0.0) for c in passed_cases),
        usd_failed=sum(c.get("usd", 0.0) for c in failed_cases),
        p50_passed_ms=_percentile(passed_lat, 50),
        p50_failed_ms=_percentile(failed_lat, 50),
        p95_passed_ms=_percentile(passed_lat, 95),
        p95_failed_ms=_percentile(failed_lat, 95),
    )


def _iter_run_data(benchmark_root: Path) -> list[tuple[str, dict, datetime]]:
    items: list[tuple[str, dict, datetime]] = []
    if not benchmark_root.exists():
        return items
    for d in benchmark_root.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        results = d / "results.json"
        if not results.exists():
            continue
        try:
            data = json.loads(results.read_text())
            run_at = datetime.fromisoformat(data["run_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        items.append((d.name, data, run_at))
    items.sort(key=lambda t: t[2])
    return items


def _failure_class_counts(data: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in data.get("cases", []):
        if _is_passed(case) or case.get("status") == "skipped":
            continue
        fc = case.get("failure_class")
        if fc is None:
            continue
        counts[fc] = counts.get(fc, 0) + 1
    return counts


def collect_failure_class_runs(benchmark_root: Path) -> list[dict[str, int]]:
    return [_failure_class_counts(data) for _, data, _ in _iter_run_data(benchmark_root)]


def collect_runs(benchmark_root: Path) -> list[Run]:
    return [summarize_run(branch, data) for branch, data, _ in _iter_run_data(benchmark_root)]


def flag_regression(runs: list[Run]) -> bool:
    if len(runs) <= 1:
        return False
    median = statistics.median(r.pass_rate for r in runs)
    return runs[-1].pass_rate < median - REGRESSION_THRESHOLD_PP / 100


# ---------------------------- SVG rendering ---------------------------- #

_W = 720
_H = 220
_PAD_L = 60
_PAD_R = 20
_PAD_T = 30
_PAD_B = 60
_BG_RECT = '<rect width="100%" height="100%" fill="#fff"/>'


def _empty_svg(title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}">'
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'<text x="{_W / 2}" y="{_H / 2}" text-anchor="middle" font-family="sans-serif" '
        f'font-size="14" fill="#000">{title}: no data</text>'
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
    parts.append(_BG_RECT)
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
            f'text-anchor="end" fill="#000">{label}</text>'
        )
        if frac > 0:
            parts.append(
                f'<line x1="{_PAD_L}" y1="{y}" x2="{_W - _PAD_R}" y2="{y}" '
                f'stroke="#eee" stroke-dasharray="2,2"/>'
            )

    parts.append(
        f'<text x="14" y="{_PAD_T + plot_h / 2}" font-size="11" fill="#000" '
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
            f'text-anchor="middle" fill="#000">{value_format(val)}</text>'
        )
        # branch label (truncated, rotated)
        label = _xml_escape(run.branch)
        if len(label) > 22:
            label = label[:21] + "…"
        cx = x + bar_w / 2
        parts.append(
            f'<text x="{cx:.2f}" y="{axis_y + 12}" font-size="10" fill="#000" '
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


_PASSED_COLOR = "#2ca02c"
_FAILED_COLOR = "#d62728"


def _grouped_bar_chart_svg(
    *,
    title: str,
    runs: list[Run],
    series: list[tuple[str, list[float], str]],
    y_label: str,
    value_format,
) -> str:
    if not runs or not series:
        return _empty_svg(title)

    n = len(runs)
    g = len(series)
    plot_w = _W - _PAD_L - _PAD_R
    plot_h = _H - _PAD_T - _PAD_B
    group_w = plot_w / n * 0.8
    bar_w = group_w / g
    gap = plot_w / n
    y_max = max((max(vals) for _, vals, _ in series if vals), default=0.0) or 1.0
    y_max *= 1.15

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}" font-family="sans-serif">'
    )
    parts.append(_BG_RECT)
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
            f'text-anchor="end" fill="#000">{label}</text>'
        )
        if frac > 0:
            parts.append(
                f'<line x1="{_PAD_L}" y1="{y}" x2="{_W - _PAD_R}" y2="{y}" '
                f'stroke="#eee" stroke-dasharray="2,2"/>'
            )

    parts.append(
        f'<text x="14" y="{_PAD_T + plot_h / 2}" font-size="11" fill="#000" '
        f'transform="rotate(-90 14 {_PAD_T + plot_h / 2})" text-anchor="middle">{y_label}</text>'
    )

    for i, run in enumerate(runs):
        group_x = _PAD_L + i * gap + (gap - group_w) / 2
        for j, (_label, vals, color) in enumerate(series):
            v = vals[i]
            h = (v / y_max * plot_h) if y_max else 0
            x = group_x + j * bar_w
            y = axis_y - h
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{h:.2f}" '
                f'fill="{color}"/>'
            )
            parts.append(
                f'<text x="{x + bar_w / 2:.2f}" y="{y - 4:.2f}" font-size="9" '
                f'text-anchor="middle" fill="#000">{value_format(v)}</text>'
            )
        # branch label below the group
        label = _xml_escape(run.branch)
        if len(label) > 22:
            label = label[:21] + "…"
        cx = group_x + group_w / 2
        parts.append(
            f'<text x="{cx:.2f}" y="{axis_y + 12}" font-size="10" fill="#000" '
            f'text-anchor="end" transform="rotate(-35 {cx:.2f} {axis_y + 12})">{label}</text>'
        )

    # legend
    lx = _W - _PAD_R - 140
    ly = _PAD_T - 4
    for j, (label, _, color) in enumerate(series):
        ox = lx + j * 70
        parts.append(f'<rect x="{ox}" y="{ly - 8}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{ox + 14}" y="{ly}" font-size="10" fill="#000">{label}</text>')

    parts.append("</svg>")
    return "".join(parts)


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
    norm_series = [(s[0], s[1], s[2], s[3] if len(s) > 3 else "") for s in series]
    y_max = max((max(vals) for _, vals, _, _ in norm_series if vals), default=0.0) or 1.0
    # round up a bit
    y_max = y_max * 1.15

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}" font-family="sans-serif">'
    )
    parts.append(_BG_RECT)
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
            f'text-anchor="end" fill="#000">{label}</text>'
        )
        if frac > 0:
            parts.append(
                f'<line x1="{_PAD_L}" y1="{y}" x2="{_W - _PAD_R}" y2="{y}" '
                f'stroke="#eee" stroke-dasharray="2,2"/>'
            )

    parts.append(
        f'<text x="14" y="{_PAD_T + plot_h / 2}" font-size="11" fill="#000" '
        f'transform="rotate(-90 14 {_PAD_T + plot_h / 2})" text-anchor="middle">{y_label}</text>'
    )

    def x_at(i: int) -> float:
        if n == 1:
            return _PAD_L + plot_w / 2
        return _PAD_L + (i / (n - 1)) * plot_w

    for _label, vals, color, dash in norm_series:
        if not vals:
            continue
        pts = " ".join(
            f"{x_at(i):.2f},{axis_y - (v / y_max) * plot_h:.2f}" for i, v in enumerate(vals)
        )
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"{dash_attr}/>'
        )
        for i, v in enumerate(vals):
            cx = x_at(i)
            cy = axis_y - (v / y_max) * plot_h
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="2.5" fill="{color}"/>')

    # legend
    entry_w = 75
    lx = _W - _PAD_R - entry_w * len(norm_series)
    ly = _PAD_T - 4
    for j, (label, _, color, dash) in enumerate(norm_series):
        ox = lx + j * entry_w
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{ox}" y1="{ly - 3}" x2="{ox + 16}" y2="{ly - 3}" '
            f'stroke="{color}" stroke-width="2"{dash_attr}/>'
        )
        parts.append(f'<text x="{ox + 20}" y="{ly}" font-size="10" fill="#000">{label}</text>')

    # x labels
    for i, run in enumerate(runs):
        label = _xml_escape(run.branch)
        if len(label) > 22:
            label = label[:21] + "…"
        cx = x_at(i)
        parts.append(
            f'<text x="{cx:.2f}" y="{axis_y + 12}" font-size="10" fill="#000" '
            f'text-anchor="end" transform="rotate(-35 {cx:.2f} {axis_y + 12})">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def render_latency_svg(runs: list[Run]) -> str:
    return _line_chart_svg(
        title="Latency by status (p50 solid, p95 dashed)",
        runs=runs,
        series=[
            ("p50 passed", [r.p50_passed_ms for r in runs], _PASSED_COLOR, ""),
            ("p95 passed", [r.p95_passed_ms for r in runs], _PASSED_COLOR, "4,3"),
            ("p50 failed", [r.p50_failed_ms for r in runs], _FAILED_COLOR, ""),
            ("p95 failed", [r.p95_failed_ms for r in runs], _FAILED_COLOR, "4,3"),
        ],
        y_label="ms",
        value_format=lambda v: f"{int(v)}",
    )


def render_cost_svg(runs: list[Run]) -> str:
    return _grouped_bar_chart_svg(
        title="Cost (USD) by status",
        runs=runs,
        series=[
            ("passed", [r.usd_passed for r in runs], _PASSED_COLOR),
            ("failed", [r.usd_failed for r in runs], _FAILED_COLOR),
        ],
        y_label="USD",
        value_format=lambda v: f"${v:.4f}",
    )


_FAILURE_CLASS_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
]


def render_failure_classes_svg(runs: list[Run], class_counts: list[dict[str, int]]) -> str:
    if not runs or not class_counts:
        return _empty_svg("Failure classes")

    all_classes = sorted({cls for counts in class_counts for cls in counts})
    if not all_classes:
        return _empty_svg("Failure classes")

    color_map = {
        cls: _FAILURE_CLASS_PALETTE[i % len(_FAILURE_CLASS_PALETTE)]
        for i, cls in enumerate(all_classes)
    }

    n = len(runs)
    plot_w = _W - _PAD_L - _PAD_R
    plot_h = _H - _PAD_T - _PAD_B
    axis_y = _PAD_T + plot_h
    y_max_raw = max((sum(c.values()) for c in class_counts), default=0) or 1
    y_max = y_max_raw * 1.15

    def x_at(i: int) -> float:
        if n == 1:
            return _PAD_L + plot_w / 2
        return _PAD_L + (i / (n - 1)) * plot_w

    def y_at(v: float) -> float:
        return axis_y - (v / y_max) * plot_h

    if n == 1:
        bar_half = plot_w * 0.15
        col_xs = [x_at(0) - bar_half, x_at(0) + bar_half]
        col_counts = [class_counts[0], class_counts[0]]
    else:
        col_xs = [x_at(i) for i in range(n)]
        col_counts = class_counts
    n_cols = len(col_xs)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}" '
        f'width="{_W}" height="{_H}" font-family="sans-serif">'
    )
    parts.append(_BG_RECT)
    parts.append(
        f'<text x="{_PAD_L}" y="18" font-size="13" font-weight="600">'
        f"Failure classes over time</text>"
    )

    parts.append(f'<line x1="{_PAD_L}" y1="{_PAD_T}" x2="{_PAD_L}" y2="{axis_y}" stroke="#999"/>')
    parts.append(
        f'<line x1="{_PAD_L}" y1="{axis_y}" x2="{_W - _PAD_R}" y2="{axis_y}" stroke="#999"/>'
    )

    for frac in (0.0, 0.5, 1.0):
        y = axis_y - frac * plot_h
        label = str(int(frac * y_max_raw))
        parts.append(
            f'<text x="{_PAD_L - 6}" y="{y + 4}" font-size="10" '
            f'text-anchor="end" fill="#000">{label}</text>'
        )
        if frac > 0:
            parts.append(
                f'<line x1="{_PAD_L}" y1="{y}" x2="{_W - _PAD_R}" y2="{y}" '
                f'stroke="#eee" stroke-dasharray="2,2"/>'
            )

    cum: list[float] = [0.0] * n_cols
    for cls in all_classes:
        color = color_map[cls]
        top_vals = [cum[i] + col_counts[i].get(cls, 0) for i in range(n_cols)]
        top_pts = " ".join(f"{col_xs[i]:.2f},{y_at(v):.2f}" for i, v in enumerate(top_vals))
        bottom_pts = " ".join(
            f"{col_xs[i]:.2f},{y_at(cum[i]):.2f}" for i in range(n_cols - 1, -1, -1)
        )
        parts.append(f'<polygon points="{top_pts} {bottom_pts}" fill="{color}" opacity="0.7"/>')
        parts.append(
            f'<polyline points="{top_pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        )
        cum = top_vals

    entry_w = max(90, plot_w // max(len(all_classes), 1))
    lx = _PAD_L
    ly = _H - 8
    for j, cls in enumerate(all_classes):
        ox = lx + j * entry_w
        color = color_map[cls]
        parts.append(f'<rect x="{ox}" y="{ly - 8}" width="10" height="10" fill="{color}"/>')
        parts.append(
            f'<text x="{ox + 14}" y="{ly}" font-size="10" fill="#000">{_xml_escape(cls)}</text>'
        )

    for i, run in enumerate(runs):
        label = _xml_escape(run.branch)
        if len(label) > 22:
            label = label[:21] + "…"
        cx = x_at(i)
        parts.append(
            f'<text x="{cx:.2f}" y="{axis_y + 12}" font-size="10" fill="#000" '
            f'text-anchor="end" transform="rotate(-35 {cx:.2f} {axis_y + 12})">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ---------------------------- latest-run table ---------------------------- #


def _fmt_latency(ms: int) -> str:
    if ms >= 1000:
        return f"{ms / 1000:.1f} s"
    return f"{ms} ms"


def render_latest_run_table(branch: str, data: dict) -> str:
    cases = [c for c in data.get("cases", []) if c.get("status") != "skipped"]
    run_at_iso = data.get("run_at", "")
    try:
        run_at = datetime.fromisoformat(run_at_iso)
        ts = run_at.strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        ts = run_at_iso

    lines: list[str] = [
        f"#### Latest run — `{branch}` ({ts})",
        "",
        "| Case | Status | Steps | Latency | Tokens | USD |",
        "|---|---|---:|---:|---:|---:|",
    ]
    total_steps = 0
    total_lat = 0
    total_tokens = 0
    total_usd = 0.0
    passed = 0
    for c in cases:
        status = c.get("status", "")
        steps = int(c.get("steps", 0) or 0)
        lat = int(c.get("latency_ms_total", 0) or 0)
        tokens = int(c.get("prompt_tokens", 0) or 0) + int(c.get("completion_tokens", 0) or 0)
        usd = float(c.get("usd", 0.0) or 0.0)
        if _is_passed(c):
            passed += 1
        total_steps += steps
        total_lat += lat
        total_tokens += tokens
        total_usd += usd
        lines.append(
            f"| `{c.get('id', '')}` | {status} | {steps} | {_fmt_latency(lat)} | "
            f"{tokens:,} | ${usd:.4f} |"
        )
    lines.append(
        f"| **Total ({len(cases)} cases, {passed} passed)** | | {total_steps} | "
        f"{_fmt_latency(total_lat)} | {total_tokens:,} | ${total_usd:.4f} |"
    )
    return "\n".join(lines)


# ---------------------------- file IO ---------------------------- #

_TRENDS_BEGIN = "<!-- TRENDS:BEGIN -->"
_TRENDS_END = "<!-- TRENDS:END -->"


def _latest_run_data(bench_root: Path) -> tuple[str, dict] | None:
    items = _iter_run_data(bench_root)
    if not items:
        return None
    branch, data, _ = items[-1]
    return branch, data


def _render_readme_block(latest: tuple[str, dict] | None, runs: list[Run]) -> str:
    body = [
        "### Basic benchmark",
        "",
        "![Pass rate over time](benchmark/_trends/pass_rate.svg)",
        "",
        "![Latency by status (p50 solid, p95 dashed)](benchmark/_trends/latency.svg)",
        "",
        "![Cost by status](benchmark/_trends/cost.svg)",
        "",
        "![Failure classes over time](benchmark/_trends/failure_classes.svg)",
        "",
        (
            "Cost and latency are split into passed vs. failed cases: a failing "
            "case bails out early, so a higher pass rate naturally raises totals. "
            "Compare the green (passed) and red (failed) series within a branch, "
            "not the totals across branches."
        ),
    ]
    if latest is not None:
        branch, data = latest
        if flag_regression(runs):
            body.extend(
                [
                    "",
                    "> ⚠️ **Pass-rate regression detected**"
                    " — latest run is >5 pp below the historical median."
                    " See `benchmark/_trends/regression_onset.md`"
                    " for per-case onset branches.",
                ]
            )
        body.extend(["", render_latest_run_table(branch, data)])
    return "\n".join(body)


def _update_readme(readme_path: Path, block: str) -> None:
    if not readme_path.exists():
        return
    text = readme_path.read_text()
    begin = text.find(_TRENDS_BEGIN)
    end = text.find(_TRENDS_END)
    if begin == -1 or end == -1 or end < begin:
        return
    new_text = text[: begin + len(_TRENDS_BEGIN)] + "\n" + block + "\n" + text[end:]
    if new_text != text:
        readme_path.write_text(new_text)


def write_trends(
    runs: list[Run],
    *,
    out_dir: Path,
    readme_path: Path | None = None,
    benchmark_root: Path | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pass_rate.svg").write_text(render_pass_rate_svg(runs))
    (out_dir / "latency.svg").write_text(render_latency_svg(runs))
    (out_dir / "cost.svg").write_text(render_cost_svg(runs))
    class_counts = collect_failure_class_runs(benchmark_root) if benchmark_root is not None else []
    (out_dir / "failure_classes.svg").write_text(render_failure_classes_svg(runs, class_counts))

    if readme_path is not None:
        latest = _latest_run_data(benchmark_root) if benchmark_root is not None else None
        _update_readme(readme_path, _render_readme_block(latest, runs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render benchmark trend charts")
    parser.add_argument("--benchmark-root", default=str(_BENCHMARK_ROOT))
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args(argv)

    bench_root = Path(args.benchmark_root)
    runs = collect_runs(bench_root)
    out_dir = bench_root / _TRENDS_SUBDIR
    readme_path = Path(args.readme) if args.readme else None
    write_trends(runs, out_dir=out_dir, readme_path=readme_path, benchmark_root=bench_root)

    print(f"wrote trends for {len(runs)} runs to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
