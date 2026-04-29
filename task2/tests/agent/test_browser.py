from __future__ import annotations

import types
import unittest.mock

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


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_screenshot_returns_png_bytes_in_with_block(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
        png = b.screenshot()
        assert isinstance(png, bytes)
        assert len(png) > 0
        assert png.startswith(_PNG_SIGNATURE)


def test_screenshot_after_exit_raises_browser_closed(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
    with pytest.raises(BrowserClosed):
        b.screenshot()


def test_screenshot_full_page_is_at_least_viewport_sized(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
        # Shrink the viewport so the document is taller than the viewport.
        b._page.set_viewport_size({"width": 200, "height": 200})
        b._page.evaluate("() => { document.body.style.height = '4000px'; }")
        viewport_png = b.screenshot()
        full_png = b.screenshot(full_page=True)
        assert viewport_png.startswith(_PNG_SIGNATURE)
        assert full_png.startswith(_PNG_SIGNATURE)
        assert len(full_png) >= len(viewport_png)


def test_click_at_fires_document_click_handler(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b.click_at(150, 250)
        click = b._page.evaluate("() => window.__l4_click")
        assert click is not None
        assert click["x"] == 150
        assert click["y"] == 250


def test_click_at_inside_target_fires_target_handler(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b.click_at(140, 220)
        click = b._page.evaluate("() => window.__l4_click")
        assert click is not None
        assert click["target"] == "target"


def test_click_at_after_exit_raises_browser_closed(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/index.html")
    with pytest.raises(BrowserClosed):
        b.click_at(10, 20)


def test_cdp_sessions_initialized_empty():
    b = Browser()
    assert b._cdp_sessions == {}
    assert isinstance(b._cdp_sessions, dict)


def test_exit_suppresses_detach_errors_and_clears_cache(playwright_chromium):
    failing_session = types.SimpleNamespace(
        detach=unittest.mock.Mock(side_effect=RuntimeError("detach boom"))
    )
    with Browser(playwright_browser=playwright_chromium) as b:
        b._cdp_sessions[id(b._page)] = failing_session

    assert b._cdp_sessions == {}
    failing_session.detach.assert_called_once()


def test_goto_retries_once_on_transient_error(playwright_chromium):
    from playwright.sync_api import Error as PlaywrightError

    with Browser(playwright_browser=playwright_chromium) as b:
        call_count = {"n": 0}

        def fake_goto(url, wait_until):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise PlaywrightError("net::ERR_NETWORK_CHANGED")

        b._page.goto = fake_goto
        b.goto("https://example.com")
        assert call_count["n"] == 2


def test_goto_does_not_retry_non_transient_error(playwright_chromium):
    from playwright.sync_api import Error as PlaywrightError

    with Browser(playwright_browser=playwright_chromium) as b:
        call_count = {"n": 0}

        def fake_goto(url, wait_until):
            call_count["n"] += 1
            raise PlaywrightError("net::ERR_NAME_NOT_RESOLVED")

        b._page.goto = fake_goto
        with pytest.raises(NavigationError):
            b.goto("https://example.com")
        assert call_count["n"] == 1


def test_goto_raises_navigation_error_on_second_transient_failure(playwright_chromium):
    from playwright.sync_api import Error as PlaywrightError

    with Browser(playwright_browser=playwright_chromium) as b:
        call_count = {"n": 0}

        def fake_goto(url, wait_until):
            call_count["n"] += 1
            raise PlaywrightError("net::ERR_NETWORK_CHANGED")

        b._page.goto = fake_goto
        with pytest.raises(NavigationError):
            b.goto("https://example.com")
        assert call_count["n"] == 2
