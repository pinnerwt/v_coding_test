from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from agent.browser import Browser
from agent.llm import LLMClient
from agent.loop import RunResult, loop
from agent.trace import (
    ActEvent,
    AnyEvent,
    DoneEvent,
    LocateEvent,
    PlanEvent,
    Run,
    RunBudget,
    RunLLM,
    SupervisorEvent,
    TraceWriter,
)

_REQUIRED_FIELDS = ("id", "domain", "category", "task", "expect", "budget")
_PASS_STATUSES = frozenset({"succeeded", "unverified"})
_FAIL_STATUSES = frozenset({"failed", "blocked", "timeout"})
_SKIP_STATUS = "skipped"


def load_cases(path: str | Path) -> list[dict]:
    p = Path(path)
    with p.open() as f:
        raw = yaml.safe_load(f)
    cases: list[dict] = raw if isinstance(raw, list) else [raw]
    for case in cases:
        for required_field in _REQUIRED_FIELDS:
            if required_field not in case:
                raise ValueError(f"Case in {p} is missing required field: {required_field!r}")
    return cases


def run_validators(validators: list[str], result: dict) -> list[dict]:
    out: list[dict] = []
    for expr in validators:
        if ".len_gte:" in expr:
            key, rest = expr.split(".len_gte:", 1)
            key = key.strip()
            n = int(rest.strip())
            val = result.get(key)
            ok = isinstance(val, (list, tuple)) and len(val) >= n
        elif expr.endswith(".nonempty"):
            key = expr.removesuffix(".nonempty").strip()
            val = result.get(key)
            ok = isinstance(val, str) and bool(val.strip())
        else:
            raise ValueError(f"Unknown validator expression: {expr!r}")
        out.append({"name": expr, "ok": ok})
    return out


@dataclass(frozen=True)
class CaseResult:
    id: str
    status: str
    steps: int
    usd: float
    l_tier_counts: dict
    validators: list[dict]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms_total: int = 0
    latency_ms_per_step: list[int] = field(default_factory=list)
    step_breakdown: list[dict] = field(default_factory=list)
    escalations: list[dict] = field(default_factory=list)
    replans: int = 0
    cache_events: dict = field(default_factory=dict)
    failure_class: str | None = None
    failure_detail: str | None = None


def _aggregate_diagnostics(
    writer: TraceWriter, run_id: str
) -> tuple[list[AnyEvent], list[dict], int, dict]:
    events: list[AnyEvent] = list(writer.iter_events(run_id))
    locates_by_seq: dict[int, LocateEvent] = {
        ev.seq: ev for ev in events if isinstance(ev, LocateEvent)
    }

    escalations: list[dict] = []
    replan_count = 0
    hits = 0
    invalidations = 0
    misses = 0

    for i, ev in enumerate(events):
        if isinstance(ev, SupervisorEvent) and ev.policy == "next_tier":
            trigger = locates_by_seq.get(ev.trigger_event_seq)
            from_tier = trigger.tier if trigger is not None else None
            intent_str = trigger.intent if trigger is not None else ""
            to_tier: str | None = None
            for j in range(i + 1, len(events)):
                nxt = events[j]
                if (
                    isinstance(nxt, LocateEvent)
                    and nxt.step_id == ev.step_id
                    and nxt.outcome == "hit"
                ):
                    to_tier = nxt.tier
                    break
            escalations.append(
                {
                    "intent": intent_str,
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "reason": ev.classified_as.lower(),
                }
            )
        elif isinstance(ev, PlanEvent) and ev.reason == "replan":
            replan_count += 1
        elif isinstance(ev, LocateEvent):
            if ev.cache_action == "read" and ev.outcome == "hit":
                hits += 1
            elif ev.cache_action == "invalidate":
                invalidations += 1
            elif ev.cache_action is None and ev.outcome == "miss":
                misses += 1

    return (
        events,
        escalations,
        replan_count,
        {"hits": hits, "invalidations": invalidations, "misses": misses},
    )


