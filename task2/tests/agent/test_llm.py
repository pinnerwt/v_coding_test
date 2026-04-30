import json
from unittest.mock import patch

import httpx
import pytest
import respx

from agent.llm import ChatResponse, LLMClient, LLMError, ToolCall, Usage, chat

CHAT_PATH = "/v1/chat/completions"


def _ok_payload(content="hello", model="qwen3.5", tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
        if content == "":
            message["content"] = None
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 1,
            "total_tokens": 6,
        },
    }


@respx.mock
def test_default_base_url():
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert route.called
    assert route.calls.last.request.url == f"http://localhost:8090{CHAT_PATH}"


@respx.mock
def test_env_base_url_honored(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3.5")
    route = respx.post(f"https://api.example.com/v1{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload(model="qwen3.5"))
    )

    chat(messages=[{"role": "user", "content": "hi"}])

    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "qwen3.5"


@respx.mock
def test_explicit_kwarg_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://env.example.com")
    route = respx.post(f"https://override.example.com{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(
        messages=[{"role": "user", "content": "hi"}],
        model="m",
        base_url="https://override.example.com",
    )

    assert route.called


@respx.mock
def test_request_body_shape():
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "m"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["temperature"] == 0.0
    assert "tools" not in body
    assert "seed" not in body
    assert route.calls.last.request.headers["content-type"].startswith("application/json")


@respx.mock
def test_tools_and_seed_forwarded():
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )
    tools = [
        {
            "type": "function",
            "function": {"name": "click", "parameters": {"type": "object"}},
        }
    ]

    chat(
        messages=[{"role": "user", "content": "hi"}],
        model="m",
        tools=tools,
        seed=7,
    )

    body = json.loads(route.calls.last.request.content)
    assert body["tools"] == tools
    assert body["seed"] == 7


@respx.mock
def test_authorization_header_present(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert route.calls.last.request.headers["authorization"] == "Bearer sk-test"


@respx.mock
def test_authorization_header_absent():
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert "authorization" not in {k.lower() for k in route.calls.last.request.headers.keys()}


@respx.mock
def test_parses_content_response():
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload(content="hello"))
    )

    resp = chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert isinstance(resp, ChatResponse)
    assert resp.content == "hello"
    assert resp.tool_calls == []
    assert resp.finish_reason == "stop"
    assert resp.model == "qwen3.5"
    assert isinstance(resp.usage, Usage)
    assert resp.usage.prompt_tokens == 5
    assert resp.usage.completion_tokens == 1
    assert resp.usage.total_tokens == 6


@respx.mock
def test_parses_tool_call_response():
    tc = [
        {
            "id": "c1",
            "type": "function",
            "function": {
                "name": "click",
                "arguments": '{"intent": "submit"}',
            },
        }
    ]
    payload = _ok_payload(content="", tool_calls=tc)
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    resp = chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert resp.content is None
    assert len(resp.tool_calls) == 1
    assert isinstance(resp.tool_calls[0], ToolCall)
    assert resp.tool_calls[0].id == "c1"
    assert resp.tool_calls[0].name == "click"
    assert resp.tool_calls[0].arguments == '{"intent": "submit"}'


@respx.mock
def test_raw_field_preserved():
    payload = _ok_payload(content="hi")
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    resp = chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert resp.raw == payload


@respx.mock
def test_missing_model_raises_config_error():
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    with pytest.raises(LLMError) as ei:
        chat(messages=[{"role": "user", "content": "hi"}])

    assert ei.value.kind == "config"
    assert not route.called


@respx.mock
def test_http_500_raises_http_error():
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(500, text="upstream timeout")
    )

    with pytest.raises(LLMError) as ei:
        chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert ei.value.kind == "http"
    assert ei.value.status == 500
    assert ei.value.body == "upstream timeout"


@respx.mock
def test_transport_error_raises_transport_error():
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(LLMError) as ei:
        chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert ei.value.kind == "transport"
    assert isinstance(ei.value.cause, httpx.ConnectError)


@respx.mock
def test_decode_error_on_bad_json():
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, text="not json {")
    )

    with pytest.raises(LLMError) as ei:
        chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert ei.value.kind == "decode"


@respx.mock
def test_decode_error_on_missing_choices():
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )

    with pytest.raises(LLMError) as ei:
        chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert ei.value.kind == "decode"


@respx.mock
def test_error_body_truncated_to_2048():
    big = "x" * 5000
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(return_value=httpx.Response(502, text=big))

    with pytest.raises(LLMError) as ei:
        chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert ei.value.kind == "http"
    assert ei.value.body is not None
    assert len(ei.value.body) <= 2048


@respx.mock
def test_llmclient_reuses_config():
    route = respx.post(f"https://x.example.com{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload(model="m"))
    )
    client = LLMClient(base_url="https://x.example.com", model="m")

    client.chat(messages=[{"role": "user", "content": "1"}])
    client.chat(messages=[{"role": "user", "content": "2"}])

    assert route.call_count == 2
    for call in route.calls:
        assert call.request.url == f"https://x.example.com{CHAT_PATH}"
        body = json.loads(call.request.content)
        assert body["model"] == "m"


