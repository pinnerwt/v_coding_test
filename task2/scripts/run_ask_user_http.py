#!/usr/bin/env python3
"""Drive the ask_user_test_set against the live HTTP /sessions API.

Per case:
  POST /sessions -> stream /sessions/{id}/events -> answer on ask_user
  -> stop on terminal -> dump full event log.

Per-slot answers
----------------
Ambiguous cases declare multiple slots. Each slot has a list of `match`
keywords (case-insensitive substrings on the question text) and a `reply`.
The first slot whose keyword matches is used. If no slot matches, the
case-level `default` reply is sent.

This makes the smoke test deterministic when the planner asks for slots
sequentially or in any order — without needing to fuse them into one
multi-slot ask.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

BASE = os.environ.get("API_BASE", "http://localhost:40781")
OUT_DIR = Path(os.environ.get("OUT_DIR", "/tmp/ask_user_smoke"))
OUT_DIR.mkdir(parents=True, exist_ok=True)


CASES: list[dict[str, Any]] = [
    {
        "id": "A1",
        "ambiguous": True,
        "task": "Book a table at Inparadise (旭集) for noon next Saturday.",
        "answers": [
            {
                "match": ["branch", "location", "店", "which inparadise", "which 旭集"],
                "reply": "天母店 (Tianmu)",
            },
            {
                "match": ["how many", "party size", "people", "guests", "diners"],
                "reply": "2 people",
            },
            {
                "match": ["time", "what time", "noon", "when"],
                "reply": "12:00 noon",
            },
            {
                "match": ["name", "under what name", "reservation name"],
                "reply": "Pinner Tw",
            },
            {
                "match": ["phone", "contact"],
                "reply": "0912-345-678",
            },
        ],
        "default": "天母店 (Tianmu), 2 people, noon, under name Pinner Tw",
    },
    {
        "id": "A3",
        "ambiguous": True,
        "task": "Book a flight from Taipei to Tokyo and return the cheapest fare.",
        "answers": [
            {
                "match": ["depart", "departure date", "leaving", "outbound", "when"],
                "reply": "December 15, 2026",
            },
            {
                "match": [
                    "return date",
                    "coming back",
                    "round trip",
                    "round-trip",
                    "one-way",
                    "one way",
                ],
                "reply": "one-way (no return)",
            },
            {
                "match": ["passenger", "how many", "travelers", "adults", "people"],
                "reply": "1 adult",
            },
            {
                "match": ["class", "cabin", "economy", "business"],
                "reply": "economy",
            },
            {
                "match": ["airport", "which airport"],
                "reply": "any airport in Taipei to any airport in Tokyo",
            },
        ],
        "default": "December 15, 2026, one-way, 1 adult, economy",
    },
    {
        "id": "A6",
        "ambiguous": True,
        "task": "Find the best ramen restaurant in Tokyo on Google Maps.",
        "answers": [
            {
                "match": [
                    "best by what",
                    "criterion",
                    "criteria",
                    "metric",
                    "rated",
                    "ranking",
                    "what makes",
                ],
                "reply": "highest-rated by Google reviews",
            },
            {
                "match": [
                    "which area",
                    "neighborhood",
                    "district",
                    "ward",
                    "where in tokyo",
                    "specific area",
                ],
                "reply": "Shinjuku",
            },
            {
                "match": ["style", "type of ramen", "tonkotsu", "shoyu", "miso"],
                "reply": "any style is fine",
            },
            {
                "match": ["price", "budget", "expensive", "cheap"],
                "reply": "no budget constraint",
            },
        ],
        "default": "highest-rated by Google reviews, in Shinjuku",
    },
    {
        "id": "U1",
        "ambiguous": False,
        "task": "Tell me the name of the Turing Award winner in 2018.",
        "answers": [],
        "default": "use your best judgement",
    },
    {
        "id": "U4",
        "ambiguous": False,
        "task": "Find the abstract of the paper 'Attention Is All You Need' on arXiv.",
        "answers": [],
        "default": "use your best judgement",
    },
]

HARD_TIMEOUT_S = 360


def _pick_answer(case: dict[str, Any], question: str) -> tuple[str, str]:
    """Return (reply, slot_label). slot_label is "default" or the first matched keyword."""
    q = question.lower()
    for slot in case.get("answers") or []:
        for kw in slot.get("match", []):
            if kw.lower() in q:
                return slot["reply"], kw
    return case.get("default", "use your best judgement"), "default"


def _print_trace(ev: dict[str, Any]) -> None:
    payload = {k: v for k, v in ev.items() if k != "type"}
    kind = payload.get("event") or payload.get("kind") or payload.get("name")
    if kind in (
        "plan",
        "planner",
        "tool_call",
        "act",
        "observe",
        "tool_result",
        "step",
        "model_reply",
        "replan",
    ):
        small = {
            k: payload.get(k)
            for k in ("event", "kind", "tool", "step_index", "args", "summary", "step", "ok")
            if k in payload
        }
        text = json.dumps(small, ensure_ascii=False)[:200]
        print(f"  trace {text}")


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    print(f"\n=== {case['id']} ({'AMBIG' if case['ambiguous'] else 'CLEAR'}) ===")
    print(f"  task: {case['task']}")

    client = httpx.Client(timeout=httpx.Timeout(HARD_TIMEOUT_S, connect=10.0))
    r = client.post(f"{BASE}/sessions", json={"task": case["task"]})
    r.raise_for_status()
    run_id = r.json()["id"]
    print(f"  run_id: {run_id}")

    events: list[dict[str, Any]] = []
    asked: list[dict[str, str]] = []
    terminal: dict[str, Any] | None = None
    start = time.time()

    with client.stream("GET", f"{BASE}/sessions/{run_id}/events") as resp:
        resp.raise_for_status()
        buf = ""
        for chunk in resp.iter_text():
            if not chunk:
                if time.time() - start > HARD_TIMEOUT_S:
                    print("  TIMEOUT")
                    break
                continue
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                events.append(ev)
                etype = ev.get("type")
                if etype == "trace":
                    _print_trace(ev)
                elif etype == "ask_user":
                    q = ev.get("question", "")
                    reply, slot = _pick_answer(case, q)
                    asked.append({"question": q, "reply": reply, "slot": slot})
                    print(f"  ask_user: {q!r}")
                    print(f"    -> slot={slot} reply={reply!r}")
                    ar = client.post(
                        f"{BASE}/sessions/{run_id}/answer",
                        json={"answer": reply},
                        timeout=10,
                    )
                    if ar.status_code != 200:
                        print(f"  answer-post FAIL {ar.status_code} {ar.text}")
                elif etype == "answer":
                    pass
                elif etype == "terminal":
                    terminal = ev
                    print(f"  terminal: status={ev.get('status')} reason={ev.get('reason')}")
                    _r = json.dumps(ev.get("result"), ensure_ascii=False)[:200]
                    _e = json.dumps(ev.get("evidence"), ensure_ascii=False)[:200]
                    print(f"           result={_r}")
                    print(f"         evidence={_e}")
                    break
            if terminal is not None:
                break
            if time.time() - start > HARD_TIMEOUT_S:
                print("  HARD TIMEOUT")
                break

    summary = {
        "case_id": case["id"],
        "run_id": run_id,
        "task": case["task"],
        "ambiguous_expected": case["ambiguous"],
        "saw_ask_user": bool(asked),
        "asked_questions": asked,
        "terminal": terminal,
        "elapsed_s": round(time.time() - start, 1),
        "n_events": len(events),
    }
    out = OUT_DIR / f"{case['id']}.json"
    out.write_text(json.dumps({"summary": summary, "events": events}, ensure_ascii=False, indent=2))
    print(f"  -> {out} ({summary['n_events']} events, {summary['elapsed_s']}s)")
    client.close()
    return summary


def main() -> int:
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    summaries = []
    for case in CASES:
        if only and case["id"] not in only:
            continue
        try:
            summaries.append(run_case(case))
        except Exception as exc:
            print(f"  EXCEPTION: {exc}")
            summaries.append({"case_id": case["id"], "error": str(exc)})

    print("\n=== SUMMARY ===")
    for s in summaries:
        if "error" in s:
            print(f"  {s['case_id']}: ERROR {s['error']}")
            continue
        ok = s["saw_ask_user"] == s["ambiguous_expected"]
        flag = "PASS" if ok else "MISS"
        term = (s.get("terminal") or {}).get("status")
        print(
            f"  {s['case_id']}: {flag} expected_ask={s['ambiguous_expected']} "
            f"asked={s['saw_ask_user']} term={term} t={s['elapsed_s']}s"
        )
    (OUT_DIR / "_summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