def _open_trace_run(writer: TraceWriter, run_id: str, case: dict) -> None:
    budget = case.get("budget", {})
    run = Run(
        run_id=run_id,
        task=case.get("task", ""),
        expect_schema=None,
        budget=RunBudget(
            steps=budget.get("steps", 20),
            usd=budget.get("usd", 1.0),
            seconds=budget.get("seconds", 300),
        ),
        llm=RunLLM(base_url="", model="", temperature=0.0, seed=None),
        agent_version="eval",
        started_at=datetime.now(UTC).isoformat(),
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    writer.open_run(run)


def _classify_failure(
    events: list[AnyEvent], validators: list[dict], status: str
) -> tuple[str | None, str | None]:
    if status not in {"failed"}:
        return None, None

    for ev in events:
        if isinstance(ev, SupervisorEvent) and ev.policy == "halt":
            return "supervisor_halt", ev.classified_as

    has_next_tier = any(
        isinstance(ev, SupervisorEvent) and ev.policy == "next_tier" for ev in events
    )
    if has_next_tier:
        all_resolved = all(
            any(
                isinstance(nxt, LocateEvent) and nxt.step_id == ev.step_id and nxt.outcome == "hit"
                for nxt in events[i + 1 :]
            )
            for i, ev in enumerate(events)
            if isinstance(ev, SupervisorEvent) and ev.policy == "next_tier"
        )
        if not all_resolved:
            return "locator_miss", "locator exhausted all tiers without a hit"

    for ev in events:
        if isinstance(ev, ActEvent) and ev.outcome == "error":
            detail = ev.diff.get("error", "unknown error")
            return "tool_error", str(detail)

    done_events = [ev for ev in events if isinstance(ev, DoneEvent)]

    failed_validators = [v for v in validators if not v.get("ok", True)]
    if failed_validators:
        names = ", ".join(v["name"] for v in failed_validators)
        return "validator_fail", names

    if done_events:
        last_done = done_events[-1]
        verifier = last_done.verifier
        if not verifier.get("ok", True):
            reasons = verifier.get("reasons", [])
            detail = "; ".join(reasons) if reasons else "schema check failed"
            return "schema_error", detail
        return "other", "done emitted and verifier passed but status is failed"

    return "no_done_emitted", "no DoneEvent in trace"


def _run_case(case: dict[str, Any], llm_client: Any, browser: Any, cache: Any = None) -> CaseResult:
    run_id = str(uuid.uuid4())
    with TraceWriter(path=":memory:") as writer:
        _open_trace_run(writer, run_id, case)
        try:
            run_result: RunResult = loop(
                case["task"],
                browser,
                llm_client,
                max_steps=case["budget"]["steps"],
                trace_writer=writer,
                run_id=run_id,
                locator_cache=cache,
            )
        except Exception as exc:
            return CaseResult(
                id=case["id"],
                status="failed",
                steps=0,
                usd=0.0,
                l_tier_counts={},
                validators=[{"name": "exception", "ok": False, "error": repr(exc)}],
                failure_class="tool_error",
                failure_detail=repr(exc),
            )
        events, escalations, replans, cache_events = _aggregate_diagnostics(writer, run_id)
    validator_results = run_validators(
        case.get("expect", {}).get("validators", []),
        run_result.result or {},
    )
    failure_class, failure_detail = _classify_failure(events, validator_results, run_result.status)
    return CaseResult(
        id=case["id"],
        status=run_result.status,
        steps=run_result.steps,
        usd=run_result.usd,
        l_tier_counts={},
        validators=validator_results,
        prompt_tokens=run_result.prompt_tokens,
        completion_tokens=run_result.completion_tokens,
        latency_ms_total=run_result.latency_ms_total,
        latency_ms_per_step=run_result.latency_ms_per_step,
        step_breakdown=run_result.step_breakdown,
        escalations=escalations,
        replans=replans,
        cache_events=cache_events,
        failure_class=failure_class,
        failure_detail=failure_detail,
    )


def _skipped_result(case: dict) -> CaseResult:
    return CaseResult(
        id=case["id"],
        status=_SKIP_STATUS,
        steps=0,
        usd=0.0,
        l_tier_counts={},
        validators=[],
    )


def run_suite(
    cases: list[dict],
    *,
    results_dir: str | Path,
    live: bool = False,
    llm_client: Any = None,
    browser: Any = None,
) -> Path:
    from agent.locator_cache import LocatorCache

    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    case_results: list[CaseResult] = []

    for parent_case in cases:
        variants = parent_case.get("variants")
        use_shared_cache = parent_case.get("shared_cache", False) and variants
        shared_cache = LocatorCache(path=":memory:") if use_shared_cache else None

        if variants:
            sub_cases = [{**parent_case, "id": f"{parent_case['id']}-{v}"} for v in variants]
        else:
            sub_cases = [parent_case]

        for case in sub_cases:
            if not live and not case.get("fixture", False):
                r = _skipped_result(case)
            else:
                r = _run_case(case, llm_client, browser, cache=shared_cache)
            case_results.append(r)
            print(f"[{_label(r.status)}] {r.id} ({r.steps} steps, ${r.usd:.4f})", flush=True)

    payload = {
        "run_at": now.isoformat(),
        "cases": [asdict(r) for r in case_results],
    }
    out_path = results_dir / f"{now.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def compute_exit_code(cases: list[dict]) -> int:
    return 1 if any(c["status"] in _FAIL_STATUSES for c in cases) else 0


def build_clients():
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090/v1")
    model = os.environ.get("LLM_MODEL", "qwen3")
    api_key = os.environ.get("LLM_API_KEY", "local")
    return LLMClient(base_url=base_url, model=model, api_key=api_key), Browser()


def _label(status: str) -> str:
    if status in _PASS_STATUSES:
        return "PASS"
    if status == _SKIP_STATUS:
        return "SKIP"
    return "FAIL"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", dest="case_id", default=None)
    args = parser.parse_args(argv)

    cases_dir = Path(os.environ.get("EVAL_CASES_DIR", "eval/cases"))
    results_dir = Path(os.environ.get("EVAL_RESULTS_DIR", "eval/results"))

    all_cases: list[dict] = []
    for yaml_file in sorted(cases_dir.glob("*.yaml")):
        all_cases.extend(load_cases(yaml_file))

    if args.case_id:
        all_cases = [c for c in all_cases if c["id"] == args.case_id]

    llm_client, browser = build_clients()
    with browser:
        out = run_suite(
            all_cases,
            results_dir=results_dir,
            live=args.live,
            llm_client=llm_client,
            browser=browser,
        )

    data = json.loads(out.read_text())
    print(f"Results: {out}")
    return compute_exit_code(data["cases"])


if __name__ == "__main__":
    sys.exit(main())
