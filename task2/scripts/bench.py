from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from eval.bench.webvoyager_loader import load_webvoyager
from scripts.eval import build_clients, compute_exit_code, run_suite

_LOADERS = {"webvoyager": load_webvoyager}
_DEFAULT_TASK_PATHS = {
    "webvoyager": {
        0: "tests/fixtures/benchmarks/webvoyager/tasks_sample.json",
        1: "eval/bench/data/webvoyager/tier1.json",
    },
}
_TASK_PATH_ENV_VARS = {"webvoyager": "WEBVOYAGER_TASKS"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, choices=sorted(_LOADERS))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--tier", type=int, choices=[0, 1], default=0)
    args = parser.parse_args(argv)

    os.environ.setdefault("LLM_TEMPERATURE", "0.0")

    results_dir = Path(os.environ.get("EVAL_RESULTS_DIR", "eval/results"))
    tasks_path = os.environ.get(
        _TASK_PATH_ENV_VARS[args.suite],
        _DEFAULT_TASK_PATHS[args.suite][args.tier],
    )
    cases = _LOADERS[args.suite](tasks_path)

    llm_client, browser = build_clients()
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
