from __future__ import annotations

import hashlib

import pytest

from agent.browser import Browser
from agent.locate import (
    IntentParseError,
    LocateError,
    LocateResult,
    LocatorMiss,
    locate,
    locate_l1,
    parse_intent,
)


def test_exception_hierarchy():
    assert issubclass(LocatorMiss, LocateError)
    assert issubclass(IntentParseError, LocateError)


def test_locator_miss_constrains_reason():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    assert miss.reason == "zero_matches"
    assert miss.match_count == 0

    miss = LocatorMiss(reason="ambiguous", match_count=3)
    assert miss.reason == "ambiguous"
    assert miss.match_count == 3

    with pytest.raises(ValueError):
        LocatorMiss(reason="bogus", match_count=0)


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("Submit button", ("button", "Submit")),
        ("the Submit button", ("button", "Submit")),
        ("a Save link", ("link", "Save")),
        ("an Edit button", ("button", "Edit")),
        ("Email address textbox", ("textbox", "Email address")),
        ("Accept checkbox", ("checkbox", "Accept")),
        ("Welcome heading", ("heading", "Welcome")),
        ("button", ("button", None)),
        ("THE Submit BUTTON", ("button", "Submit")),
    ],
)
def test_parse_intent_happy_paths(intent, expected):
    assert parse_intent(intent) == expected


def test_parse_intent_unknown_role():
    with pytest.raises(IntentParseError) as excinfo:
        parse_intent("Submit widget")
    assert "widget" in str(excinfo.value)


def test_parse_intent_unknown_role_includes_full_intent():
    with pytest.raises(IntentParseError) as excinfo:
        parse_intent("do the thing")
    assert "do the thing" in str(excinfo.value)


def test_parse_intent_empty():
    with pytest.raises(IntentParseError):
        parse_intent("   ")
    with pytest.raises(IntentParseError):
        parse_intent("")


def test_locate_l1_unique_match(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate_l1(b._page, role="button", name="Submit")
        assert isinstance(result, LocateResult)
        assert result.tier == "L1_ax"
        assert result.role == "button"
        assert result.name == "Submit"
        assert result.confidence == 1.0
        assert result.ax_fingerprint
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        assert (loc.first.text_content() or "").strip() == "Submit"
        tag = loc.first.evaluate("el => el.tagName")
        assert tag == "BUTTON"


def test_locate_l1_zero_matches(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l1(b._page, role="button", name="Nonexistent")
        assert excinfo.value.reason == "zero_matches"
        assert excinfo.value.match_count == 0


def test_locate_l1_ambiguous(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l1(b._page, role="button", name="Save")
        assert excinfo.value.reason == "ambiguous"
        assert excinfo.value.match_count == 2


def test_locate_l1_non_semantic_invisible(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1_div_only.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l1(b._page, role="button", name="Submit")
        assert excinfo.value.reason == "zero_matches"


def test_locate_l1_bare_role(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate_l1(b._page, role="heading", name=None)
        assert result.tier == "L1_ax"
        assert result.role == "heading"
        assert result.name is None


def test_ax_fingerprint_deterministic(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        a = locate_l1(b._page, role="button", name="Submit")
        c = locate_l1(b._page, role="button", name="Submit")
        assert a.ax_fingerprint == c.ax_fingerprint


def test_locate_orchestrator_runs_l1(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate(b._page, "Submit button")
        assert result.tier == "L1_ax"
        assert result.role == "button"
        assert result.name == "Submit"


def test_locate_orchestrator_propagates_intent_error(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        with pytest.raises(IntentParseError):
            locate(b._page, "do the thing")


def test_locator_selector_escapes_quoted_names(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1_quoted.html")
        result = locate_l1(b._page, role="button", name='Say "Hi"')
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        assert (loc.first.text_content() or "").strip() == 'Say "Hi"'


def test_ax_fingerprint_uses_matched_accessible_name(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1_substring.html")
        full = locate_l1(b._page, role="button", name="Save draft")
        sub = locate_l1(b._page, role="button", name="Save")
        assert full.ax_fingerprint == sub.ax_fingerprint


def test_ax_fingerprint_resolves_label_for_association(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1_label_for.html")
        labelled = locate_l1(b._page, role="textbox", name="Email address")
        b.goto(f"{fixture_server}/locate_l1_labelledby.html")
        labelledby = locate_l1(b._page, role="textbox", name="Phone number")
    empty = hashlib.sha256(b"textbox:").hexdigest()
    assert labelled.ax_fingerprint != empty
    assert labelledby.ax_fingerprint != empty
    assert labelled.ax_fingerprint != labelledby.ax_fingerprint


def test_parse_intent_list_role():
    assert parse_intent("list") == ("list", None)


def test_parse_intent_listitem_role():
    assert parse_intent("listitem") == ("listitem", None)


def test_parse_intent_items_listitem():
    assert parse_intent("Items listitem") == ("listitem", "Items")


def test_parse_intent_items_still_raises():
    with pytest.raises(IntentParseError) as excinfo:
        parse_intent("items")
    assert "items" in str(excinfo.value)
