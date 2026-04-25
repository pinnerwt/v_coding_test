from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from playwright.sync_api import Browser as PlaywrightBrowser


class BrowserError(Exception):
    pass


class NavigationError(BrowserError):
    pass


class ElementNotFound(BrowserError):
    pass


class BrowserClosed(BrowserError):
    pass


class Browser:
    def __init__(self, playwright_browser: PlaywrightBrowser | None = None):
        self._owns_runtime = playwright_browser is None
        self._playwright = None
        self._browser = playwright_browser
        self._context = None
        self._page = None
        self._closed = False

    def __enter__(self) -> Browser:
        if self._owns_runtime:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._closed = True
        try:
            if self._context is not None:
                self._context.close()
        finally:
            self._context = None
            self._page = None
            if self._owns_runtime:
                try:
                    if self._browser is not None:
                        self._browser.close()
                finally:
                    self._browser = None
                    if self._playwright is not None:
                        self._playwright.stop()
                        self._playwright = None

    def goto(self, url: str) -> None:
        if self._closed or self._page is None:
            raise BrowserClosed("Browser is closed")
        try:
            self._page.goto(url, wait_until="load")
        except PlaywrightError as e:
            raise NavigationError(f"failed to navigate to {url}: {e}") from e

    def read(self, selector: str) -> str:
        if self._closed or self._page is None:
            raise BrowserClosed("Browser is closed")
        locator = self._page.locator(selector)
        if locator.count() == 0:
            raise ElementNotFound(f"no element matched selector {selector!r}")
        text = locator.first.text_content() or ""
        return text.strip()
