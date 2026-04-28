from __future__ import annotations

import os
from pathlib import Path

from scripts.eval import _resolve_fixture_url, iter_runnable_subcases

_REPO_ROOT = Path(__file__).resolve().parents[2]

_BASE_CASE = {
    "id": "base",
    "domain": "example",
    "category": "test",
    "task": "do something",
    "expect": {"schema": {"result": "str"}},
    "budget": {"steps": 5, "usd": 0.05, "seconds": 30},
}


def test_resolve_fixture_path_returns_file_url_under_repo_root():
    fixture_path = "task2/tests/fixtures/correction_l1_miss.html"
    result = _resolve_fixture_url(fixture_path)
    assert result.startswith("file://")
    assert str(_REPO_ROOT) in result
    assert result.endswith(fixture_path)


def test_iter_runnable_subcases_fixture_existence_check_is_repo_root_anchored(
    tmp_path, monkeypatch
):
    case = {
        **_BASE_CASE,
        "id": "fp-anchor",
        "fixture": True,
        "fixture_path": "task2/tests/fixtures/correction_l1_miss.html",
    }
    monkeypatch.chdir(tmp_path)
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 1
    _sub_case, _cache, skip_reason = results[0]
    assert skip_reason is None, (
        f"expected fixture_path to resolve via REPO_ROOT regardless of cwd ({os.getcwd()!r}), "
        f"got skip_reason={skip_reason!r}"
    )


def test_iter_runnable_subcases_missing_variant_fixture_path_yields_fixture_missing():
    case = {
        **_BASE_CASE,
        "id": "missing-variant",
        "fixture": True,
        "variants": ["v1"],
        "variant_fixture_paths": {
            "v1": "task2/tests/fixtures/does/not/exist.html",
        },
    }
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 1
    _sub_case, _cache, skip_reason = results[0]
    assert skip_reason == "fixture_missing", (
        "expected variant fixture path to be checked for existence; "
        f"got skip_reason={skip_reason!r}"
    )


def test_iter_runnable_subcases_resolves_variant_fixture_paths():
    case = {
        **_BASE_CASE,
        "fixture": True,
        "variants": ["v1", "v2"],
        "variant_fixture_paths": {
            "v1": "task2/tests/fixtures/drift/submit-form/v1/index.html",
            "v2": "task2/tests/fixtures/drift/submit-form/v2/index.html",
        },
    }
    results = list(iter_runnable_subcases([case], live=False))
    assert len(results) == 2
    for sub_case, _cache, skip_reason in results:
        assert skip_reason is None
        assert "fixture_url" in sub_case
        assert sub_case["fixture_url"].startswith("file://")
        variant = sub_case["id"].split("-")[-1]
        assert case["variant_fixture_paths"][variant] in sub_case["fixture_url"]
