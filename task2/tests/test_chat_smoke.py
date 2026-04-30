from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

_TASK2_DIR = Path(__file__).parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"server not ready at {url}")


def _start_uvicorn(port: int, db_path: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "SESSIONS_FAKE_LOOP": "1",
        "DB_PATH": str(db_path),
        "LLM_BASE_URL": "http://stub.invalid",
        "LLM_MODEL": "stub",
    }
    return subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "api.server:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(_TASK2_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture
def smoke_server(tmp_path):
    port = _free_port()
    proc = _start_uvicorn(port, tmp_path / "smoke.db")
    base = f"http://localhost:{port}"
    try:
        _wait_ready(f"{base}/chat")
        yield base
    finally:
        _stop(proc)


def test_chat_smoke_ask_user_round_trip(smoke_server, playwright_chromium):
    context = playwright_chromium.new_context()
    page = context.new_page()
    try:
        page.goto(f"{smoke_server}/chat")
        page.fill("#task-input", "find me a hotel")
        page.click("#task-submit")

        page.wait_for_selector("#answer-form:not([hidden])", timeout=10_000)
        page.wait_for_selector("#messages .msg.agent", timeout=5_000)
        question = page.text_content("#messages .msg.agent") or ""
        assert "destination" in question.lower(), question
        assert page.get_attribute("#status", "data-status") == "awaiting_user"

        page.fill("#answer-input", "Tokyo")
        page.click("#answer-submit")

        page.wait_for_function(
            "document.querySelector('#status').dataset.status === 'done'",
            timeout=10_000,
        )

        msgs = page.text_content("#messages") or ""
        assert "Tokyo" in msgs, msgs
        assert "find me a hotel" in msgs, msgs

        events_text = page.text_content("#events") or ""
        assert "terminal: done" in events_text, events_text
    finally:
        context.close()


def test_chat_smoke_no_question_path(smoke_server):
    """If the agent never asks, frontend still gets a final result via polling."""
    r = httpx.post(f"{smoke_server}/sessions", json={"task": "anything"}, timeout=5)
    assert r.status_code == 200
    run_id = r.json()["id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        s = httpx.get(f"{smoke_server}/sessions/{run_id}", timeout=2).json()
        if s["status"] == "awaiting_user":
            httpx.post(
                f"{smoke_server}/sessions/{run_id}/answer",
                json={"answer": "Paris"},
                timeout=2,
            )
            break
        time.sleep(0.1)

    deadline = time.time() + 5
    final = None
    while time.time() < deadline:
        s = httpx.get(f"{smoke_server}/sessions/{run_id}", timeout=2).json()
        if s["status"] == "done":
            final = s
            break
        time.sleep(0.1)
    assert final is not None
    assert final["result"]["answer"] == "Paris"
