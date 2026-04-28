from __future__ import annotations

from typing import Literal

from scripts.eval import PASS_STATUSES

CaseDelta = Literal["regression", "improvement", "unchanged", "new", "dropped"]


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    sv = sorted(values)
    idx = max(0, int((pct / 100) * len(sv) + 0.5) - 1)
    return sv[min(idx, len(sv) - 1)]


def _classify(master_status: str | None, branch_status: str | None) -> CaseDelta:
    if master_status is None:
        return "new"
    if branch_status is None:
        return "dropped"
    m_pass = master_status in PASS_STATUSES
    b_pass = branch_status in PASS_STATUSES
    if m_pass and not b_pass:
        return "regression"
    if not m_pass and b_pass:
        return "improvement"
    return "unchanged"


def _pass_count(cases: list[dict]) -> int:
    return sum(1 for c in cases if c.get("status") in PASS_STATUSES)


def _fmt_signed(val: float, fmt: str = ".0f") -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:{fmt}}"


def generate_diff_markdown(master: dict, branch: dict) -> str:
    master_cases: dict[str, dict] = {c["id"]: c for c in master.get("cases", [])}
    branch_cases: dict[str, dict] = {c["id"]: c for c in branch.get("cases", [])}
    all_ids = sorted(set(master_cases) | set(branch_cases))

    lines: list[str] = [
        "## Δ vs master",
        "",
        f"Master run: {master.get('run_at', 'unknown')}",
        f"Branch run: {branch.get('run_at', 'unknown')}",
        "",
        "| Case | Master status | Branch status | Delta |",
        "|---|---|---|---|",
    ]

    for cid in all_ids:
        mc = master_cases.get(cid)
        bc = branch_cases.get(cid)
        ms = mc["status"] if mc else None
        bs = bc["status"] if bc else None
        delta = _classify(ms, bs)
        if delta == "regression":
            delta_cell = "⚠️ REGRESSION"
        elif delta == "improvement":
            delta_cell = "✅ IMPROVEMENT"
        else:
            delta_cell = delta
        lines.append(f"| {cid} | {ms or '—'} | {bs or '—'} | {delta_cell} |")

    lines.append("")

    m_list = list(master_cases.values())
    b_list = list(branch_cases.values())

    m_ran = len(m_list)
    b_ran = len(b_list)
    m_pct = int(100 * _pass_count(m_list) / m_ran) if m_ran else 0
    b_pct = int(100 * _pass_count(b_list) / b_ran) if b_ran else 0

    m_usd = sum(c.get("usd", 0.0) for c in m_list)
    b_usd = sum(c.get("usd", 0.0) for c in b_list)
    delta_usd = b_usd - m_usd

    m_lat = [c.get("latency_ms_total", 0) for c in m_list]
    b_lat = [c.get("latency_ms_total", 0) for c in b_list]

    sign_usd = "+" if delta_usd >= 0 else "-"
    lines.append(f"Δ pass-rate: {_fmt_signed(b_pct - m_pct)}%")
    lines.append(f"Δ total USD: {sign_usd}${abs(delta_usd):.4f}")
    lines.append(f"Δ p50 latency: {_fmt_signed(_percentile(b_lat, 50) - _percentile(m_lat, 50))}ms")
    lines.append(f"Δ p95 latency: {_fmt_signed(_percentile(b_lat, 95) - _percentile(m_lat, 95))}ms")
    lines.append("")

    return "\n".join(lines)
