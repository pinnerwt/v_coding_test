from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from agent.locator_cache import CacheEntry, LocatorCache, _origin_from_url

from agent.browser import Browser
from agent.llm import ChatResponse, Usage
from agent.locate import LocatorMiss, locate

# ---------------------------------------------------------------------------
# Helpers (mirrored from test_locate_l4.py)
# ---------------------------------------------------------------------------


def _ok_chat_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=[],
        finish_reason="stop",
        model="stub",
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        raw={},
    )


def _make_chat_stub(
    *, content: str | None = None, fail_if_called: bool = False
) -> Callable[..., ChatResponse]:
    calls: list[dict] = []

    def stub(messages, **kwargs):
        if fail_if_called:
            raise AssertionError("llm_chat was invoked but the test expected no call")
        calls.append({"messages": messages, "kwargs": kwargs})
        return _ok_chat_response(content if content is not None else "")

    stub.calls = calls  # type: ignore[attr-defined]
    return stub


def _entry_for(
    *,
    origin: str,
    intent: str = "Submit button",
    role: str = "button",
    name: str | None = "Submit",
    selector: str = 'role=button[name="Submit" i]',
    ax_fingerprint: str = "abc123",
    confidence: float = 1.0,
    tier: str = "L1_ax",
    coords: tuple[int, int] | None = None,
    written_at_utc: str = "2026-04-25T12:00:00Z",
) -> CacheEntry:
    return CacheEntry(
        origin=origin,
        intent=intent,
        role=role,
        name=name,
        selector=selector,
        ax_fingerprint=ax_fingerprint,
        confidence=confidence,
        tier=tier,
        coords=coords,
        written_at_utc=written_at_utc,
    )


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if scheme == "http" and (port is None or port == 80):
        return f"http://{host}"
    if scheme == "https" and (port is None or port == 443):
        return f"https://{host}"
    if port is None:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


# ---------------------------------------------------------------------------
# Section 2 — LocatorCache unit tests
# ---------------------------------------------------------------------------


def test_construct_in_memory_default():
    cache = LocatorCache()
    try:
        cache.put(_entry_for(origin="http://x"))
        assert cache.get(origin="http://x", intent="Submit button") is not None
    finally:
        cache.close()
    # Re-construct: fresh in-memory database SHALL not see the prior row.
    cache2 = LocatorCache()
    try:
        assert cache2.get(origin="http://x", intent="Submit button") is None
    finally:
        cache2.close()


def test_construct_with_file_path(tmp_path):
    db_path = tmp_path / "locator.sqlite"
    cache = LocatorCache(path=str(db_path))
    try:
        cache.put(_entry_for(origin="http://x"))
    finally:
        cache.close()
    assert db_path.exists()
    cache2 = LocatorCache(path=str(db_path))
    try:
        assert cache2.get(origin="http://x", intent="Submit button") is not None
    finally:
        cache2.close()


def test_schema_mismatch_drops_and_recreates(tmp_path):
    db_path = tmp_path / "locator.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE locator_cache (origin TEXT, intent TEXT)")
        conn.execute(
            "INSERT INTO locator_cache (origin, intent) VALUES (?, ?)",
            ("http://stale", "stale intent"),
        )
        conn.commit()
    finally:
        conn.close()

    cache = LocatorCache(path=str(db_path))
    try:
        # The legacy row SHALL be gone.
        assert cache.get(origin="http://stale", intent="stale intent") is None
        # And the new schema is in place.
        cols = {row[1] for row in cache._conn.execute("PRAGMA table_info(locator_cache)")}
        for col in (
            "origin",
            "intent",
            "role",
            "name",
            "selector",
            "ax_fingerprint",
            "confidence",
            "tier",
            "coords_x",
            "coords_y",
            "written_at_utc",
        ):
            assert col in cols
    finally:
        cache.close()


def test_constructor_ignores_locator_cache_path_env_var(monkeypatch, tmp_path):
    sentinel = tmp_path / "should_not_be_used.sqlite"
    monkeypatch.setenv("LOCATOR_CACHE_PATH", str(sentinel))

    cache = LocatorCache()
    try:
        cache.put(_entry_for(origin="http://x"))
    finally:
        cache.close()

    assert not sentinel.exists()


def test_get_on_empty_cache_returns_none():
    cache = LocatorCache()
    try:
        assert cache.get(origin="http://x", intent="Save button") is None
    finally:
        cache.close()


def test_put_then_get_round_trips():
    cache = LocatorCache()
    try:
        entry = _entry_for(
            origin="http://127.0.0.1:9000",
            intent="Submit button",
            role="button",
            name="Submit",
            selector='role=button[name="Submit" i]',
            ax_fingerprint="abc123",
            confidence=1.0,
            tier="L1_ax",
            coords=None,
            written_at_utc="2026-04-25T12:00:00Z",
        )
        cache.put(entry)
        got = cache.get(origin="http://127.0.0.1:9000", intent="Submit button")
        assert got == entry
    finally:
        cache.close()


