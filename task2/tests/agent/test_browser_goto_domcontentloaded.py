from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent.browser import Browser, NavigationError


def _start_server(
    handler_cls: type[BaseHTTPRequestHandler],
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, thread, f"http://{host}:{port}"


def _stop_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    try:
        server.shutdown()
    finally:
        try:
            server.server_close()
        finally:
            thread.join(timeout=5)


@pytest.fixture
def slow_subresource_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - signature dictated by stdlib
            if self.path == "/slow.png":
                time.sleep(8)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'<!doctype html><html><body><h1>hi</h1><img src="/slow.png"></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 - signature dictated by stdlib
            return

    server, thread, url = _start_server(Handler)
    try:
        yield url
    finally:
        _stop_server(server, thread)


@pytest.fixture
def hanging_html_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - signature dictated by stdlib
            time.sleep(20)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):  # noqa: A002 - signature dictated by stdlib
            return

    server, thread, url = _start_server(Handler)
    try:
        yield url
    finally:
        _stop_server(server, thread)


def test_goto_returns_after_domcontentloaded_when_subresource_hangs(
    playwright_chromium, slow_subresource_server
):
    with Browser(playwright_browser=playwright_chromium) as b:
        start = time.monotonic()
        b.goto(slow_subresource_server + "/")
        elapsed = time.monotonic() - start
    assert elapsed < 3.0, f"goto blocked on subresource (elapsed={elapsed:.2f}s)"


def test_goto_raises_navigation_error_on_dcl_timeout(playwright_chromium, hanging_html_server):
    with Browser(playwright_browser=playwright_chromium) as b:
        start = time.monotonic()
        with pytest.raises(NavigationError):
            b.goto(hanging_html_server + "/")
        elapsed = time.monotonic() - start
    assert elapsed < 31.0, f"goto did not honor 15s timeout (elapsed={elapsed:.2f}s)"


def test_goto_passes_wait_until_domcontentloaded_arg(playwright_chromium):
    captured: list[dict] = []

    with Browser(playwright_browser=playwright_chromium) as b:

        def fake_goto(url, **kwargs):
            captured.append(dict(kwargs))

        b._page.goto = fake_goto
        b.goto("https://example.com")

    assert len(captured) == 1
    assert captured[0]["wait_until"] == "domcontentloaded"
    assert captured[0]["timeout"] == 15000
