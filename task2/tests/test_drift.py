from __future__ import annotations

from agent.browser import Browser
from agent.locate import LocateResult, locate


def test_v1_resolves_at_l1(playwright_chromium, fixture_server):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/drift/submit-form/v1/index.html")
        result = locate(b._page, "Submit button")
        assert result.tier == "L1_ax"
        assert result.confidence == 1.0


def test_v2_resolves_at_l2(playwright_chromium, fixture_server):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/drift/submit-form/v2/index.html")
        result = locate(b._page, "Submit button")
        assert result.tier == "L2_dom"
        assert result.confidence == 0.7


def test_same_intent_both_variants_succeed(playwright_chromium, fixture_server):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/drift/submit-form/v1/index.html")
        r1 = locate(b._page, "Submit button")
        b.goto(f"{fixture_server}/drift/submit-form/v2/index.html")
        r2 = locate(b._page, "Submit button")
        assert isinstance(r1, LocateResult)
        assert isinstance(r2, LocateResult)
        assert r1.tier != r2.tier