def test_put_replaces_existing_row():
    cache = LocatorCache()
    try:
        entry_v1 = _entry_for(
            origin="http://x",
            intent="Save button",
            selector='role=button[name="Save" i]',
            ax_fingerprint="finger-v1",
        )
        entry_v2 = _entry_for(
            origin="http://x",
            intent="Save button",
            selector='role=button[name="Save" i] >> nth=2',
            ax_fingerprint="finger-v2",
        )
        cache.put(entry_v1)
        cache.put(entry_v2)
        got = cache.get(origin="http://x", intent="Save button")
        assert got == entry_v2
        (count,) = cache._conn.execute(
            "SELECT COUNT(*) FROM locator_cache WHERE origin=? AND intent=?",
            ("http://x", "Save button"),
        ).fetchone()
        assert count == 1
    finally:
        cache.close()


def test_invalidate_deletes_row():
    cache = LocatorCache()
    try:
        cache.put(_entry_for(origin="http://x", intent="Save button"))
        cache.invalidate(origin="http://x", intent="Save button")
        assert cache.get(origin="http://x", intent="Save button") is None
    finally:
        cache.close()


def test_invalidate_missing_row_is_noop():
    cache = LocatorCache()
    try:
        cache.invalidate(origin="http://nope", intent="ghost button")
    finally:
        cache.close()


def test_cache_scoped_by_origin():
    cache = LocatorCache()
    try:
        cache.put(_entry_for(origin="http://a", intent="x"))
        assert cache.get(origin="http://b", intent="x") is None
    finally:
        cache.close()


def test_cache_scoped_by_intent():
    cache = LocatorCache()
    try:
        cache.put(_entry_for(origin="http://x", intent="a"))
        assert cache.get(origin="http://x", intent="b") is None
    finally:
        cache.close()


