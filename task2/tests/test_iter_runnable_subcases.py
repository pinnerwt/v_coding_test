from __future__ import annotations

from scripts.eval import iter_runnable_subcases

_BASE_CASE = {
    "id": "base",
    "domain": "example",
    "category": "test",
    "task": "do something",
    "expect": {"schema": {"result": "str"}},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
}


def test_shared_cache_identity_across_variants():
    """Two variants with shared_cache=True yield the same LocatorCache instance and correct ids."""
    case = {
        **_BASE_CASE,
        "fixture": True,
        "fixture_path": __file__,
        "variants": ["v1", "v2"],
        "shared_cache": True,
    }
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 2
    c1, cache1, skip1 = results[0]
    c2, cache2, skip2 = results[1]
    assert skip1 is None
    assert skip2 is None
    assert cache1 is not None
    assert cache1 is cache2
    assert c1["id"] == "base-v1"
    assert c2["id"] == "base-v2"


def test_live_disabled_skip():
    """Live-only case with live=False yields one tuple with skip_reason='live_disabled'."""
    case = {**_BASE_CASE}
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 1
    _c, cache, skip_reason = results[0]
    assert skip_reason == "live_disabled"
    assert cache is None


def test_fixture_missing_skip(tmp_path):
    """fixture_path pointing to a non-existent path yields skip_reason='fixture_missing'."""
    case = {
        **_BASE_CASE,
        "fixture": True,
        "fixture_path": str(tmp_path / "nonexistent.html"),
    }
    results = list(iter_runnable_subcases([case], live=True))
    assert len(results) == 1
    _c, cache, skip_reason = results[0]
    assert skip_reason == "fixture_missing"
    assert cache is None


def test_non_variantized_case_yields_once():
    """Non-variantized fixture case yields one tuple with skip_reason=None and shared_cache=None."""
    case = {**_BASE_CASE, "fixture": True}
    results = list(iter_runnable_subcases([case], live=True))
    assert len(results) == 1
    yielded_case, cache, skip_reason = results[0]
    assert skip_reason is None
    assert cache is None
    assert yielded_case is case


def test_variants_without_shared_cache_yield_none_for_cache():
    """Variants without shared_cache key yield two tuples both with shared_cache=None."""
    case = {
        **_BASE_CASE,
        "fixture": True,
        "fixture_path": __file__,
        "variants": ["v1", "v2"],
    }
    results = list(iter_runnable_subcases([case], live=True))
    assert len(results) == 2
    for _c, cache, skip_reason in results:
        assert cache is None
        assert skip_reason is None
