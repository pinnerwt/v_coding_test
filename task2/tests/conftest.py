from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    for var in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield


def _start_fixture_server() -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIXTURES_DIR), **kwargs)

        def log_message(self, format, *args):  # noqa: A002 - signature dictated by stdlib
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, thread, f"http://{host}:{port}"


def _stop_fixture_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    try:
        server.shutdown()
    finally:
        try:
            server.server_close()
        finally:
            thread.join(timeout=5)


@pytest.fixture(scope="session")
def fixture_server() -> Iterator[str]:
    server, thread, url = _start_fixture_server()
    try:
        yield url
    finally:
        _stop_fixture_server(server, thread)


@pytest.fixture
def fixture_server_factory() -> Iterator[Callable[[], str]]:
    """Function-scoped factory yielding a callable that starts a fresh fixture server.

    Each invocation returns a new origin (different random port) so tests can verify
    origin-scoping semantics. All servers spawned through the factory are torn down
    automatically when the test completes.
    """
    started: list[tuple[ThreadingHTTPServer, threading.Thread]] = []

    def _factory() -> str:
        server, thread, url = _start_fixture_server()
        started.append((server, thread))
        return url

    try:
        yield _factory
    finally:
        for server, thread in started:
            _stop_fixture_server(server, thread)


@pytest.fixture(scope="session")
def playwright_chromium() -> Iterator:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()
