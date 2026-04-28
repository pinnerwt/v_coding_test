from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_PASSING = frozenset({"succeeded", "unverified"})
_NON_FAILING = frozenset({"succeeded", "unverified", "skipped"})


def _collect_case_history(benchmark_root: Path) -> list[tuple[str, str, dict]]:
    runs: list[tuple[datetime, str, dict]] = []
    if not benchmark_root.exists():
        return []
    for d in benchmark_root.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        rj = d / "results.json"
        if not rj.exists():
            continue
        try:
            data = json.loads(rj.read_text())
            run_at = datetime.fromisoformat(data["run_at"])
            runs.append((run_at, d.name, data))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    runs.sort(key=lambda t: t[0])
    return [(branch, data["run_at"], data) for _, branch, data in runs]


def _classify_cases(
    runs: list[tuple[str, str, dict]],
) -> tuple[list[dict], list[dict], list[dict]]:
    last_pass: dict[str, str] = {}
    first_seen: dict[str, str] = {}
    seen_count: dict[str, int] = {}
    regressions: dict[str, dict] = {}
    ever_passed: set[str] = set()
    ever_failed: set[str] = set()

    for branch, run_at, data in runs:
        for case in data.get("cases", []):
            cid = case.get("id", "")
            status = case.get("status", "")
            if not cid:
                continue
            if cid not in first_seen:
                first_seen[cid] = branch
                seen_count[cid] = 0
            seen_count[cid] += 1
            if status in _PASSING:
                ever_passed.add(cid)
                last_pass[cid] = branch
            elif status not in _NON_FAILING:
                ever_failed.add(cid)
                if cid not in regressions and cid in ever_passed:
                    regressions[cid] = {
                        "case": cid,
                        "onset_branch": branch,
                        "onset_run_at": run_at,
                        "prior_passing": last_pass[cid],
                    }

    never_passed: set[str] = set()
    stable: set[str] = set()
    for cid in first_seen:
        if cid in regressions:
            continue
        if cid in ever_failed and cid not in ever_passed:
            never_passed.add(cid)
        else:
            stable.add(cid)

    reg_rows = sorted(regressions.values(), key=lambda r: r["case"])
    np_rows = sorted(
        (
            {"case": cid, "first_seen": first_seen[cid], "total_runs": seen_count[cid]}
            for cid in never_passed
        ),
        key=lambda r: r["case"],
    )
    stable_rows = sorted(
        (
            {"case": cid, "status": "always passing" if cid in ever_passed else "always skipped"}
            for cid in stable
        ),
        key=lambda r: r["case"],
    )
    return reg_rows, np_rows, stable_rows


def write_report(
    reg_rows: list[dict],
    np_rows: list[dict],
    stable_rows: list[dict],
    output_path: Path,
    benchmark_root: Path,
) -> None:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    lines: list[str] = [
        "# Regression Onset Report",
        "",
        f"Generated: {ts}",
        f"Benchmark root: {benchmark_root}",
        "",
        "Branch names map to git branches via 'git log --oneline <branch> -1'.",
        "",
        "Regenerate: `cd task2 && uv run python -m scripts.regression_onset"
        " --benchmark-root benchmark`",
        "",
        "## Regressions",
        "",
        "| Case | Onset Branch | Onset run_at | Prior passing branch |",
        "|---|---|---|---|",
    ]
    for r in reg_rows:
        lines.append(
            f"| {r['case']} | {r['onset_branch']} | {r['onset_run_at']} | {r['prior_passing']} |"
        )
    lines += [
        "",
        "## Never Passed",
        "",
        "| Case | First seen | Total runs seen |",
        "|---|---|---|",
    ]
    for r in np_rows:
        lines.append(f"| {r['case']} | {r['first_seen']} | {r['total_runs']} |")
    lines += [
        "",
        "## Stable",
        "",
        "| Case | Status |",
        "|---|---|",
    ]
    for r in stable_rows:
        lines.append(f"| {r['case']} | {r['status']} |")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regression onset report")
    parser.add_argument("--benchmark-root", default="benchmark")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    benchmark_root = Path(args.benchmark_root)
    output_path = (
        Path(args.output) if args.output else benchmark_root / "_trends" / "regression_onset.md"
    )

    try:
        runs = _collect_case_history(benchmark_root)
        reg_rows, np_rows, stable_rows = _classify_cases(runs)
        write_report(reg_rows, np_rows, stable_rows, output_path, benchmark_root)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"wrote regression_onset.md: {len(reg_rows)} regression(s),"
        f" {len(np_rows)} never-passed, {len(stable_rows)} stable"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
