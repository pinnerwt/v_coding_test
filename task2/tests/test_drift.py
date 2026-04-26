from __future__ import annotations

from agent.locate import LocateResult, locate


def test_v1_resolves_at_l1(playwright_chromium, fixture_server):
    page = playwright_chromium.new_page()
    try:
        page.goto(f"{fixture_server}/drift/submit-form/v1/index.html")
        result = locate(page, "Submit button")
        assert result.tier == "L1_ax"
        assert result.confidence == 1.0
    finally:
        page.close()


def test_v2_resolves_at_l2(playwright_chromium, fixture_server):
    page = playwright_chromium.new_page()
    try:
        page.goto(f"{fixture_server}/drift/submit-form/v2/index.html")
        result = locate(page, "Submit button")
        assert result.tier == "L2_dom"
        assert result.confidence == 0.7
    finally:
        page.close()


def test_same_intent_both_variants_succeed(playwright_chromium, fixture_server):
    page = playwright_chromium.new_page()
    try:
        page.goto(f"{fixture_server}/drift/submit-form/v1/index.html")
        r1 = locate(page, "Submit button")
        page.goto(f"{fixture_server}/drift/submit-form/v2/index.html")
        r2 = locate(page, "Submit button")
        assert isinstance(r1, LocateResult)
        assert isinstance(r2, LocateResult)
        assert r1.tier != r2.tier
    finally:
        page.close()
