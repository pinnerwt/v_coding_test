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


def test_shared_cache_identity_across_variants(tmp_path):
    fixture = tmp_path / "present.html"
    fixture.touch()
    case = {
        **_BASE_CASE,
        "fixture": True,
        "fixture_path": str(fixture),
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
    case = {**_BASE_CASE}
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 1
    _c, cache, skip_reason = results[0]
    assert skip_reason == "live_disabled"
    assert cache is None


def test_fixture_missing_skip(tmp_path):
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
    case = {**_BASE_CASE, "fixture": True}
    results = list(iter_runnable_subcases([case], live=True))
    assert len(results) == 1
    yielded_case, cache, skip_reason = results[0]
    assert skip_reason is None
    assert cache is None
    assert yielded_case is case


def test_variants_without_shared_cache_yield_none_for_cache(tmp_path):
    fixture = tmp_path / "present.html"
    fixture.touch()
    case = {
        **_BASE_CASE,
        "fixture": True,
        "fixture_path": str(fixture),
        "variants": ["v1", "v2"],
    }
    results = list(iter_runnable_subcases([case], live=True))
    assert len(results) == 2
    for _c, cache, skip_reason in results:
        assert cache is None
        assert skip_reason is None


def test_variant_fixture_urls_injected_per_variant():
    case = {
        **_BASE_CASE,
        "fixture": True,
        "variants": ["v1", "v2"],
        "variant_fixture_urls": {
            "v1": "data:text/html,<button>Submit</button>",
            "v2": "data:text/html,<div class=btn>Submit</div>",
        },
    }
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 2
    c1, _cache1, skip1 = results[0]
    c2, _cache2, skip2 = results[1]
    assert skip1 is None
    assert skip2 is None
    assert c1["fixture_url"] == "data:text/html,<button>Submit</button>"
    assert c2["fixture_url"] == "data:text/html,<div class=btn>Submit</div>"
