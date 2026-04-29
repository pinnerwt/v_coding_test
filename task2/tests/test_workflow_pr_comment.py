from __future__ import annotations

from pathlib import Path

_WORKFLOW = Path(__file__).parent.parent.parent / ".github" / "workflows" / "task2-benchmark.yml"


def _load_workflow() -> dict:
    import yaml

    return yaml.safe_load(_WORKFLOW.read_text())


def test_post_diff_step_uses_gh_api_detection():
    workflow = _load_workflow()
    steps = workflow["jobs"]["verify"]["steps"]
    step = next(s for s in steps if s.get("name") == "Post diff as PR comment")
    run = step["run"]
    assert "gh api" in run and "/comments" in run
    assert 'select(.user.login == "github-actions[bot]")' in run


def test_post_diff_step_uses_gh_api_patch():
    workflow = _load_workflow()
    steps = workflow["jobs"]["verify"]["steps"]
    step = next(s for s in steps if s.get("name") == "Post diff as PR comment")
    run = step["run"]
    assert "gh api --method PATCH" in run
    assert '-F "body=@' in run
    assert "--edit-last" not in run
    assert "2>/dev/null" not in run


def test_workflow_has_issues_write_permission():
    workflow = _load_workflow()
    assert workflow["permissions"]["issues"] == "write"
