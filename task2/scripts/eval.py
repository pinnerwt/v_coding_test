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

from agent.browser import Browser
from agent.llm import LLMClient
from agent.loop import RunResult, loop

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


def _expand_variants(cases: list[dict]) -> list[dict]:
    result: list[dict] = []
    for case in cases:
        variants = case.get("variants")
        if variants:
            for v in variants:
                expanded = {**case, "id": f"{case['id']}-{v}", "_variant": v}
                result.append(expanded)
        else:
            result.append(case)
    return result


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
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    cases = _expand_variants(cases)
    case_results: list[CaseResult] = []
    for case in cases:
        if not live and not case.get("fixture", False):
            r = _skipped_result(case)
        else:
            r = _run_case(case, llm_client, browser)
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


def _build_clients():
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

    llm_client, browser = _build_clients()
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
