from __future__ import annotations

import pytest

from agent.loop import trim_history


def _sys() -> dict:
    return {"role": "system", "content": "You are a browser agent."}


def _user_state(n: int) -> dict:
    return {"role": "user", "content": f"##STATE## step {n}"}


def _group(n: int) -> tuple[dict, dict]:
    call_id = f"tc-{n}"
    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": "goto", "arguments": "{}"}}
        ],
    }
    tool_result = {"role": "tool", "tool_call_id": call_id, "content": f"result {n}"}
    return assistant, tool_result


def _build_messages() -> list[dict]:
    msgs: list[dict] = [_sys()]
    msgs.append(_user_state(0))
    for i in range(1, 7):
        asst, tool = _group(i)
        msgs.append(_user_state(i))
        msgs.append(asst)
        msgs.append(tool)
    return msgs


def test_trim_history_drops_oldest_groups_outside_window():
    messages = _build_messages()
    result = trim_history(messages, keep_steps=4)

    assert result is not messages

    assert result[0] == _sys()

    user_contents = {m["content"] for m in result if m["role"] == "user"}
    for i in range(7):
        assert f"##STATE## step {i}" in user_contents, f"user state {i} missing"

    kept_ids = {f"tc-{i}" for i in range(3, 7)}
    dropped_ids = {f"tc-{i}" for i in range(1, 3)}

    result_tool_call_ids = {
        tc["id"]
        for m in result
        if m["role"] == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }
    result_tool_result_ids = {m["tool_call_id"] for m in result if m["role"] == "tool"}

    for cid in kept_ids:
        assert cid in result_tool_call_ids, f"kept group {cid} assistant missing"
        assert cid in result_tool_result_ids, f"kept group {cid} tool result missing"

    for cid in dropped_ids:
        assert cid not in result_tool_call_ids, f"dropped group {cid} assistant still present"
        assert cid not in result_tool_result_ids, f"dropped group {cid} tool result still present"


def test_trim_history_retains_system_prompt():
    messages = _build_messages()
    result = trim_history(messages, keep_steps=2)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are a browser agent."


def test_trim_history_never_drops_user_state_messages():
    messages = _build_messages()
    result = trim_history(messages, keep_steps=1)
    user_msgs = [m for m in result if m["role"] == "user"]
    assert len(user_msgs) == 7


def test_trim_history_keep_window_larger_than_history_is_noop():
    messages = _build_messages()
    result = trim_history(messages, keep_steps=100)
    assert result == messages


def test_trim_history_drops_multi_tool_call_group_atomically():
    call_id_a = "tc-multi-a"
    call_id_b = "tc-multi-b"
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": call_id_a, "type": "function", "function": {"name": "f", "arguments": "{}"}},
                {"id": call_id_b, "type": "function", "function": {"name": "f", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": call_id_a, "content": "ra"},
        {"role": "tool", "tool_call_id": call_id_b, "content": "rb"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "tc-keep", "type": "function", "function": {"name": "f", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "tc-keep", "content": "rk"},
    ]
    result = trim_history(messages, keep_steps=1)

    result_tool_ids = {m["tool_call_id"] for m in result if m["role"] == "tool"}
    result_asst_call_ids = {
        tc["id"]
        for m in result
        if m["role"] == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }

    assert call_id_a not in result_tool_ids
    assert call_id_b not in result_tool_ids
    assert call_id_a not in result_asst_call_ids
    assert call_id_b not in result_asst_call_ids
    assert "tc-keep" in result_tool_ids
    assert "tc-keep" in result_asst_call_ids


def test_trim_history_respects_env_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HISTORY_TRIM_KEEP_STEPS", "2")
    messages = _build_messages()
    result = trim_history(messages)

    kept_ids = {f"tc-{i}" for i in range(5, 7)}
    dropped_ids = {f"tc-{i}" for i in range(1, 5)}

    result_tool_call_ids = {
        tc["id"]
        for m in result
        if m["role"] == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }
    result_tool_result_ids = {m["tool_call_id"] for m in result if m["role"] == "tool"}

    for cid in kept_ids:
        assert cid in result_tool_call_ids
        assert cid in result_tool_result_ids

    for cid in dropped_ids:
        assert cid not in result_tool_call_ids
        assert cid not in result_tool_result_ids


def test_trim_history_does_not_mutate_input():
    import copy

    messages = _build_messages()
    snapshot = copy.deepcopy(messages)
    _ = trim_history(messages, keep_steps=2)
    assert messages == snapshot


def test_trim_history_handles_empty_list():
    result = trim_history([], keep_steps=4)
    assert result == []


def test_trim_history_handles_only_system_message():
    messages = [{"role": "system", "content": "sys"}]
    result = trim_history(messages, keep_steps=4)
    assert result == messages


def test_trim_history_handles_no_tool_groups():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    result = trim_history(messages, keep_steps=4)
    assert result == messages


def test_trim_history_handles_assistant_with_tool_calls_no_results():
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc-orphan",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}"},
                }
            ],
        },
    ]
    result = trim_history(messages, keep_steps=1)
    result_asst_call_ids = {
        tc["id"]
        for m in result
        if m["role"] == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }
    assert "tc-orphan" in result_asst_call_ids


def test_trim_history_preserves_first_tool_group_when_window_smaller():
    """First tool-result group (group 0) must survive even when keep_steps < total groups."""
    messages = _build_messages()
    result = trim_history(messages, keep_steps=2)

    result_tool_call_ids = {
        tc["id"]
        for m in result
        if m["role"] == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }
    result_tool_result_ids = {m["tool_call_id"] for m in result if m["role"] == "tool"}

    for cid in ("tc-1", "tc-5", "tc-6"):
        assert cid in result_tool_call_ids, f"anchor/kept group {cid} assistant missing"
        assert cid in result_tool_result_ids, f"anchor/kept group {cid} tool result missing"

    for cid in ("tc-2", "tc-3", "tc-4"):
        assert cid not in result_tool_call_ids, f"dropped group {cid} assistant still present"
        assert cid not in result_tool_result_ids, f"dropped group {cid} tool result still present"


def test_trim_history_unparseable_env_var_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("HISTORY_TRIM_KEEP_STEPS", "not-an-int")
    messages = _build_messages()
    result = trim_history(messages)

    kept_ids = {f"tc-{i}" for i in range(3, 7)}
    dropped_ids = {f"tc-{i}" for i in range(1, 3)}

    result_tool_call_ids = {
        tc["id"]
        for m in result
        if m["role"] == "assistant" and m.get("tool_calls")
        for tc in m["tool_calls"]
    }

    for cid in kept_ids:
        assert cid in result_tool_call_ids
    for cid in dropped_ids:
        assert cid not in result_tool_call_ids
