from __future__ import annotations

import json
from pathlib import Path

_EXPECT = {"schema": {"answer": "str"}, "validators": ["answer.nonempty"]}
_BUDGET = {"steps": 20, "usd": 0.25, "seconds": 120}


def load_webvoyager(path: str | Path) -> list[dict]:
    with Path(path).open() as f:
        entries = json.load(f)
    return [
        {
            "id": f"webvoyager-{entry['id']}",
            "task": f"Navigate to {entry['web']} and {entry['ques']}",
            "domain": entry["web"],
            "category": entry["web_name"],
            "expect": _EXPECT,
            "budget": _BUDGET,
            "fixture": False,
        }
        for entry in entries
    ]
