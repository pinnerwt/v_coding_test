from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.baseline_diff import generate_diff_markdown

_SKIP_REASON_ORDER = [
    "live_disabled",
    "infra_unavailable",
    "fixture_missing",
    "feature_not_implemented",
]

SUITE_THRESHOLDS: dict[str, dict] = {
    "drift": {
        "name": "Drift suite",
        "id_prefixes": ["drift-", "maintenance-drift-", "correction-"],
        "target_pct": 100,
    },
    "fixture": {
        "name": "Fixture",
        "id_prefixes": ["fixture-"],
        "target_pct": 80,
    },
    "live": {
        "name": "Live",
        "id_prefixes": ["live-"],
        "target_pct": 60,
    },
}


def _render_step_breakdown(steps: list[dict]) -> str:
    if not steps:
        return ""
    header = "| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |"
    sep = "|---|---|---|---|---|"
    rows = [header, sep]
    for step in steps:
        tool = ", ".join(step.get("tool_calls") or []) or "-"
        rows.append(
            f"| {step['step']} | {tool}"
            f" | {step.get('prompt_tokens', 0)}"
            f" | {step.get('completion_tokens', 0)}"
            f" | {step.get('latency_ms', 0)} |"
        )
    return "\n".join(rows)


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = max(0, int((pct / 100) * len(sorted_vals) + 0.5) - 1)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def _bucket_cases_by_suite(cases: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {key: [] for key in SUITE_THRESHOLDS}
    for case in cases:
        cid = case.get("id", "")
        for suite_key, suite in SUITE_THRESHOLDS.items():
            if any(cid.startswith(prefix) for prefix in suite["id_prefixes"]):
                buckets[suite_key].append(case)
                break
    return buckets


def _render_case_status(case: dict) -> str:
    if case.get("repeat_status") == "skipped":
        return case.get("status", "skipped")
    repeats = case.get("repeats", 1)
    if repeats > 1:
        passed_runs = case.get("passed_runs", 0)
        glyph = "✓" if passed_runs == repeats else "✗"
        return f"{passed_runs}/{repeats} {glyph}"
    return case.get("status", "unknown")


def generate_scoreboard(data: dict, *, detail: bool = False) -> str:
    cases = data.get("cases", [])
    run_at = data.get("run_at", "unknown")

    lines: list[str] = []
    lines.append(f"Generated from eval run: {run_at}")
    lines.append("")

    buckets = _bucket_cases_by_suite(cases)
    for suite_key, suite in SUITE_THRESHOLDS.items():
        suite_cases = buckets[suite_key]
        name = suite["name"]
        target_pct = suite["target_pct"]
        ran = len([c for c in suite_cases if c.get("status") != "skipped"])
        passed = len([c for c in suite_cases if c.get("status") in ("succeeded", "unverified")])
        if ran == 0:
            lines.append(f"{name}: 0/0 ran [target {target_pct}%] ⏭️")
        else:
            pct = int(100 * passed / ran)
            glyph = "✅" if pct >= target_pct else "❌"
            lines.append(f"{name}: {passed}/{ran} ({pct}%) [target {target_pct}%] {glyph}")
    lines.append("")

    lines.append(
        "| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) "
        "| Escalations | Replans | Cache Inv. | Failure class |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    non_skipped = []
    total_usd = 0.0
    total_prompt = 0
    total_completion = 0
    tier_counts: dict[str, int] = {}

    for case in cases:
        status = _render_case_status(case)
        steps = case.get("steps", 0)
        lat = case.get("latency_ms_total", 0)
        usd = case.get("usd", 0.0)
        prompt = case.get("prompt_tokens", 0)
        completion = case.get("completion_tokens", 0)
        cid = case.get("id", "?")
        esc_count = len(case.get("escalations", []))
        replan_count = case.get("replans", 0)
        cache_inv = case.get("cache_events", {}).get("invalidations", 0)
        fc = case.get("failure_class") or "-"

        lines.append(
            f"| {cid} | {status} | {steps} | {lat} | ${usd:.4f} | {prompt}+{completion}"
            f" | {esc_count} | {replan_count} | {cache_inv} | {fc} |"
        )

        raw_status = case.get("status", "unknown")
        is_failing = raw_status not in ("succeeded", "unverified", "skipped")
        steps_data = case.get("step_breakdown") or []
        if is_failing and steps_data:
            table = _render_step_breakdown(steps_data)
            lines.append("")
            if detail:
                lines.append(table)
            else:
                lines.append(
                    f"<details><summary>step breakdown ({len(steps_data)} steps)</summary>"
                )
                lines.append("")
                lines.append(table)
                lines.append("")
                lines.append("</details>")

        if status != "skipped":
            non_skipped.append(case)
            total_usd += usd
            total_prompt += prompt
            total_completion += completion

        for tier, count in case.get("l_tier_counts", {}).items():
            tier_counts[tier] = tier_counts.get(tier, 0) + count

    lines.append("")

    skip_reason_counts: dict[str, int] = {}
    for case in cases:
        reason = case.get("skip_reason")
        if reason is not None:
            skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
    if skip_reason_counts:
        total_skipped = sum(skip_reason_counts.values())
        lines.append(f"**Skipped** ({total_skipped} cases)")
        lines.append("")
        lines.append("| Skip reason | Count |")
        lines.append("|---|---|")
        for reason in _SKIP_REASON_ORDER:
            if reason in skip_reason_counts:
                lines.append(f"| {reason} | {skip_reason_counts[reason]} |")
        lines.append("")

    passed = sum(1 for c in non_skipped if c.get("status") in ("succeeded", "unverified"))
    total = len(non_skipped)
    pct = int(100 * passed / total) if total > 0 else 0
    lines.append(f"**{passed}/{total} succeeded ({pct}%)**")
    lines.append("")

    latencies = [c.get("latency_ms_total", 0) for c in non_skipped]
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    lines.append(f"p50: {p50}ms  p95: {p95}ms")
    lines.append("")

    token_summary = f"{total_prompt} prompt + {total_completion} completion"
    lines.append(f"Total USD: ${total_usd:.4f}   Total tokens: {token_summary}")
    lines.append("")

    lines.append("| Tier | Count |")
    lines.append("|---|---|")
    if tier_counts:
        for tier, count in sorted(tier_counts.items()):
            lines.append(f"| {tier} | {count} |")
    else:
        lines.append("| (none) | 0 |")

    lines.append("")

    esc_with_firing = sum(1 for c in non_skipped if len(c.get("escalations", [])) >= 1)
    replan_with_firing = sum(1 for c in non_skipped if c.get("replans", 0) >= 1)
    cache_inv_with_firing = sum(
        1 for c in non_skipped if c.get("cache_events", {}).get("invalidations", 0) >= 1
    )
    lines.append("**Mechanism firing rates**")
    lines.append("")
    lines.append("| Mechanism | Cases with ≥1 firing |")
    lines.append("|---|---|")
    lines.append(f"| L1→L2 escalation | {esc_with_firing}/{total} |")
    lines.append(f"| Replan | {replan_with_firing}/{total} |")
    lines.append(f"| Cache invalidation | {cache_inv_with_firing}/{total} |")

    lines.append("")
    lines.append(f"Recorded at: {run_at}")

    return "\n".join(lines) + "\n"


def update_readme(data: dict, *, readme_path: Path) -> None:
    scoreboard = generate_scoreboard(data)
    begin = "<!-- SCOREBOARD:BEGIN -->"
    end = "<!-- SCOREBOARD:END -->"

    if not readme_path.exists():
        readme_path.write_text(f"{begin}\n{scoreboard}{end}\n")
        return

    content = readme_path.read_text()
    if begin in content and end in content:
        pre = content[: content.index(begin) + len(begin)]
        post = content[content.index(end) :]
        new_content = f"{pre}\n{scoreboard}{post}"
    else:
        section = f"\n## Live eval results\n\n{begin}\n{scoreboard}{end}\n"
        new_content = content.rstrip() + section
    if new_content != content:
        readme_path.write_text(new_content)


def _find_latest_results(results_dir: Path) -> Path:
    try:
        return max(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except ValueError as exc:
        raise FileNotFoundError(f"No result JSON files found in {results_dir}") from exc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scoreboard generator for eval results")
    parser.add_argument("results_file", nargs="?", help="Path to results JSON")
    parser.add_argument("--update-readme", action="store_true")
    parser.add_argument(
        "--readme-path",
        default=None,
        help="Path to README to update (default: task2/README.md)",
    )
    parser.add_argument("--output", default=None, help="Write scoreboard to this file")
    parser.add_argument(
        "--diff",
        metavar="BASELINE_RESULTS_JSON",
        default=None,
        help="Path to baseline results JSON; appends Δ vs master diff block to output",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Emit per-step breakdown table for failing cases",
    )
    args = parser.parse_args(argv)

    if args.results_file:
        results_path = Path(args.results_file)
    else:
        results_dir = Path("eval") / "results"
        results_path = _find_latest_results(results_dir)

    data = json.loads(results_path.read_text())
    scoreboard = generate_scoreboard(data, detail=args.detail)

    if args.diff is not None:
        diff_path = Path(args.diff)
        if not diff_path.exists():
            print(f"error: --diff path does not exist: {args.diff}", file=sys.stderr)
            sys.exit(1)
        baseline_data = json.loads(diff_path.read_text())
        diff_block = generate_diff_markdown(baseline_data, data)
        scoreboard = scoreboard + "\n---\n" + diff_block

    if args.output:
        Path(args.output).write_text(scoreboard)
    else:
        print(scoreboard, end="")

    if args.update_readme:
        default_readme = Path(__file__).resolve().parent.parent / "README.md"
        readme = Path(args.readme_path) if args.readme_path else default_readme
        update_readme(data, readme_path=readme)


if __name__ == "__main__":
    main(sys.argv[1:])
