from __future__ import annotations

import pytest

from agent.browser import (
    Browser,
    BrowserClosed,
    BrowserError,
    ElementNotFound,
    NavigationError,
)


def test_goto_and_read_h1(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
        assert b.read("h1") == "Hello, world"


def test_read_strips_whitespace(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/whitespace.html")
        assert b.read("h1") == "Hello"


def test_read_returns_first_match_for_multiple(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
        assert b.read("p") == "first"


def test_read_raises_element_not_found(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
        with pytest.raises(ElementNotFound) as excinfo:
            b.read(".does-not-exist")
        assert ".does-not-exist" in str(excinfo.value)


def test_goto_raises_navigation_error(playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        with pytest.raises(NavigationError) as excinfo:
            b.goto("http://127.0.0.1:1/never-listening")
        assert "http://127.0.0.1:1/never-listening" in str(excinfo.value)


def test_context_manager_cleans_up_on_exception(playwright_chromium):
    with pytest.raises(RuntimeError, match="boom"):
        with Browser(playwright_browser=playwright_chromium) as b:
            assert b is not None
            raise RuntimeError("boom")


def test_calls_after_close_raise_browser_closed(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
    with pytest.raises(BrowserClosed):
        b.read("h1")
    with pytest.raises(BrowserClosed):
        b.goto(f"{fixture_server}/index.html")


def test_exception_hierarchy():
    assert issubclass(NavigationError, BrowserError)
    assert issubclass(ElementNotFound, BrowserError)
    assert issubclass(BrowserClosed, BrowserError)
