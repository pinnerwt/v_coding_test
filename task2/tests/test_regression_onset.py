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

    reg_section = text.split("## Regressions")[1].split("##")[0]
    row = next(line for line in reg_section.splitlines() if "fixture-heading" in line)
    assert "run_b" in row
    assert "run_a" in row


def test_handles_empty_benchmark_root(tmp_path):
    root = tmp_path / "bench"
    root.mkdir()
    out = tmp_path / "report.md"

    from scripts.regression_onset import main

    code = main(["--benchmark-root", str(root), "--output", str(out)])
    assert code == 0
    text = out.read_text()
    assert "## Regressions" in text
    assert "## Never Passed" in text
    assert "## Stable" in text


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


def test_never_passed_case_in_never_passed_section_not_regressions(tmp_path):
    root = tmp_path / "bench"
    out = tmp_path / "report.md"

    _write_run(
        root / "run_a" / "results.json",
        "2026-04-26T01:00:00+00:00",
        [_case("correction-l1-miss-l2-hit", "failed")],
    )
    _write_run(
        root / "run_b" / "results.json",
        "2026-04-26T02:00:00+00:00",
        [_case("correction-l1-miss-l2-hit", "failed")],
    )

    from scripts.regression_onset import main

    main(["--benchmark-root", str(root), "--output", str(out)])

    text = out.read_text()
    regressions_section = text.split("## Never Passed")[0]
    never_passed_section = text.split("## Never Passed")[1].split("## Stable")[0]

    assert "correction-l1-miss-l2-hit" not in regressions_section
    assert "correction-l1-miss-l2-hit" in never_passed_section


def test_total_runs_seen_includes_skipped_appearances(tmp_path):
    root = tmp_path / "bench"
    out = tmp_path / "report.md"

    _write_run(
        root / "run_a" / "results.json",
        "2026-04-26T01:00:00+00:00",
        [_case("never-win", "failed")],
    )
    _write_run(
        root / "run_b" / "results.json",
        "2026-04-26T02:00:00+00:00",
        [_case("never-win", "skipped")],
    )

    from scripts.regression_onset import main

    main(["--benchmark-root", str(root), "--output", str(out)])

    text = out.read_text()
    never_passed_section = text.split("## Never Passed")[1].split("## Stable")[0]
    row = next(line for line in never_passed_section.splitlines() if "never-win" in line)
    assert "| 2 |" in row
