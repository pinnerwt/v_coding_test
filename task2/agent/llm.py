from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from agent.pricing import compute_usd, load_price_table

_DEFAULT_BASE_URL = "http://localhost:8090"
_DEFAULT_LLM_MODEL = "qwen3-5-27b"
_CHAT_PATH = "/v1/chat/completions"
_MAX_ERROR_BODY = 2048
_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_TIMEOUT = 180.0


def _resolve_temperature(explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    raw = os.environ.get("LLM_TEMPERATURE")
    if raw is None:
        return _DEFAULT_TEMPERATURE
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TEMPERATURE


def _resolve_timeout(explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    raw = os.environ.get("LLM_TIMEOUT")
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT


LLMErrorKind = Literal["config", "transport", "http", "decode"]


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: LLMErrorKind,
        status: int | None = None,
        body: str | None = None,
        cause: BaseException | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.body = body[:_MAX_ERROR_BODY] if body is not None else None
        self.cause = cause


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
    usd: float = 0.0


class LLMClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        price_table: dict | None = None,
    ):
        resolved_base = base_url or os.environ.get("LLM_BASE_URL") or _DEFAULT_BASE_URL
        self._base_url = resolved_base.rstrip("/")
        self._api_key = api_key or os.environ.get("LLM_API_KEY")
        self._model_default = model
        self._client = httpx.Client(timeout=_resolve_timeout(timeout))
        self._price_table: dict | None = price_table

    def _get_price_table(self) -> dict:
        if self._price_table is None:
            self._price_table = load_price_table()
        return self._price_table

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
        seed: int | None = None,
    ) -> ChatResponse:
        resolved_model = model or self._model_default or os.environ.get("LLM_MODEL")
        if not resolved_model:
            raise LLMError("model not configured", kind="config")

        resolved_temperature = _resolve_temperature(temperature)

        body: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": resolved_temperature,
        }
        if tools is not None:
            body["tools"] = tools
        if seed is not None:
            body["seed"] = seed
        if os.environ.get("LLM_DISABLE_THINKING", "").strip().lower() in {"1", "true", "yes", "on"}:
            body["chat_template_kwargs"] = {"enable_thinking": False}

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._base_url}{_CHAT_PATH}"
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
        except ValueError as exc:
            raise LLMError(
                "response body is not valid JSON",
                kind="decode",
                body=response.text,
                cause=exc,
            ) from exc

        return _parse_response(payload, price_table=self._get_price_table(), model=resolved_model)


def _parse_response(
    payload: Any,
    *,
    price_table: dict | None = None,
    model: str | None = None,
) -> ChatResponse:
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

    tool_calls: list[ToolCall] = []
    for tc in message.get("tool_calls") or []:
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

    usage_raw = payload.get("usage") or {}
    prompt_tokens = int(usage_raw.get("prompt_tokens", 0))
    completion_tokens = int(usage_raw.get("completion_tokens", 0))

    effective_model = payload.get("model") or model or ""
    usd = 0.0
    if price_table is not None:
        usd = compute_usd(prompt_tokens, completion_tokens, effective_model, price_table)

    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=choice.get("finish_reason") or "",
        model=effective_model,
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage_raw.get("total_tokens", 0)),
        ),
        raw=payload,
        usd=usd,
    )


def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float | None = None,
    tools: list[dict] | None = None,
    seed: int | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
) -> ChatResponse:
    with LLMClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
    ) as client:
        return client.chat(
            messages,
            model=model,
            temperature=temperature,
            tools=tools,
            seed=seed,
        )
