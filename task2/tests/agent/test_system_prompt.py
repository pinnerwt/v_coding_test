from __future__ import annotations

from agent.loop import _build_system_prompt


def test_system_prompt_contains_only_for_irrecoverable():
    prompt = _build_system_prompt("dummy task")
    assert "ONLY for irrecoverable conditions" in prompt


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
    assert "required information genuinely absent from the page" in prompt
