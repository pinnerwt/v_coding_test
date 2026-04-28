from __future__ import annotations

import json

import pytest


def _write_results(tmp_path, cases: list[dict]) -> str:
    data = {"run_at": "2026-01-01T00:00:00+00:00", "cases": cases}
    p = tmp_path / "results.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_a_canary_failed_exits_1(tmp_path, capsys):
    from scripts.canary_gate import main

    path = _write_results(
        tmp_path,
        [{"id": "fixture-heading", "canary": True, "status": "failed"}],
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--results", path])
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "fixture-heading" in out


def test_b_all_canaries_pass_non_canary_failed_exits_0_with_warning(tmp_path, capsys):
    from scripts.canary_gate import main

    path = _write_results(
        tmp_path,
        [
            {"id": "fixture-heading", "canary": True, "status": "succeeded"},
            {"id": "fixture-count", "canary": True, "status": "succeeded"},
            {"id": "live-search-extract", "canary": False, "status": "failed"},
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--results", path])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "live-search-extract" in out


def test_c_no_canary_cases_exits_0_with_notice(tmp_path, capsys):
    from scripts.canary_gate import main

    path = _write_results(
        tmp_path,
        [{"id": "live-search-extract", "canary": False, "status": "failed"}],
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--results", path])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "no canary" in out.lower()


def test_d_canary_skipped_exits_1(tmp_path, capsys):
    from scripts.canary_gate import main

    path = _write_results(
        tmp_path,
        [
            {
                "id": "fixture-heading",
                "canary": True,
                "status": "skipped",
                "skip_reason": "live_disabled",
            }
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--results", path])
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "fixture-heading" in out


def test_e_all_pass_exits_0_without_warning(tmp_path, capsys):
    from scripts.canary_gate import main

    path = _write_results(
        tmp_path,
        [
            {"id": "fixture-heading", "canary": True, "status": "succeeded"},
            {"id": "fixture-count", "canary": True, "status": "succeeded"},
            {"id": "live-search-extract", "canary": False, "status": "succeeded"},
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--results", path])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "WARNING" not in out


def test_missing_results_arg_exits_nonzero(capsys):
    from scripts.canary_gate import main

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
