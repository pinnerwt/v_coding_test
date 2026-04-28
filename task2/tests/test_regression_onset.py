from __future__ import annotations

import json
from pathlib import Path


def _write_run(path: Path, run_at: str, cases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_at": run_at, "cases": cases}))


def _case(cid: str, status: str) -> dict:
    return {"id": cid, "status": status}


def test_writes_regressions_section(tmp_path):
    root = tmp_path / "bench"
    out = tmp_path / "report.md"

    _write_run(
        root / "run_a" / "results.json",
        "2026-04-26T01:00:00+00:00",
        [_case("fixture-heading", "succeeded")],
    )
    _write_run(
        root / "run_b" / "results.json",
        "2026-04-26T02:00:00+00:00",
        [_case("fixture-heading", "failed")],
    )

    from scripts.regression_onset import main

    main(["--benchmark-root", str(root), "--output", str(out)])

    text = out.read_text()
    assert "## Regressions" in text
    assert "fixture-heading" in text


def test_handles_empty_benchmark_root(tmp_path):
    root = tmp_path / "bench"
    root.mkdir()
    out = tmp_path / "report.md"

    from scripts.regression_onset import main

    code = main(["--benchmark-root", str(root), "--output", str(out)])
    assert code == 0
    text = out.read_text()
    assert "## Regressions" in text


def test_skips_underscore_dirs(tmp_path):
    root = tmp_path / "bench"
    out = tmp_path / "report.md"

    _write_run(
        root / "_trends" / "results.json",
        "2026-04-26T01:00:00+00:00",
        [_case("fixture-heading", "succeeded")],
    )
    _write_run(
        root / "master" / "results.json",
        "2026-04-26T02:00:00+00:00",
        [_case("fixture-heading", "failed")],
    )

    from scripts.regression_onset import main

    main(["--benchmark-root", str(root), "--output", str(out)])

    text = out.read_text()
    assert "_trends" not in text
