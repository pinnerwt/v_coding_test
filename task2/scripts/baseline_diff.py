from __future__ import annotations

from typing import Literal, get_args

CaseDelta = Literal["regression", "improvement", "unchanged", "new", "dropped"]
_VALID_DELTAS: frozenset[str] = frozenset(get_args(CaseDelta))

_PASS_STATUSES = frozenset({"succeeded", "unverified"})
_FAIL_STATUSES = frozenset({"failed", "skipped"})


def _classify(master_status: str | None, branch_status: str | None) -> CaseDelta:
    if master_status is None:
        return "new"
    if branch_status is None:
        return "dropped"
    m_pass = master_status in _PASS_STATUSES
    b_pass = branch_status in _PASS_STATUSES
    if m_pass and not b_pass:
        return "regression"
    if not m_pass and b_pass:
        return "improvement"
    return "unchanged"


def _pass_count(cases: list[dict]) -> int:
    return sum(1 for c in cases if c.get("status") in _PASS_STATUSES)


def _ran_count(cases: list[dict]) -> int:
    return len(cases)


def _total_usd(cases: list[dict]) -> float:
    return sum(c.get("usd", 0.0) for c in cases)


def _latencies(cases: list[dict]) -> list[int]:
    return [c.get("latency_ms_total", 0) for c in cases]


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    sv = sorted(values)
    idx = max(0, int((pct / 100) * len(sv) + 0.5) - 1)
    return sv[min(idx, len(sv) - 1)]


def _fmt_signed(val: float, fmt: str = ".0f") -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:{fmt}}"


def generate_diff_markdown(master: dict, branch: dict) -> str:
    master_cases: dict[str, dict] = {c["id"]: c for c in master.get("cases", [])}
    branch_cases: dict[str, dict] = {c["id"]: c for c in branch.get("cases", [])}
    all_ids = list(master_cases) + [k for k in branch_cases if k not in master_cases]

    lines: list[str] = []
    lines.append("## Δ vs master")
    lines.append("")
    lines.append(f"Master run: {master.get('run_at', 'unknown')}")
    lines.append(f"Branch run: {branch.get('run_at', 'unknown')}")
    lines.append("")

    lines.append("| Case | Master status | Branch status | Delta |")
    lines.append("|---|---|---|---|")

    for cid in all_ids:
        mc = master_cases.get(cid)
        bc = branch_cases.get(cid)
        ms = mc["status"] if mc else "—"
        bs = bc["status"] if bc else "—"
        delta = _classify(mc["status"] if mc else None, bc["status"] if bc else None)
        if delta == "regression":
            delta_cell = "⚠️ REGRESSION"
        elif delta == "improvement":
            delta_cell = "✅ IMPROVEMENT"
        else:
            delta_cell = delta
        lines.append(f"| {cid} | {ms} | {bs} | {delta_cell} |")

    lines.append("")

    m_list = list(master_cases.values())
    b_list = list(branch_cases.values())

    m_ran = _ran_count(m_list)
    b_ran = _ran_count(b_list)
    m_pass = _pass_count(m_list)
    b_pass = _pass_count(b_list)

    m_pct = int(100 * m_pass / m_ran) if m_ran else 0
    b_pct = int(100 * b_pass / b_ran) if b_ran else 0
    delta_pct = b_pct - m_pct

    m_usd = _total_usd(m_list)
    b_usd = _total_usd(b_list)
    delta_usd = b_usd - m_usd

    m_lat = _latencies(m_list)
    b_lat = _latencies(b_list)
    m_p50 = _percentile(m_lat, 50)
    b_p50 = _percentile(b_lat, 50)
    m_p95 = _percentile(m_lat, 95)
    b_p95 = _percentile(b_lat, 95)

    lines.append(f"Δ pass-rate: {_fmt_signed(delta_pct)}%")
    usd_str = _fmt_signed(delta_usd, ".4f").replace("+", "+$").replace("-", "-$")
    lines.append(f"Δ total USD: {usd_str}")
    lines.append(f"Δ p50 latency: {_fmt_signed(b_p50 - m_p50)}ms")
    lines.append(f"Δ p95 latency: {_fmt_signed(b_p95 - m_p95)}ms")
    lines.append("")

    return "\n".join(lines)
