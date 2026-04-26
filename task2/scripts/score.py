from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = max(0, int((pct / 100) * len(sorted_vals) + 0.5) - 1)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def generate_scoreboard(data: dict) -> str:
    cases = data.get("cases", [])
    run_at = data.get("run_at", "unknown")

    lines: list[str] = []
    lines.append(f"Generated from eval run: {run_at}")
    lines.append("")

    lines.append("| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) |")
    lines.append("|---|---|---|---|---|---|")

    non_skipped = []
    total_usd = 0.0
    total_prompt = 0
    total_completion = 0
    tier_counts: dict[str, int] = {}

    for case in cases:
        status = case.get("status", "unknown")
        steps = case.get("steps", 0)
        lat = case.get("latency_ms_total", 0)
        usd = case.get("usd", 0.0)
        prompt = case.get("prompt_tokens", 0)
        completion = case.get("completion_tokens", 0)
        cid = case.get("id", "?")

        lines.append(f"| {cid} | {status} | {steps} | {lat} | ${usd:.4f} | {prompt}+{completion} |")

        if status != "skipped":
            non_skipped.append(case)
            total_usd += usd
            total_prompt += prompt
            total_completion += completion

        for tier, count in case.get("l_tier_counts", {}).items():
            tier_counts[tier] = tier_counts.get(tier, 0) + count

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
    args = parser.parse_args(argv)

    if args.results_file:
        results_path = Path(args.results_file)
    else:
        results_dir = Path("eval") / "results"
        results_path = _find_latest_results(results_dir)

    data = json.loads(results_path.read_text())
    scoreboard = generate_scoreboard(data)

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
