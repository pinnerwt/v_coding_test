from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.eval import build_clients, compute_exit_code, load_cases, run_suite
from scripts.score import generate_scoreboard

_BENCHMARK_ROOT = Path("benchmark")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class BenchmarkVerificationError(Exception):
    pass


def resolve_branch(explicit: str | None) -> str:
    if explicit:
        return explicit
    for var in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        val = os.environ.get(var)
        if val:
            return val
    raise ValueError("no branch given; pass --branch or set GITHUB_HEAD_REF / GITHUB_REF_NAME")


def sanitize_branch(name: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("-", name).replace("/", "-")
    cleaned = cleaned.strip("-.")
    if not cleaned:
        raise ValueError(f"branch name sanitized to empty: {name!r}")
    return cleaned


def output_dir_for_branch(branch: str) -> Path:
    return _BENCHMARK_ROOT / sanitize_branch(branch)


def write_outputs(results: dict, *, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    (out_dir / "scoreboard.md").write_text(generate_scoreboard(results))


def verify_benchmark(*, branch: str, base_date: str) -> None:
    out_dir = output_dir_for_branch(branch)
    results = out_dir / "results.json"
    if not results.exists():
        raise BenchmarkVerificationError(
            f"benchmark results missing for branch {branch!r} at {results}; "
            f"run `uv run python -m scripts.benchmark --branch {branch}` and commit the output"
        )
    data = json.loads(results.read_text())
    run_at = datetime.fromisoformat(data["run_at"])
    base_dt = datetime.fromisoformat(base_date)
    if run_at < base_dt:
        raise BenchmarkVerificationError(
            f"benchmark for branch {branch!r} is stale: run_at={run_at.isoformat()} "
            f"is older than base commit date {base_dt.isoformat()}; re-run the benchmark"
        )


def _build_results_payload(case_results) -> dict:
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "cases": [asdict(r) for r in case_results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run eval and record metrics per branch")
    parser.add_argument("--branch", default=None, help="branch name (defaults to GH env)")
    parser.add_argument("--live", action="store_true", help="run live cases too")
    parser.add_argument(
        "--verify",
        metavar="BASE_ISO_DATE",
        default=None,
        help="verify mode: check results exist and run_at >= BASE_ISO_DATE; do not run",
    )
    args = parser.parse_args(argv)

    branch = resolve_branch(args.branch)

    if args.verify:
        try:
            verify_benchmark(branch=branch, base_date=args.verify)
        except BenchmarkVerificationError as exc:
            print(f"benchmark verification failed: {exc}", file=sys.stderr)
            return 1
        print(f"benchmark verified for branch {branch!r}")
        return 0

    out_dir = output_dir_for_branch(branch)

    cases_dir = Path(os.environ.get("EVAL_CASES_DIR", "eval/cases"))
    all_cases: list[dict] = []
    for yaml_file in sorted(cases_dir.glob("*.yaml")):
        all_cases.extend(load_cases(yaml_file))

    llm_client, browser = build_clients()
    with browser:
        out_path = run_suite(
            all_cases,
            results_dir=out_dir,
            live=args.live,
            llm_client=llm_client,
            browser=browser,
        )

    data = json.loads(out_path.read_text())
    out_path.unlink()
    write_outputs(data, out_dir=out_dir)
    print(f"Wrote: {out_dir}/results.json, {out_dir}/scoreboard.md")
    return compute_exit_code(data["cases"])


if __name__ == "__main__":
    sys.exit(main())
