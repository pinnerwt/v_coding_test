from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from agent.loop import RunResult, loop

_REQUIRED_FIELDS = ("id", "domain", "category", "task", "expect", "budget")


def load_cases(path: str | Path) -> list[dict]:
    p = Path(path)
    with p.open() as f:
        raw = yaml.safe_load(f)
    cases: list[dict] = raw if isinstance(raw, list) else [raw]
    for case in cases:
        for field in _REQUIRED_FIELDS:
            if field not in case:
                raise ValueError(f"Case in {p} is missing required field: {field!r}")
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
        else:
            key = expr.removesuffix(".nonempty").strip()
            val = result.get(key)
            ok = isinstance(val, str) and bool(val.strip())
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


def _run_case(case: dict[str, Any], llm_client: Any, browser: Any) -> CaseResult:
    run_result: RunResult = loop(
        case["task"],
        browser,
        llm_client,
        max_steps=case["budget"]["steps"],
    )
    validator_results = run_validators(
        case.get("expect", {}).get("validators", []),
        run_result.result or {},
    )
    return CaseResult(
        id=case["id"],
        status=run_result.status,
        steps=0,
        usd=0.0,
        l_tier_counts={},
        validators=validator_results,
    )


def run_suite(
    cases: list[dict],
    *,
    results_dir: str | Path,
    live: bool = False,
    llm_client: Any = None,
    browser: Any = None,
) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now(UTC).isoformat()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    case_results: list[CaseResult] = []
    for case in cases:
        is_fixture = case.get("fixture", False)
        if not live and not is_fixture:
            case_results.append(
                CaseResult(
                    id=case["id"],
                    status="skipped",
                    steps=0,
                    usd=0.0,
                    l_tier_counts={},
                    validators=[],
                )
            )
        else:
            case_results.append(_run_case(case, llm_client, browser))
    payload = {
        "run_at": run_at,
        "cases": [asdict(r) for r in case_results],
    }
    out_path = results_dir / f"{ts}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def compute_exit_code(cases: list[dict]) -> int:
    fail_statuses = {"failed", "blocked", "timeout"}
    return 1 if any(c["status"] in fail_statuses for c in cases) else 0


def _build_clients():
    from agent.browser import Browser
    from agent.llm import LLMClient

    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090/v1")
    model = os.environ.get("LLM_MODEL", "qwen3")
    api_key = os.environ.get("LLM_API_KEY", "local")
    llm_client = LLMClient(base_url=base_url, model=model, api_key=api_key)
    browser = Browser()
    return llm_client, browser


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run eval suite")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", dest="case_id", default=None)
    args = parser.parse_args()

    cases_dir = Path(os.environ.get("EVAL_CASES_DIR", "eval/cases"))
    results_dir = Path(os.environ.get("EVAL_RESULTS_DIR", "eval/results"))

    all_cases: list[dict] = []
    for yaml_file in sorted(cases_dir.glob("*.yaml")):
        all_cases.extend(load_cases(yaml_file))

    if args.case_id:
        all_cases = [c for c in all_cases if c["id"] == args.case_id]

    llm_client, browser = _build_clients()
    out = run_suite(
        all_cases,
        results_dir=results_dir,
        live=args.live,
        llm_client=llm_client,
        browser=browser,
    )

    data = json.loads(out.read_text())
    for c in data["cases"]:
        label = (
            "PASS"
            if c["status"] in {"succeeded", "unverified"}
            else ("SKIP" if c["status"] == "skipped" else "FAIL")
        )
        print(f"[{label}] {c['id']} ({c['steps']} steps, ${c['usd']:.4f})")
    print(f"Results: {out}")
    sys.exit(compute_exit_code(data["cases"]))
