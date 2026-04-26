"""Offline decision-replay harness for the agent loop.

Given a recorded trace JSONL file, drives loop.py with a stub browser and
stub LLM client (no real Playwright, no real HTTP) and compares emitted
decisions against the recording. Targets traces using `goto`, `read`
(no intent), `done`, `fail`; intent-based reads always surface as prompt
drift since the stub locator resolves to zero matches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import STATE_MESSAGE_PREFIX, loop
from agent.trace import (
    AnyEvent,
    DecisionEvent,
    LLMCallEvent,
    ObservationEvent,
    Run,
    _any_event_adapter,
)

_TERMINAL_TOOLS = frozenset({"done", "fail"})


class _ZeroMatchLocator:
    """Locator that resolves to zero matches.

    Lets locate_l1/locate_l2 raise a clean LocatorMiss(zero_matches) — which
    loop._dispatch turns into an "Error: could not locate ..." tool message —
    instead of letting the stub page surface AttributeError on missing methods.
    """

    def count(self) -> int:
        return 0

    def filter(self, **_: Any) -> _ZeroMatchLocator:
        return self


_ZERO_MATCH = _ZeroMatchLocator()


class _StubPage:
    def __init__(
        self,
        url: str = "",
        *,
        observations: list[dict] | None = None,
    ) -> None:
        self._observations: list[dict] = list(observations or [])
        self._idx: int = -1
        self._url: str = url
        self._text: str = ""

    @property
    def url(self) -> str:
        # _url is driven by goto() so a goto regression surfaces as prompt drift
        # instead of being masked by the recording. Only _text is replayed.
        if self._observations and self._idx + 1 < len(self._observations):
            self._idx += 1
            self._text = str(self._observations[self._idx].get("text", ""))
        return self._url

    def set_url(self, url: str) -> None:
        self._url = url

    def evaluate(self, js: str, *args: Any) -> str:  # noqa: ARG002
        return self._text

    def get_by_role(
        self,
        role: str,  # noqa: ARG002
        *,
        name: str | None = None,  # noqa: ARG002
        exact: bool = False,  # noqa: ARG002
    ) -> _ZeroMatchLocator:
        return _ZERO_MATCH

    def get_by_placeholder(
        self,
        text: str,  # noqa: ARG002
        *,
        exact: bool = False,  # noqa: ARG002
    ) -> _ZeroMatchLocator:
        return _ZERO_MATCH

    def locator(self, selector: str) -> _ZeroMatchLocator:  # noqa: ARG002
        return _ZERO_MATCH

    def title(self) -> str:
        return ""


class StubBrowser:
    """Duck-type replacement for agent.browser.Browser.

    Does NOT subclass agent.browser.Browser to avoid importing Playwright.
    """

    def __init__(
        self,
        *,
        initial_url: str = "",
        observations: list[dict] | None = None,
    ) -> None:
        self._page: _StubPage = _StubPage(url=initial_url, observations=observations)

    def goto(self, url: str) -> None:
        self._page.set_url(url)

    def read(self, selector: str) -> str:  # noqa: ARG002
        return ""

    def screenshot(self, *, full_page: bool = False) -> bytes:  # noqa: ARG002
        return b""

    def click_at(self, x: int, y: int) -> None:  # noqa: ARG002
        pass

    def __enter__(self) -> StubBrowser:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        pass


def _noop_response() -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[],
        finish_reason="stop",
        model="stub",
        usage=Usage(0, 0, 0),
        raw={},
    )


class StubLLMClient:
    """Returns pre-recorded ChatResponse objects in sequence.

    Does NOT subclass agent.llm.LLMClient to avoid constructing httpx.Client
    or reading environment variables.
    """

    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses: list[ChatResponse] = list(responses)
        self._idx: int = 0
        self.responses_consumed: list[ChatResponse] = []
        self.prompts_consumed: list[list[dict]] = []

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,  # noqa: ARG002
        temperature: float = 0.0,  # noqa: ARG002
        tools: list[dict] | None = None,  # noqa: ARG002
        seed: int | None = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ChatResponse:
        # Snapshot the messages — loop.py keeps mutating the same list across calls.
        self.prompts_consumed.append(json.loads(json.dumps(messages)))
        if self._idx < len(self._responses):
            response = self._responses[self._idx]
            self._idx += 1
        else:
            response = _noop_response()
        self.responses_consumed.append(response)
        return response


@dataclass(frozen=True)
class ReplayDivergence:
    step_id: str | None
    expected: dict
    actual: dict
    kind: Literal["decision", "prompt"] = "decision"


@dataclass(frozen=True)
class ReplayResult:
    matched: bool
    steps: int
    first_divergence: ReplayDivergence | None


def _iter_replayed_pairs(responses: list[ChatResponse]):
    """Yield (tool_name, args) pairs loop.py would emit DecisionEvents for.

    Stops at the first `done`/`fail` because loop.py returns there.
    """
    for cr in responses:
        for tc in cr.tool_calls:
            pair = _replayed_pair(tc)
            if pair is None:
                continue
            yield pair
            if pair[0] in _TERMINAL_TOOLS:
                return


def _replayed_pair(tc: ToolCall) -> tuple[str, dict] | None:
    """(tool_name, args) for tool calls loop.py would actually dispatch.

    Mirrors loop.py: malformed JSON or non-object args are recoverable — no
    DecisionEvent is emitted for them, so replay must not count them either.
    """
    try:
        args = json.loads(tc.arguments) if tc.arguments else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict):
        return None
    return tc.name, args


def _observation_from_call(call: LLMCallEvent) -> dict:
    messages = call.prompt.get("messages") or []
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not content.startswith(STATE_MESSAGE_PREFIX):
            continue
        try:
            payload = json.loads(content[len(STATE_MESSAGE_PREFIX) :])
        except json.JSONDecodeError:
            return {"url": ""}
        if not isinstance(payload, dict):
            return {"url": ""}
        return payload
    return {"url": ""}


def _response_from_recorded(resp: dict) -> ChatResponse:
    tool_calls: list[ToolCall] = []
    for tc in resp.get("tool_calls") or []:
        fn = tc.get("function") or {}
        arguments_raw = fn.get("arguments", "")
        arguments = arguments_raw if isinstance(arguments_raw, str) else json.dumps(arguments_raw)
        tool_calls.append(
            ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=arguments,
            )
        )

    content_raw = resp.get("content")
    content: str | None = content_raw if isinstance(content_raw, str) else None
    finish_reason: str = resp.get("finish_reason") or ""

    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        model="stub",
        usage=Usage(0, 0, 0),
        raw=resp,
    )


def replay_run(trace_path: str | Path) -> ReplayResult:
    """Load a trace JSONL, drive loop.py offline, and compare decisions.

    First line is a Run JSON; subsequent lines are AnyEvent JSON (the format
    TraceWriter writes). Returns a ReplayResult describing whether every
    decision step matched and, if not, the first divergence.
    """
    path = Path(trace_path)
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"Trace file {str(path)!r} is empty; expected a Run header line.")

    run = Run.model_validate_json(lines[0])
    events: list[AnyEvent] = [_any_event_adapter.validate_json(ln) for ln in lines[1:]]

    recorded_decisions: list[DecisionEvent] = sorted(
        (e for e in events if isinstance(e, DecisionEvent)),
        key=lambda e: e.seq,
    )
    decide_llm_calls: list[LLMCallEvent] = sorted(
        (e for e in events if isinstance(e, LLMCallEvent) and e.purpose == "decide"),
        key=lambda e: e.seq,
    )
    responses: list[ChatResponse] = [
        _response_from_recorded(lc.response) for lc in decide_llm_calls
    ]

    observations = [_observation_from_call(lc) for lc in decide_llm_calls]
    first_obs = next((e for e in events if isinstance(e, ObservationEvent)), None)
    initial_url = first_obs.url if first_obs is not None else ""
    stub_browser = StubBrowser(initial_url=initial_url, observations=observations)
    stub_llm = StubLLMClient(responses)

    # Closed runs cap at the recorded count (timeout traces fit exactly); truncated
    # runs (status=None) get slack so surplus chat() calls surface as divergence.
    headroom = 0 if run.status is not None else 2
    loop(
        task=run.task,
        browser=stub_browser,
        llm_client=stub_llm,
        max_steps=len(decide_llm_calls) + headroom,
    )

    # Diff on `messages` only — `LLMCallEvent.prompt` may carry extra keys
    # (tools/model/…) that replay does not drive.
    n_recorded_calls = len(decide_llm_calls)
    n_consumed_calls = len(stub_llm.prompts_consumed)
    n_prompt_pairs = min(n_recorded_calls, n_consumed_calls)
    for i in range(n_prompt_pairs):
        recorded_messages = decide_llm_calls[i].prompt.get("messages")
        actual_messages = stub_llm.prompts_consumed[i]
        if recorded_messages != actual_messages:
            return ReplayResult(
                matched=False,
                steps=i,
                first_divergence=ReplayDivergence(
                    step_id=decide_llm_calls[i].step_id,
                    expected={"messages": recorded_messages},
                    actual={"messages": actual_messages},
                    kind="prompt",
                ),
            )

    if n_consumed_calls != n_recorded_calls:
        step_id = (
            decide_llm_calls[n_consumed_calls].step_id
            if n_recorded_calls > n_consumed_calls
            else None
        )
        return ReplayResult(
            matched=False,
            steps=n_prompt_pairs,
            first_divergence=ReplayDivergence(
                step_id=step_id,
                expected={"chat_calls": n_recorded_calls},
                actual={"chat_calls": n_consumed_calls},
                kind="prompt",
            ),
        )

    replayed_pairs = list(_iter_replayed_pairs(stub_llm.responses_consumed))

    n_rec = len(recorded_decisions)
    n_rep = len(replayed_pairs)
    steps = min(n_rec, n_rep)

    for i in range(steps):
        rec = recorded_decisions[i]
        rep_tool, rep_args = replayed_pairs[i]
        if rec.tool != rep_tool or rec.args != rep_args:
            return ReplayResult(
                matched=False,
                steps=i,
                first_divergence=ReplayDivergence(
                    step_id=rec.step_id,
                    expected={"tool": rec.tool, "args": rec.args},
                    actual={"tool": rep_tool, "args": rep_args},
                ),
            )

    if n_rec > n_rep:
        rec = recorded_decisions[steps]
        return ReplayResult(
            matched=False,
            steps=steps,
            first_divergence=ReplayDivergence(
                step_id=rec.step_id,
                expected={"tool": rec.tool, "args": rec.args},
                actual={"tool": "", "args": {}},
            ),
        )
    if n_rep > n_rec:
        rep_tool, rep_args = replayed_pairs[steps]
        return ReplayResult(
            matched=False,
            steps=steps,
            first_divergence=ReplayDivergence(
                step_id=None,
                expected={"tool": "", "args": {}},
                actual={"tool": rep_tool, "args": rep_args},
            ),
        )

    return ReplayResult(matched=True, steps=steps, first_divergence=None)