def test_cache_entry_is_frozen():
    entry = _entry_for(origin="http://x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.origin = "http://y"  # type: ignore[misc]


def test_close_is_idempotent():
    cache = LocatorCache()
    cache.close()
    cache.close()


def test_context_manager():
    with LocatorCache() as cache:
        cache.put(_entry_for(origin="http://x"))
        assert cache.get(origin="http://x", intent="Submit button") is not None
    # Outside the with-block the connection is closed; subsequent operations raise.
    with pytest.raises(sqlite3.ProgrammingError):
        cache.get(origin="http://x", intent="Submit button")


# ---------------------------------------------------------------------------
# Section 3 — origin derivation
# ---------------------------------------------------------------------------


def test_origin_strips_default_http_port():
    assert _origin_from_url("http://example.com:80/path") == "http://example.com"


def test_origin_strips_default_https_port():
    assert _origin_from_url("https://EXAMPLE.com:443/") == "https://example.com"


def test_origin_preserves_non_default_port():
    assert _origin_from_url("http://127.0.0.1:9123/locate_l1.html") == "http://127.0.0.1:9123"


def test_origin_drops_path_query_fragment():
    assert _origin_from_url("http://x.test/a/b?q=1#f") == "http://x.test"


def test_origin_lowercases_scheme_and_host():
    assert _origin_from_url("HTTP://X.TEST/") == "http://x.test"


# ---------------------------------------------------------------------------
# Section 4 — locate() cache integration
# ---------------------------------------------------------------------------


def test_first_resolve_writes_cache_returns_l1_tier(fixture_server, playwright_chromium):
    stub = _make_chat_stub(fail_if_called=True)
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/locate_l1.html")
            origin = _origin_of(b._page.url)
            result = locate(b._page, "Submit button", llm_chat=stub, cache=cache)
        assert result.tier == "L1_ax"
        entry = cache.get(origin=origin, intent="Submit button")
        assert entry is not None
        assert entry.tier == "L1_ax"
        assert entry.selector == result.selector
        assert entry.ax_fingerprint
    finally:
        cache.close()


def test_second_resolve_hits_cache_skips_llm(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/locate_l1.html")
            origin = _origin_of(b._page.url)
            warm_stub = _make_chat_stub()
            first = locate(b._page, "Submit button", llm_chat=warm_stub, cache=cache)
            assert first.tier == "L1_ax"

            cold_stub = _make_chat_stub(fail_if_called=True)
            second = locate(b._page, "Submit button", llm_chat=cold_stub, cache=cache)
        stored = cache.get(origin=origin, intent="Submit button")
        assert stored is not None
        assert second.tier == "cache"
        assert second.selector == stored.selector
        assert second.ax_fingerprint == stored.ax_fingerprint
        assert cold_stub.calls == []  # type: ignore[attr-defined]
    finally:
        cache.close()


def test_drift_invalidates_cache_and_replaces_row(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/cache_drift.html")
            origin = _origin_of(b._page.url)
            first = locate(b._page, "Submit button", cache=cache)
            assert first.tier == "L1_ax"
            first_entry = cache.get(origin=origin, intent="Submit button")
            assert first_entry is not None

            # Rename the original button (so cached selector no longer matches)
            # AND add a NEW Submit button so L1 still resolves uniquely.
            b._page.evaluate("__rename('Send')")
            b._page.evaluate("__add('Submit')")

            second = locate(b._page, "Submit button", cache=cache)
        assert second.tier != "cache"
        assert second.tier == "L1_ax"
        replaced = cache.get(origin=origin, intent="Submit button")
        assert replaced is not None
        assert replaced.ax_fingerprint == second.ax_fingerprint
    finally:
        cache.close()


def test_removed_element_invalidates_cache_and_falls_through(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/cache_drift.html")
            origin = _origin_of(b._page.url)
            first = locate(b._page, "Submit button", cache=cache)
            assert first.tier == "L1_ax"
            assert cache.get(origin=origin, intent="Submit button") is not None

            b._page.evaluate("__remove()")
            b._page.evaluate("__add('Submit')")

            second = locate(b._page, "Submit button", cache=cache)
        assert second.tier == "L1_ax"
        replaced = cache.get(origin=origin, intent="Submit button")
        assert replaced is not None
        assert replaced.ax_fingerprint == second.ax_fingerprint
    finally:
        cache.close()


def test_origin_scoping_two_servers(fixture_server_factory, playwright_chromium):
    server_a = fixture_server_factory()
    server_b = fixture_server_factory()
    assert server_a != server_b
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{server_a}/locate_l1.html")
            origin_a = _origin_of(b._page.url)
            first = locate(b._page, "Submit button", cache=cache)
            assert first.tier == "L1_ax"

        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{server_b}/locate_l1.html")
            origin_b = _origin_of(b._page.url)
            second = locate(b._page, "Submit button", cache=cache)
        assert origin_a != origin_b
        assert second.tier != "cache"
        (rowcount,) = cache._conn.execute("SELECT COUNT(*) FROM locator_cache").fetchone()
        assert rowcount == 2
    finally:
        cache.close()


def test_intent_scoping_same_page(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/cache_two_intents.html")
            first = locate(b._page, "Submit button", cache=cache)
            assert first.tier == "L1_ax"
            second = locate(b._page, "Cancel button", cache=cache)
        assert second.tier != "cache"
        assert second.tier == "L1_ax"
        (rowcount,) = cache._conn.execute("SELECT COUNT(*) FROM locator_cache").fetchone()
        assert rowcount == 2
    finally:
        cache.close()


def test_l4_cached_entry_forced_miss_on_read(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/locate_l1.html")
            origin = _origin_of(b._page.url)
            cache.put(
                _entry_for(
                    origin=origin,
                    intent="Submit button",
                    selector="",
                    ax_fingerprint="vision-fp",
                    confidence=0.5,
                    tier="L4_vision",
                    coords=(100, 50),
                )
            )
            stub = _make_chat_stub(fail_if_called=True)
            result = locate(b._page, "Submit button", llm_chat=stub, cache=cache)
        assert result.tier == "L1_ax"
        replaced = cache.get(origin=origin, intent="Submit button")
        assert replaced is not None
        assert replaced.tier == "L1_ax"
        assert stub.calls == []  # type: ignore[attr-defined]
    finally:
        cache.close()


def test_cache_none_preserves_prior_behaviour(fixture_server, playwright_chromium):
    # Observability: if `cache` is None, agent.locator_cache must NOT be imported as a
    # side effect of `locate(...)` — otherwise we'd be paying a sqlite3 import cost on
    # every cache-less call. The lazy import inside `locate()` only fires when
    # `cache is not None`, so a fresh subprocess that imports `agent.locate` and runs
    # locate(...) without `cache=` SHALL not have `agent.locator_cache` in sys.modules.
    import subprocess
    import sys

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate(b._page, "Submit button")
    assert result.tier == "L1_ax"

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            ("import sys, agent.locate;print('agent.locator_cache' in sys.modules)"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == "False"


def test_cache_hit_does_not_call_get_by_role(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/locate_l1.html")
            warm = _make_chat_stub()
            first = locate(b._page, "Submit button", llm_chat=warm, cache=cache)
            assert first.tier == "L1_ax"
            cold = _make_chat_stub(fail_if_called=True)
            second = locate(b._page, "Submit button", llm_chat=cold, cache=cache)
        assert second.tier == "cache"
        assert cold.calls == []  # type: ignore[attr-defined]
    finally:
        cache.close()


def test_cache_failure_does_not_write_row(fixture_server, playwright_chromium):
    cache = LocatorCache()
    try:
        with Browser(playwright_browser=playwright_chromium) as b:
            b.goto(f"{fixture_server}/locate_l1.html")
            origin = _origin_of(b._page.url)
            stub = _make_chat_stub(content=json.dumps({"box": "garbage"}))
            with pytest.raises(LocatorMiss):
                locate(b._page, "Refund button", llm_chat=stub, cache=cache)
        assert cache.get(origin=origin, intent="Refund button") is None
    finally:
        cache.close()