@respx.mock
def test_llmclient_per_call_override():
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload(model="other-m"))
    )
    client = LLMClient(model="default-m")

    client.chat(messages=[{"role": "user", "content": "hi"}], model="other-m")

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "other-m"


@respx.mock
def test_llmclient_does_not_load_price_table_until_first_chat():
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    with patch("agent.llm.load_price_table") as mock_load:
        mock_load.return_value = {
            "models": {},
            "default": {"prompt_per_1k": 0.0, "completion_per_1k": 0.0},
        }
        client = LLMClient(model="m")
        assert mock_load.call_count == 0

        client.chat(messages=[{"role": "user", "content": "hi"}])
        assert mock_load.call_count == 1

        client.chat(messages=[{"role": "user", "content": "hi"}])
        assert mock_load.call_count == 1


_PRICE_TABLE_QWEN35 = {
    "models": {
        "qwen3.5": {"prompt_per_1k": 0.002, "completion_per_1k": 0.006},
    },
    "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002},
}


@respx.mock
def test_chat_response_has_usd_field():
    payload = {
        "id": "chatcmpl-usd",
        "object": "chat.completion",
        "model": "qwen3.5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        },
    }
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = LLMClient(model="qwen3.5", price_table=_PRICE_TABLE_QWEN35)
    resp = client.chat(messages=[{"role": "user", "content": "hi"}])

    assert hasattr(resp, "usd")
    assert abs(resp.usd - 0.005) < 1e-9


@respx.mock
def test_chat_response_usd_uses_injected_price_table_not_file():
    """Injected price_table is used without reading pricing.toml."""
    payload = {
        "id": "chatcmpl-2",
        "object": "chat.completion",
        "model": "qwen3.5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        },
    }
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    custom_table = {
        "models": {"qwen3.5": {"prompt_per_1k": 0.001, "completion_per_1k": 0.001}},
        "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.001},
    }
    client = LLMClient(model="qwen3.5", price_table=custom_table)
    resp = client.chat(messages=[{"role": "user", "content": "hi"}])

    assert abs(resp.usd - 0.0015) < 1e-9


@respx.mock
def test_chat_response_usd_uses_actual_response_model():
    payload = {
        "id": "chatcmpl-actual",
        "object": "chat.completion",
        "model": "actual-m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        },
    }
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    price_table = {
        "models": {
            "requested-m": {"prompt_per_1k": 0.001, "completion_per_1k": 0.001},
            "actual-m": {"prompt_per_1k": 0.01, "completion_per_1k": 0.02},
        },
        "default": {"prompt_per_1k": 0.0001, "completion_per_1k": 0.0001},
    }
    client = LLMClient(model="requested-m", price_table=price_table)
    resp = client.chat(messages=[{"role": "user", "content": "hi"}])

    assert resp.model == "actual-m"
    expected = 1.0 * 0.01 + 0.5 * 0.02
    assert abs(resp.usd - expected) < 1e-9


@respx.mock
def test_chat_response_usd_unknown_model_uses_default():
    payload = {
        "id": "chatcmpl-3",
        "object": "chat.completion",
        "model": "unknown-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 1000,
            "total_tokens": 2000,
        },
    }
    respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = LLMClient(model="unknown-model", price_table=_PRICE_TABLE_QWEN35)
    resp = client.chat(messages=[{"role": "user", "content": "hi"}])

    expected = 1.0 * 0.001 + 1.0 * 0.002
    assert abs(resp.usd - expected) < 1e-9


@respx.mock
def test_chat_disable_thinking_env_unset_omits_kwargs(monkeypatch):
    monkeypatch.delenv("LLM_DISABLE_THINKING", raising=False)
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert "chat_template_kwargs" not in body


@respx.mock
@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_chat_disable_thinking_truthy_env_injects_kwargs(monkeypatch, value):
    monkeypatch.setenv("LLM_DISABLE_THINKING", value)
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


@respx.mock
@pytest.mark.parametrize("value", ["0", "false", "no", "", "off"])
def test_chat_disable_thinking_falsy_env_omits_kwargs(monkeypatch, value):
    monkeypatch.setenv("LLM_DISABLE_THINKING", value)
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert "chat_template_kwargs" not in body


@respx.mock
def test_chat_temperature_env_overrides_default(monkeypatch):
    """LLM_TEMPERATURE in the environment becomes the request temperature when
    the caller does not pass one explicitly. Lets benchmarks force temp=0.0
    without code changes; lets prod set a higher value via Zeabur env."""
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert body["temperature"] == 0.7


@respx.mock
def test_chat_temperature_env_unset_defaults_to_zero(monkeypatch):
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert body["temperature"] == 0.0


@respx.mock
def test_chat_explicit_temperature_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m", temperature=0.2)

    body = json.loads(route.calls.last.request.content)
    assert body["temperature"] == 0.2


@respx.mock
def test_chat_invalid_temperature_env_falls_back_to_zero(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "not-a-number")
    route = respx.post(f"http://localhost:8090{CHAT_PATH}").mock(
        return_value=httpx.Response(200, json=_ok_payload())
    )

    chat(messages=[{"role": "user", "content": "hi"}], model="m")

    body = json.loads(route.calls.last.request.content)
    assert body["temperature"] == 0.0
