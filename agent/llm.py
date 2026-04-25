from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx


_DEFAULT_BASE_URL = "http://localhost:8090"
_CHAT_PATH = "/v1/chat/completions"
_MAX_ERROR_BODY = 2048


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: str,
        status: int | None = None,
        body: str | None = None,
        cause: BaseException | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.body = _truncate(body) if body is not None else None
        self.cause = cause


def _truncate(s: str) -> str:
    if len(s) <= _MAX_ERROR_BODY:
        return s
    return s[:_MAX_ERROR_BODY]


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    model: str
    usage: Usage
    raw: dict


def _resolve(kwarg: str | None, env_name: str, default: str | None) -> str | None:
    if kwarg is not None:
        return kwarg
    env_val = os.environ.get(env_name)
    if env_val is not None:
        return env_val
    return default


class LLMClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        self._base_url_override = base_url
        self._model_override = model
        self._api_key_override = api_key
        self._client = httpx.Client(timeout=timeout)

    def _resolved_base_url(self, override: str | None) -> str:
        url = _resolve(override or self._base_url_override, "LLM_BASE_URL", _DEFAULT_BASE_URL)
        assert url is not None  # default ensures non-None
        return url.rstrip("/")

    def _resolved_model(self, override: str | None) -> str:
        model = _resolve(override or self._model_override, "LLM_MODEL", None)
        if not model:
            raise LLMError("model not configured", kind="config")
        return model

    def _resolved_api_key(self, override: str | None) -> str | None:
        return _resolve(override or self._api_key_override, "LLM_API_KEY", None)

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tools: list[dict] | None = None,
        seed: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> ChatResponse:
        resolved_model = self._resolved_model(model)
        resolved_base = self._resolved_base_url(base_url)
        resolved_key = self._resolved_api_key(api_key)

        body: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools is not None:
            body["tools"] = tools
        if seed is not None:
            body["seed"] = seed

        headers = {"Content-Type": "application/json"}
        if resolved_key:
            headers["Authorization"] = f"Bearer {resolved_key}"

        url = f"{resolved_base}{_CHAT_PATH}"
        try:
            response = self._client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"transport error: {exc}", kind="transport", cause=exc) from exc

        if response.status_code >= 400:
            raise LLMError(
                f"http {response.status_code}",
                kind="http",
                status=response.status_code,
                body=response.text,
            )

        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMError(
                "response body is not valid JSON",
                kind="decode",
                body=response.text,
                cause=exc,
            ) from exc

        return _parse_response(payload)


def _parse_response(payload: Any) -> ChatResponse:
    if not isinstance(payload, dict):
        raise LLMError("response is not a JSON object", kind="decode")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("response missing 'choices'", kind="decode")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise LLMError("choice is not an object", kind="decode")

    message = choice.get("message")
    if not isinstance(message, dict):
        raise LLMError("choice missing 'message'", kind="decode")

    content_raw = message.get("content")
    content: str | None = content_raw if isinstance(content_raw, str) and content_raw else None

    tool_calls_raw = message.get("tool_calls") or []
    tool_calls: list[ToolCall] = []
    for tc in tool_calls_raw:
        if not isinstance(tc, dict):
            raise LLMError("tool_call is not an object", kind="decode")
        fn = tc.get("function") or {}
        try:
            tool_calls.append(
                ToolCall(
                    id=tc["id"],
                    name=fn["name"],
                    arguments=fn.get("arguments", ""),
                )
            )
        except KeyError as exc:
            raise LLMError(f"tool_call missing field: {exc}", kind="decode") from exc

    finish_reason = choice.get("finish_reason") or ""
    model = payload.get("model") or ""
    usage_raw = payload.get("usage") or {}
    usage = Usage(
        prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
        completion_tokens=int(usage_raw.get("completion_tokens", 0)),
        total_tokens=int(usage_raw.get("total_tokens", 0)),
    )

    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        model=model,
        usage=usage,
        raw=payload,
    )


def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.0,
    tools: list[dict] | None = None,
    seed: int | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> ChatResponse:
    client = LLMClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
    )
    return client.chat(
        messages,
        model=model,
        temperature=temperature,
        tools=tools,
        seed=seed,
    )
