from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

from agent.locator_cache import LocatorCache
from scripts.baseline_diff import generate_diff_markdown
from scripts.eval import (
    _PASS_STATUSES,
    _SKIP_STATUS,
    _run_case,
    build_clients,
    compute_exit_code,
    load_cases,
    run_suite,
)
from scripts.score import _percentile, generate_scoreboard

_DEFAULT_REPEATS = 1

RepeatStatus = Literal["all_pass", "partial", "all_fail", "skipped"]
_VALID_REPEAT_STATUSES: frozenset[str] = frozenset(get_args(RepeatStatus))

DerivedStatus = Literal["succeeded", "failed", "skipped"]
_VALID_DERIVED_STATUSES: frozenset[str] = frozenset(get_args(DerivedStatus))


@dataclass(frozen=True)
class AggregatedCaseResult:
    id: str
    repeat_status: RepeatStatus
    repeats: int
    passed_runs: int
    median_latency_ms: int
    p95_latency_ms: int
    stddev_usd: float
    avg_mechanism_firings: float
    status: DerivedStatus
    steps: int
    usd: float
    prompt_tokens: int
    completion_tokens: int
    latency_ms_total: int
    escalations: list[dict] = field(default_factory=list)
    replans: int = 0
    cache_events: dict = field(default_factory=dict)
    failure_class: str | None = None
    skip_reason: str | None = None

    def __post_init__(self) -> None:
        if self.repeat_status not in _VALID_REPEAT_STATUSES:
            raise ValueError(
                f"repeat_status {self.repeat_status!r} not in {sorted(_VALID_REPEAT_STATUSES)}"
            )
        if self.status not in _VALID_DERIVED_STATUSES:
            raise ValueError(f"status {self.status!r} not in {sorted(_VALID_DERIVED_STATUSES)}")


def _pre_run_skip_reason(case: dict, *, live: bool) -> str | None:
    fixture_path = case.get("fixture_path")
    if fixture_path is not None and not Path(fixture_path).exists():
        return "fixture_missing"
    if not live and not case.get("fixture", False):
        return "live_disabled"
    return None


def _skipped_aggregate(case: dict, *, repeats: int, reason: str) -> AggregatedCaseResult:
    return AggregatedCaseResult(
        id=case["id"],
        repeat_status="skipped",
        repeats=repeats,
        passed_runs=0,
        median_latency_ms=0,
        p95_latency_ms=0,
        stddev_usd=0.0,
        avg_mechanism_firings=0.0,
        status=_SKIP_STATUS,
        steps=0,
        usd=0.0,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms_total=0,
        escalations=[],
        replans=0,
        cache_events={},
        failure_class=None,
        skip_reason=reason,
    )


def aggregate_repeats(
    case: dict,
    *,
    repeats: int,
    llm_client,
    browser,
    live: bool = False,
    cache=None,
) -> AggregatedCaseResult:
    skip_reason = _pre_run_skip_reason(case, live=live)
    if skip_reason is not None:
        return _skipped_aggregate(case, repeats=repeats, reason=skip_reason)

    runs = [_run_case(case, llm_client, browser, cache=cache) for _ in range(repeats)]

    all_skipped = all(r.status == _SKIP_STATUS for r in runs)
    passed_runs = sum(1 for r in runs if r.status in _PASS_STATUSES)

    if all_skipped:
        repeat_status: RepeatStatus = "skipped"
    elif passed_runs == repeats:
        repeat_status = "all_pass"
    elif passed_runs == 0:
        repeat_status = "all_fail"
    else:
        repeat_status = "partial"

    status_map: dict[RepeatStatus, DerivedStatus] = {
        "all_pass": "succeeded",
        "partial": "failed",
        "all_fail": "failed",
        "skipped": _SKIP_STATUS,
    }
    derived_status = status_map[repeat_status]

    latencies = [r.latency_ms_total for r in runs]
    usd_values = [r.usd for r in runs]
    steps_values = [r.steps for r in runs]
    firings = [len(r.escalations) + r.replans for r in runs]

    median_lat = int(statistics.median(latencies))
    p95_lat = _percentile(latencies, 95)
    stddev_usd = statistics.pstdev(usd_values)
    avg_firings = sum(firings) / len(firings)
    mean_replans = sum(r.replans for r in runs) / len(runs)
    median_steps = int(statistics.median(steps_values))
    mean_usd = sum(usd_values) / len(usd_values)

    failing_runs = [r for r in runs if r.status not in _PASS_STATUSES and r.status != _SKIP_STATUS]
    rep_run = failing_runs[-1] if failing_runs else runs[-1]

    return AggregatedCaseResult(
        id=case["id"],
        repeat_status=repeat_status,
        repeats=repeats,
        passed_runs=passed_runs,
        median_latency_ms=median_lat,
        p95_latency_ms=p95_lat,
        stddev_usd=stddev_usd,
        avg_mechanism_firings=avg_firings,
        status=derived_status,
        steps=median_steps,
        usd=mean_usd,
        prompt_tokens=sum(r.prompt_tokens for r in runs),
        completion_tokens=sum(r.completion_tokens for r in runs),
        latency_ms_total=sum(latencies),
        escalations=rep_run.escalations,
        replans=round(mean_replans),
        cache_events=rep_run.cache_events,
        failure_class=rep_run.failure_class,
        skip_reason=rep_run.skip_reason if repeat_status == "skipped" else None,
    )


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


def write_diff(branch: str, branch_data: dict, *, benchmark_root: Path) -> None:
    if sanitize_branch(branch) == "master":
        return
    master_path = benchmark_root / "master" / "results.json"
    if not master_path.exists():
        print(
            f"baseline-diff: master baseline not found at {master_path}; skipping diff.md",
            file=sys.stderr,
        )
        return
    master_data = json.loads(master_path.read_text())
    diff_md = generate_diff_markdown(master_data, branch_data)
    out_path = benchmark_root / sanitize_branch(branch) / "diff.md"
    out_path.write_text(diff_md)


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
    parser.add_argument("--repeats", type=int, default=_DEFAULT_REPEATS)
    args = parser.parse_args(argv)

    if args.repeats < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 1

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

    if args.repeats > _DEFAULT_REPEATS:
        agg_results: list[AggregatedCaseResult] = []
        with browser:
            for parent_case in all_cases:
                variants = parent_case.get("variants")
                use_shared_cache = parent_case.get("shared_cache", False) and variants
                shared_cache = LocatorCache(path=":memory:") if use_shared_cache else None

                if variants:
                    sub_cases = [
                        {**parent_case, "id": f"{parent_case['id']}-{v}"} for v in variants
                    ]
                else:
                    sub_cases = [parent_case]

                for case in sub_cases:
                    agg_results.append(
                        aggregate_repeats(
                            case,
                            repeats=args.repeats,
                            llm_client=llm_client,
                            browser=browser,
                            live=args.live,
                            cache=shared_cache,
                        )
                    )
        data = {
            "run_at": datetime.now(UTC).isoformat(),
            "cases": [asdict(r) for r in agg_results],
        }
        write_outputs(data, out_dir=out_dir)
        write_diff(branch, data, benchmark_root=_BENCHMARK_ROOT)
        print(f"Wrote: {out_dir}/results.json, {out_dir}/scoreboard.md")
        return compute_exit_code(data["cases"])

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
    write_diff(branch, data, benchmark_root=_BENCHMARK_ROOT)
    print(f"Wrote: {out_dir}/results.json, {out_dir}/scoreboard.md")
    return compute_exit_code(data["cases"])


if __name__ == "__main__":
    sys.exit(main())
