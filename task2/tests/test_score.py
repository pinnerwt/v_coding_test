from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "results"
_SAMPLE_RESULTS = _FIXTURES_DIR / "sample_results.json"
_GOLDEN_SNAPSHOT = _FIXTURES_DIR / "sample_results_scoreboard.md"
_SCORE_MD = Path(__file__).parent.parent.parent / ".claude" / "commands" / "score.md"


def _run_score(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/score.py", *args],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
    )


def test_score_produces_table_and_keywords():
    result = _run_score(str(_SAMPLE_RESULTS))
    assert result.returncode == 0, result.stderr
    assert "|" in result.stdout
    assert "succeeded" in result.stdout
    assert "p50:" in result.stdout


def test_score_has_total_usd_and_tokens():
    result = _run_score(str(_SAMPLE_RESULTS))
    assert result.returncode == 0, result.stderr
    assert "Total USD:" in result.stdout
    assert "Total tokens:" in result.stdout


def test_score_has_tier_table():
    result = _run_score(str(_SAMPLE_RESULTS))
    assert result.returncode == 0, result.stderr
    assert "| Tier |" in result.stdout


def test_score_p50_p95_computation():
    from scripts.score import _percentile

    values = [100, 200, 800]
    assert _percentile(values, 50) == 200
    assert _percentile(values, 95) == 800


def test_score_generate_scoreboard_importable():
    from scripts.score import generate_scoreboard

    data = json.loads(_SAMPLE_RESULTS.read_text())
    output = generate_scoreboard(data)
    assert "succeeded" in output
    assert "p50:" in output
    assert "|" in output


def test_score_golden_snapshot_matches():
    if not _GOLDEN_SNAPSHOT.exists():
        pytest.skip("golden snapshot not yet captured — run task 5.6 first")
    result = _run_score(str(_SAMPLE_RESULTS))
    actual = "\n".join(line.rstrip() for line in result.stdout.splitlines())
    expected = "\n".join(line.rstrip() for line in _GOLDEN_SNAPSHOT.read_text().splitlines())
    assert actual == expected


def test_score_update_readme_splices_between_sentinels(tmp_path):
    from scripts.score import update_readme

    readme = tmp_path / "README.md"
    readme.write_text(
        "# Title\n\n<!-- SCOREBOARD:BEGIN -->\nstale content\n<!-- SCOREBOARD:END -->\n\nfooter\n"
    )
    data = json.loads(_SAMPLE_RESULTS.read_text())
    update_readme(data, readme_path=readme)
    content = readme.read_text()
    assert "<!-- SCOREBOARD:BEGIN -->" in content
    assert "<!-- SCOREBOARD:END -->" in content
    assert "stale content" not in content
    assert "succeeded" in content
    assert "footer" in content


def test_score_update_readme_idempotent(tmp_path):
    from scripts.score import update_readme

    readme = tmp_path / "README.md"
    readme.write_text("# Title\n\n<!-- SCOREBOARD:BEGIN -->\nstale\n<!-- SCOREBOARD:END -->\n")
    data = json.loads(_SAMPLE_RESULTS.read_text())
    update_readme(data, readme_path=readme)
    content_first = readme.read_text()
    update_readme(data, readme_path=readme)
    content_second = readme.read_text()
    assert content_first == content_second


def test_score_update_readme_appends_when_no_sentinels(tmp_path):
    from scripts.score import update_readme

    readme = tmp_path / "README.md"
    readme.write_text("# Title\n\nSome content.\n")
    data = json.loads(_SAMPLE_RESULTS.read_text())
    update_readme(data, readme_path=readme)
    content = readme.read_text()
    assert "<!-- SCOREBOARD:BEGIN -->" in content
    assert "<!-- SCOREBOARD:END -->" in content
    assert "succeeded" in content


def test_score_has_recorded_at_footer():
    from scripts.score import generate_scoreboard

    data = json.loads(_SAMPLE_RESULTS.read_text())
    output = generate_scoreboard(data)
    last_lines = [ln for ln in output.splitlines() if ln.strip()]
    assert last_lines[-1] == f"Recorded at: {data['run_at']}"


def test_score_skipped_excluded_from_summary(tmp_path):
    from scripts.score import generate_scoreboard

    data = {
        "run_at": "2026-04-26T00:00:00+00:00",
        "cases": [
            {
                "id": "c1",
                "status": "succeeded",
                "steps": 1,
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "latency_ms_total": 200,
                "latency_ms_per_step": [200],
                "step_breakdown": [],
            },
            {
                "id": "c2",
                "status": "skipped",
                "steps": 0,
                "usd": 0.0,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms_total": 0,
                "latency_ms_per_step": [],
                "step_breakdown": [],
            },
        ],
    }
    output = generate_scoreboard(data)
    assert "1/1" in output
    assert "p50: 200ms" in output


def test_find_latest_results_returns_most_recent(tmp_path):
    from scripts.score import _find_latest_results

    f1 = tmp_path / "20270101_000000.json"
    f1.write_text(json.dumps({"run_at": "2027-01-01", "cases": []}))
    time.sleep(0.05)
    f2 = tmp_path / "20260101_000000.json"
    f2.write_text(json.dumps({"run_at": "2026-01-01", "cases": []}))

    result = _find_latest_results(tmp_path)
    assert result.name == "20260101_000000.json"


