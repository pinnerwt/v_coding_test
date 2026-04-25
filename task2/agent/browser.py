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
        self._playwright = None
        self._browser = playwright_browser
        self._context = None
        self._page = None

    def __enter__(self) -> Browser:
        try:
            if self._browser is None:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        context, playwright = self._context, self._playwright
        owned_browser = self._browser if playwright is not None else None
        self._context = None
        self._page = None
        self._playwright = None
        if playwright is not None:
            self._browser = None
        try:
            if context is not None:
                context.close()
        finally:
            try:
                if owned_browser is not None:
                    owned_browser.close()
            finally:
                if playwright is not None:
                    playwright.stop()

    def goto(self, url: str) -> None:
        if self._page is None:
            raise BrowserClosed()
        try:
            self._page.goto(url, wait_until="load")
        except PlaywrightError as e:
            raise NavigationError(f"failed to navigate to {url}: {e}") from e

    def read(self, selector: str) -> str:
        if self._page is None:
            raise BrowserClosed()
        locator = self._page.locator(selector)
        if locator.count() == 0:
            raise ElementNotFound(f"no element matched selector {selector!r}")
        text = locator.first.text_content() or ""
        return text.strip()
