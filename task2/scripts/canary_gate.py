from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.eval import FAIL_STATUSES, PASS_STATUSES


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, metavar="PATH")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.results).read_text())
    cases = data.get("cases", [])

    canary_cases = [c for c in cases if c.get("canary", False)]
    if not canary_cases:
        print("canary-gate: no canary cases found in results; gate is a no-op")
        sys.exit(0)

    failing_canaries = [c for c in canary_cases if c.get("status") not in PASS_STATUSES]
    if failing_canaries:
        statuses = ", ".join(f"{c['id']}={c.get('status')}" for c in failing_canaries)
        print(f"canary-gate: FAILED — canary regressions detected: {statuses}")
        sys.exit(1)

    non_canary_failing = [
        c for c in cases if not c.get("canary", False) and c.get("status") in FAIL_STATUSES
    ]
    if non_canary_failing:
        ids = ", ".join(c["id"] for c in non_canary_failing)
        print(f"WARNING: non-canary regressions detected: {ids}")
        sys.exit(0)

    print("canary-gate: all canary cases passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
