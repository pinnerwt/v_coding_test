from __future__ import annotations

from agent.loop import _build_system_prompt


def test_system_prompt_contains_only_for_irrecoverable():
    prompt = _build_system_prompt("dummy task")
    assert "only for irrecoverable conditions" in prompt


def test_system_prompt_contains_action_first_guidance():
    prompt = _build_system_prompt("dummy task")
    assert "attempt `click`/`type`" in prompt


def test_system_prompt_does_not_contain_old_phrasing():
    prompt = _build_system_prompt("dummy task")
    assert "If you cannot complete the task, call" not in prompt


def test_system_prompt_names_irrecoverable_conditions():
    prompt = _build_system_prompt("dummy task")
    assert "login walls" in prompt
    assert "captchas" in prompt
    assert "pages that don't exist" in prompt
    assert "genuinely absent from the page" in prompt


_SCHEMA_MARKER = "MUST be a JSON object matching this schema"


def test_build_system_prompt_schema_present():
    prompt = _build_system_prompt(
        "find the price",
        expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]},
    )
    assert _SCHEMA_MARKER in prompt
    assert "answer" in prompt


def test_build_system_prompt_schema_absent():
    prompt = _build_system_prompt("find the price")
    assert "browser automation agent" in prompt
    assert "find the price" in prompt
    assert "only for irrecoverable conditions" in prompt
    assert _SCHEMA_MARKER not in prompt
    assert _build_system_prompt("find the price") == _build_system_prompt(
        "find the price", expect=None
    )


def test_build_system_prompt_empty_schema_leaves_no_schema_clause():
    prompt = _build_system_prompt(
        "find the price",
        expect={"schema": {}, "validators": []},
    )
    assert _SCHEMA_MARKER not in prompt
    assert prompt == _build_system_prompt("find the price")


def test_build_system_prompt_required_keys_appear_sorted():
    prompt = _build_system_prompt(
        "task",
        expect={"schema": {"title": "str", "answer": "str"}, "validators": []},
    )
    assert "answer, title" in prompt
    assert "title, answer" not in prompt
