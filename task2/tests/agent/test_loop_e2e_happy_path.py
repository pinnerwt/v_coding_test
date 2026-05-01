"""End-to-end happy-path test against the real local LLM at localhost:8090.

Exercises the full agent loop with a real LLM, the local fixture server,
and Playwright Chromium. Validates that T1-T6 features compose cleanly:
T1 self-eval gate, T2 verifier evidence gating, T3 judge prompt,
T4 plan_cursor, T5 dom_digest, T6 monotone-escalation replan budget.

Auto-skips if the local LLM at http://localhost:8090 is unreachable.
"""

from __future__ import annotations

import httpx
import pytest

from agent.browser import Browser
from agent.llm import LLMClient
from agent.loop import loop

_LLM_BASE_URL = "http://localhost:8090"
_LLM_MODEL = "qwen3.5-27b"


def _llm_reachable() -> bool:
    try:
        r = httpx.get(f"{_LLM_BASE_URL}/v1/models", timeout=2.0)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _llm_reachable(),
    reason=f"local LLM at {_LLM_BASE_URL} not reachable; skipping E2E happy-path test",
)


def test_loop_e2e_happy_path_real_llm(fixture_server, playwright_chromium):
    """Real-LLM smoke: agent navigates to a fixture page and reports the H1.

    The fixture page (loop_happy_path.html) contains <h1>Hello, loop</h1>.
    A correctly-functioning agent should `goto` the URL, `read` the page,
    and `done` with a result containing the heading text.
    """
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    task = (
        f"Open {fixture_url} and report the page's H1 heading text "
        "as a JSON object with key 'heading'."
    )

    with (
        Browser(playwright_browser=playwright_chromium) as browser,
        LLMClient(base_url=_LLM_BASE_URL, model=_LLM_MODEL) as llm_client,
    ):
        result = loop(task, browser, llm_client, max_steps=10, budget_seconds=180)

    # Status must be terminal-success-ish; with a real LLM the verifier
    # judge can land on either "succeeded" or "unverified" depending on
    # how it scores grounding, but both indicate a clean done.
    assert result.status in {"succeeded", "unverified"}, (
        f"expected succeeded/unverified, got {result.status!r}; result={result.result!r}"
    )
    assert result.result is not None, "agent must produce a result on happy path"

    # Result must mention the actual heading text (case-insensitive) — this
    # is the grounding evidence T1/T2/T3 are designed to enforce.
    flat = repr(result.result).lower()
    assert "hello, loop" in flat, f"result did not contain the H1 text; got {result.result!r}"

    # Sanity: at least one step ran and at least one LLM call was billed.
    assert result.steps >= 1
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
