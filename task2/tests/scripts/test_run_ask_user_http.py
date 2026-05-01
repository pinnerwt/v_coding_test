"""Unit tests for the ask_user smoke runner's per-slot answer matcher."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_runner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_ask_user_http.py"
    spec = importlib.util.spec_from_file_location("run_ask_user_http", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


def _case(answers, default="DEFAULT"):
    return {"answers": answers, "default": default}


def test_pick_answer_matches_first_slot_by_keyword(runner):
    case = _case(
        [
            {"match": ["branch", "location"], "reply": "Tianmu"},
            {"match": ["how many", "people"], "reply": "2 people"},
        ]
    )
    reply, slot = runner._pick_answer(case, "Which branch of Inparadise?")
    assert reply == "Tianmu"
    assert slot == "branch"


def test_pick_answer_is_case_insensitive(runner):
    case = _case([{"match": ["Shinjuku"], "reply": "Shinjuku, please"}])
    reply, _ = runner._pick_answer(case, "Which AREA in Tokyo? E.g. shinjuku")
    assert reply == "Shinjuku, please"


def test_pick_answer_picks_earlier_slot_when_multiple_match(runner):
    case = _case(
        [
            {"match": ["depart", "when"], "reply": "Dec 15"},
            {"match": ["return", "one-way"], "reply": "one-way"},
        ]
    )
    # Question hits both "when" (slot 1) and "return" (slot 2). Slot 1 wins.
    reply, slot = runner._pick_answer(case, "When and what's your return date?")
    assert reply == "Dec 15"
    assert slot == "when"


def test_pick_answer_falls_back_to_default_when_no_keyword_matches(runner):
    case = _case(
        [{"match": ["branch", "location"], "reply": "Tianmu"}],
        default="best judgement",
    )
    reply, slot = runner._pick_answer(case, "Are you sure you want to continue?")
    assert reply == "best judgement"
    assert slot == "default"


def test_pick_answer_falls_back_to_default_when_no_slots_declared(runner):
    case = {"answers": [], "default": "use your best judgement"}
    reply, slot = runner._pick_answer(case, "anything")
    assert reply == "use your best judgement"
    assert slot == "default"


def test_pick_answer_handles_missing_default(runner):
    case = {"answers": []}
    reply, slot = runner._pick_answer(case, "anything")
    assert reply == "use your best judgement"
    assert slot == "default"


def test_cases_have_well_formed_slots(runner):
    """Every shipped case must have a default reply and well-formed slots."""
    for case in runner.CASES:
        assert "default" in case, f"{case['id']} missing default"
        assert isinstance(case["default"], str) and case["default"]
        for slot in case.get("answers", []):
            assert "match" in slot and isinstance(slot["match"], list) and slot["match"]
            assert "reply" in slot and isinstance(slot["reply"], str) and slot["reply"]
            for kw in slot["match"]:
                assert isinstance(kw, str) and kw.strip() == kw and kw
