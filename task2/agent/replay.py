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

# ---------------------------------------------------------------------------
# _StubPage — inner sentinel satisfying loop.py's browser._page contract
# ---------------------------------------------------------------------------


class _StubPage:
    """Minimal page sentinel: provides .url and .evaluate() used by loop._observe."""

    @property
    def url(self) -> str:
        return "http://stub.local/"

    def evaluate(self, js: str, *args: Any) -> str:  # noqa: ARG002
        return ""


# ---------------------------------------------------------------------------
# StubBrowser — duck-type replacement for agent.browser.Browser
# ---------------------------------------------------------------------------


class StubBrowser:
    """No-op browser stub for offline replay.

    Does NOT subclass agent.browser.Browser to avoid importing Playwright.
    """

    def __init__(self) -> None:
        self._page: _StubPage = _StubPage()

    def goto(self, url: str) -> None:  # noqa: ARG002
        """No-op navigation."""

    def read(self, selector: str) -> str:  # noqa: ARG002
        """Return empty string — LLM response is canned by the stub."""
        return ""

    def screenshot(self, *, full_page: bool = False) -> bytes:  # noqa: ARG002
        return b""

    def click_at(self, x: int, y: int) -> None:  # noqa: ARG002
        """No-op click."""

    def __enter__(self) -> StubBrowser:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        pass


# ---------------------------------------------------------------------------
# StubLLMClient — duck-type replacement for agent.llm.LLMClient
# ---------------------------------------------------------------------------


def _noop_response() -> ChatResponse:
    """Return a do-nothing ChatResponse for when the stub list is exhausted."""
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
        self._remaining: list[ChatResponse] = list(responses)
        self.responses_consumed: list[ChatResponse] = []

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
        if self._remaining:
            response = self._remaining.pop(0)
        else:
            response = _noop_response()
        self.responses_consumed.append(response)
        return response


# ---------------------------------------------------------------------------
# ReplayDivergence / ReplayResult — result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayDivergence:
    """Describes the first step where replay diverged from the recording."""

    step_id: str | None
    expected: dict  # {"tool": str, "args": dict}
    actual: dict  # {"tool": str, "args": dict}


@dataclass(frozen=True)
class ReplayResult:
    """Summary of a replay run."""

    matched: bool
    steps: int
    first_divergence: ReplayDivergence | None


# ---------------------------------------------------------------------------
# _response_from_recorded — convert LLMCallEvent.response dict → ChatResponse
# ---------------------------------------------------------------------------


def _response_from_recorded(resp: dict) -> ChatResponse:
    """Convert a recorded LLMCallEvent.response dict into a ChatResponse.

    Mirrors agent.llm._parse_response but operates on the already-decoded dict.
    """
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


# ---------------------------------------------------------------------------
# replay_run — main entry point
# ---------------------------------------------------------------------------


def replay_run(trace_path: str | Path) -> ReplayResult:
    """Load a trace JSONL, drive loop.py offline, and compare decisions.

    Args:
        trace_path: Path to a JSONL file. First line is a Run JSON; subsequent
                    lines are AnyEvent JSON (same format TraceWriter writes).

    Returns:
        ReplayResult describing whether every decision step matched.
    """
    path = Path(trace_path)
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]

    # Parse header Run + event stream
    run = Run.model_validate_json(lines[0])
    events: list[AnyEvent] = [_any_event_adapter.validate_json(ln) for ln in lines[1:]]

    # Extract recorded decisions (kind=="decision"), sorted by seq
    recorded_decisions: list[DecisionEvent] = sorted(
        (e for e in events if isinstance(e, DecisionEvent)),
        key=lambda e: e.seq,
    )

    # Extract decide LLM calls, sorted by seq → build ChatResponse sequence
    decide_llm_calls: list[LLMCallEvent] = sorted(
        (e for e in events if isinstance(e, LLMCallEvent) and e.purpose == "decide"),
        key=lambda e: e.seq,
    )
    responses: list[ChatResponse] = [
        _response_from_recorded(lc.response) for lc in decide_llm_calls
    ]

    # Drive loop offline
    stub_browser = StubBrowser()
    stub_llm = StubLLMClient(responses)

    loop(
        task=run.task,
        browser=stub_browser,
        llm_client=stub_llm,
        max_steps=len(recorded_decisions) + 2,
    )

    # Compare: for each consumed ChatResponse, extract the primary tool call
    # and diff against the corresponding recorded DecisionEvent.
    replayed_pairs: list[tuple[str, dict]] = []
    for cr in stub_llm.responses_consumed:
        if cr.tool_calls:
            tc = cr.tool_calls[0]
            try:
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError:
                args = {}
            replayed_pairs.append((tc.name, args))
        else:
            # No tool call in this response (e.g. noop exhausted response)
            replayed_pairs.append(("", {}))

    steps = min(len(recorded_decisions), len(replayed_pairs))

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

    # Check count mismatch (more recorded than replayed, or vice versa)
    if len(recorded_decisions) != len(replayed_pairs):
        # Find the first excess/missing step
        if len(recorded_decisions) > len(replayed_pairs):
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
        else:
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
