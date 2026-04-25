"""Offline decision-replay harness for the agent loop.

Given a recorded trace JSONL file, drives loop.py with a stub browser and
stub LLM client (no real Playwright, no real HTTP) and compares emitted
decisions against the recording.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import loop
from agent.trace import AnyEvent, DecisionEvent, LLMCallEvent, Run, _any_event_adapter


class _StubPage:
    @property
    def url(self) -> str:
        return "http://stub.local/"

    def evaluate(self, js: str, *args: Any) -> str:  # noqa: ARG002
        return ""


class StubBrowser:
    """Duck-type replacement for agent.browser.Browser.

    Does NOT subclass agent.browser.Browser to avoid importing Playwright.
    """

    def __init__(self) -> None:
        self._page: _StubPage = _StubPage()

    def goto(self, url: str) -> None:  # noqa: ARG002
        pass

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
    kind: str = "decision"


@dataclass(frozen=True)
class ReplayResult:
    matched: bool
    steps: int
    first_divergence: ReplayDivergence | None


def _response_from_recorded(resp: dict) -> ChatResponse:
    tool_calls: list[ToolCall] = []
    for tc in resp.get("tool_calls") or []:
        fn = tc.get("function") or {}
        tool_calls.append(
            ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=fn.get("arguments", ""),
            )
        )

    content_raw = resp.get("content")
    content: str | None = content_raw if isinstance(content_raw, str) and content_raw else None
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

    stub_browser = StubBrowser()
    stub_llm = StubLLMClient(responses)

    loop(
        task=run.task,
        browser=stub_browser,
        llm_client=stub_llm,
        max_steps=len(decide_llm_calls) + 2,
    )

    # Prompt drift: compare what loop.py actually sent against what was recorded.
    # If the prompt diverges at any chat() call, surface that divergence — a matching
    # tool-call sequence is not enough to declare the run regression-free.
    n_prompt_pairs = min(len(decide_llm_calls), len(stub_llm.prompts_consumed))
    for i in range(n_prompt_pairs):
        recorded_prompt = decide_llm_calls[i].prompt
        actual_prompt = {"messages": stub_llm.prompts_consumed[i]}
        if recorded_prompt != actual_prompt:
            return ReplayResult(
                matched=False,
                steps=i,
                first_divergence=ReplayDivergence(
                    step_id=decide_llm_calls[i].step_id,
                    expected=recorded_prompt,
                    actual=actual_prompt,
                    kind="prompt",
                ),
            )

    # Decision diff is over tool-call responses only. A no-tool 'decide' turn produces
    # an LLMCallEvent but no DecisionEvent in the recording, so its consumed counterpart
    # must not occupy a slot in replayed_pairs.
    replayed_pairs: list[tuple[str, dict]] = []
    for cr in stub_llm.responses_consumed:
        if not cr.tool_calls:
            continue
        tc = cr.tool_calls[0]
        args = json.loads(tc.arguments) if tc.arguments else {}
        replayed_pairs.append((tc.name, args))

    n_rec = len(recorded_decisions)
    n_rep = len(replayed_pairs)
    steps = min(n_rec, n_rep)

    for i in range(steps):
        rec = recorded_decisions[i]
        rep_tool, rep_args = replayed_pairs[i]
        if rec.tool != rep_tool or rec.args != rep_args:
            return ReplayResult(
                matched=False,
                steps=steps,
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