def test_score_no_arg_uses_latest_results(tmp_path):
    from scripts.score import _find_latest_results, generate_scoreboard

    results_dir = tmp_path / "eval" / "results"
    results_dir.mkdir(parents=True)

    new_content = {
        "run_at": "2026-04-26T03:27:29+00:00",
        "cases": [
            {
                "id": "c1",
                "status": "succeeded",
                "steps": 1,
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "latency_ms_total": 200,
                "latency_ms_per_step": [200],
                "step_breakdown": [],
            }
        ],
    }
    (results_dir / "20260426_032729.json").write_text(json.dumps(new_content))
    time.sleep(0.05)
    old_content = {"run_at": "2026-01-01T00:00:00+00:00", "cases": []}
    (results_dir / "20270101_120000.json").write_text(json.dumps(old_content))

    latest = _find_latest_results(results_dir)
    assert latest.name == "20270101_120000.json"
    data = json.loads(latest.read_text())
    output = generate_scoreboard(data)
    assert "2026-01-01" in output


def test_score_update_readme_default_path_is_task2_readme(tmp_path, monkeypatch):
    from scripts.score import main

    task2_readme = Path(__file__).parent.parent / "README.md"
    original = task2_readme.read_text() if task2_readme.exists() else None
    try:
        monkeypatch.chdir(tmp_path)
        main([str(_SAMPLE_RESULTS), "--update-readme"])
        assert not (tmp_path / "README.md").exists()
        assert task2_readme.exists()
        sample_run_at = json.loads(_SAMPLE_RESULTS.read_text())["run_at"]
        post = task2_readme.read_text()
        assert sample_run_at in post
        assert post != original
    finally:
        if original is not None:
            task2_readme.write_text(original)


def test_score_skill_file_exists():
    assert _SCORE_MD.exists(), f"score skill not found at {_SCORE_MD}"


def test_score_skill_invokes_score_py():
    content = _SCORE_MD.read_text()
    assert "uv run python scripts/score.py" in content


def test_score_skill_under_30_lines():
    content = _SCORE_MD.read_text()
    assert len(content.splitlines()) < 30


# ---------------------------------------------------------------------------
# Task 3.1: generate_scoreboard includes mechanism columns (RED until 7.1)
# ---------------------------------------------------------------------------


def test_generate_scoreboard_mechanism_columns_in_header():
    from scripts.score import generate_scoreboard

    data = {
        "run_at": "2026-04-27T00:00:00+00:00",
        "cases": [
            {
                "id": "c1",
                "status": "succeeded",
                "steps": 2,
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "latency_ms_total": 200,
                "latency_ms_per_step": [200],
                "step_breakdown": [],
                "escalations": [
                    {
                        "from_tier": "L1_ax",
                        "to_tier": "L2_dom",
                        "intent": "x",
                        "reason": "zero_matches",
                    }
                ],
                "replans": 0,
                "cache_events": {"hits": 0, "invalidations": 0, "misses": 0},
            }
        ],
    }
    output = generate_scoreboard(data)
    assert "Escalations" in output
    assert "Replans" in output
    assert "Cache Inv." in output
    assert "| 1 | 0 | 0 |" in output


# ---------------------------------------------------------------------------
# Task 3.2: generate_scoreboard mechanism firing rates block (RED until 7.2)
# ---------------------------------------------------------------------------


def test_generate_scoreboard_mechanism_firing_rates_block():
    from scripts.score import generate_scoreboard

    data = {
        "run_at": "2026-04-27T00:00:00+00:00",
        "cases": [
            {
                "id": "c1",
                "status": "succeeded",
                "steps": 1,
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "latency_ms_total": 200,
                "latency_ms_per_step": [200],
                "step_breakdown": [],
                "escalations": [],
                "replans": 1,
                "cache_events": {"hits": 0, "invalidations": 0, "misses": 0},
            },
            {
                "id": "c2",
                "status": "succeeded",
                "steps": 1,
                "usd": 0.001,
                "l_tier_counts": {},
                "validators": [],
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "latency_ms_total": 200,
                "latency_ms_per_step": [200],
                "step_breakdown": [],
                "escalations": [],
                "replans": 0,
                "cache_events": {"hits": 0, "invalidations": 0, "misses": 0},
            },
        ],
    }
    output = generate_scoreboard(data)
    assert "Mechanism firing rates" in output
    assert "L1→L2 escalation" in output
    assert "| Replan | 1/2 |" in output
    assert "Cache invalidation" in output


# ---------------------------------------------------------------------------
# Task 3.3 (part): backward compat — cases without new fields still work
# ---------------------------------------------------------------------------


def test_generate_scoreboard_backward_compat_missing_mechanism_fields():
    from scripts.score import generate_scoreboard

    data = json.loads(_SAMPLE_RESULTS.read_text())
    output = generate_scoreboard(data)
    assert "succeeded" in output
