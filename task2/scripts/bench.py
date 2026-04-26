from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent.browser import Browser
from agent.llm import LLMClient
from eval.bench.webvoyager_loader import load_webvoyager
from scripts.eval import compute_exit_code, run_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    results_dir = Path(os.environ.get("EVAL_RESULTS_DIR", "eval/results"))

    if args.suite == "webvoyager":
        tasks_path = os.environ.get(
            "WEBVOYAGER_TASKS",
            "tests/fixtures/benchmarks/webvoyager/tasks_sample.json",
        )
        cases = load_webvoyager(tasks_path)
    else:
        raise ValueError(f"Unknown suite: {args.suite!r}")

    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090/v1")
    model = os.environ.get("LLM_MODEL", "qwen3")
    api_key = os.environ.get("LLM_API_KEY", "local")
    llm_client = LLMClient(base_url=base_url, model=model, api_key=api_key)
    browser = Browser()

    with browser:
        out = run_suite(
            cases,
            results_dir=results_dir,
            live=args.live,
            llm_client=llm_client,
            browser=browser,
        )

    data = json.loads(out.read_text())
    return compute_exit_code(data["cases"])


if __name__ == "__main__":
    sys.exit(main())
