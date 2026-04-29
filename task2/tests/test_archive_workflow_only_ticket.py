import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

MINIMAL_FRONTMATTER = {
    "id": 82,
    "slug": "fast-path-ticket-archival-hygiene",
    "status": "active",
    "tier": 1,
    "urgency": "P2",
    "axes": {"pass_rate": 0, "tokens_pct": 0, "latency_pct": 0},
    "dependencies": [],
    "pre_flight_gates": [],
    "evidence": [],
    "related": [],
    "filed_pr": None,
    "merged_pr": None,
    "archived_at": None,
    "trigger": "test fixture trigger for archive helper unit tests",
}


def _write_ticket(directory: Path, ticket_number: int, slug: str, fm: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{ticket_number:03d}-{slug}.md"
    path = directory / filename
    body = f"{ticket_number}. **Stub ticket body for {slug}.**"
    content = "---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + body + "\n"
    path.write_text(content)
    return path


def _setup_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )


def _git_add_and_commit(repo_root: Path, paths: list[Path]) -> None:
    for p in paths:
        subprocess.run(["git", "add", str(p)], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )


def _make_fake_run(regen_calls_collector=None):
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if "regen_tickets_index" in str(args):
            if regen_calls_collector is not None:
                regen_calls_collector.append(kwargs)

            class R:
                returncode = 0

            return R()
        return real_run(args, **kwargs)

    return fake_run


def test_archives_ticket_successfully(tmp_path):
    from scripts.archive_workflow_only_ticket import archive_workflow_only_ticket

    repo_root = tmp_path
    active_dir = repo_root / "task2" / "tickets" / "active"
    archive_dir = repo_root / "task2" / "tickets" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    ticket_path = _write_ticket(
        active_dir, 82, "fast-path-ticket-archival-hygiene", MINIMAL_FRONTMATTER
    )
    _setup_git_repo(repo_root)
    _git_add_and_commit(repo_root, [ticket_path])

    regen_calls: list = []
    with patch(
        "scripts.archive_workflow_only_ticket.subprocess.run",
        side_effect=_make_fake_run(regen_calls),
    ):
        archive_workflow_only_ticket(
            slug="fast-path-ticket-archival-hygiene",
            ticket_number=82,
            pr_number=125,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )

    expected_archive = archive_dir / "082-fast-path-ticket-archival-hygiene.md"
    assert expected_archive.exists()
    assert not (active_dir / "082-fast-path-ticket-archival-hygiene.md").exists()

    text = expected_archive.read_text()
    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end])
    assert fm["merged_pr"] == 125
    assert fm["archived_at"] == "2026-04-29"
    assert fm["status"] == "archived"

    assert len(regen_calls) == 1
    regen_cwd = regen_calls[0].get("cwd")
    assert regen_cwd is not None and "task2" in str(regen_cwd)

    diff_result = subprocess.run(
        ["git", "diff", "--staged", "--stat"],
        cwd=str(repo_root),
        capture_output=True,
        check=True,
        text=True,
    )
    diff_output = diff_result.stdout
    assert "082-fast-path-ticket-archival-hygiene.md" in diff_output
    assert "+++" in diff_output


def test_archives_ticket_stages_content_change(tmp_path):
    from scripts.archive_workflow_only_ticket import archive_workflow_only_ticket

    repo_root = tmp_path
    active_dir = repo_root / "task2" / "tickets" / "active"
    archive_dir = repo_root / "task2" / "tickets" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    ticket_path = _write_ticket(
        active_dir, 82, "fast-path-ticket-archival-hygiene", MINIMAL_FRONTMATTER
    )
    _setup_git_repo(repo_root)
    _git_add_and_commit(repo_root, [ticket_path])

    with patch(
        "scripts.archive_workflow_only_ticket.subprocess.run",
        side_effect=_make_fake_run(),
    ):
        archive_workflow_only_ticket(
            slug="fast-path-ticket-archival-hygiene",
            ticket_number=82,
            pr_number=125,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )

    unstaged = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=str(repo_root),
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    assert unstaged == ""


def test_archives_ticket_idempotently(tmp_path):
    from scripts.archive_workflow_only_ticket import archive_workflow_only_ticket

    repo_root = tmp_path
    active_dir = repo_root / "task2" / "tickets" / "active"
    archive_dir = repo_root / "task2" / "tickets" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    ticket_path = _write_ticket(
        active_dir, 82, "fast-path-ticket-archival-hygiene", MINIMAL_FRONTMATTER
    )

    _setup_git_repo(repo_root)
    _git_add_and_commit(repo_root, [ticket_path])

    regen_target = "scripts.archive_workflow_only_ticket.subprocess.run"

    with patch(regen_target, side_effect=_make_fake_run()) as mock_run:
        archive_workflow_only_ticket(
            slug="fast-path-ticket-archival-hygiene",
            ticket_number=82,
            pr_number=125,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )

        expected_archive = archive_dir / "082-fast-path-ticket-archival-hygiene.md"
        assert expected_archive.exists(), "File was not moved to archive/"
        assert not (active_dir / "082-fast-path-ticket-archival-hygiene.md").exists()

        text = expected_archive.read_text()
        end = text.index("---", 3)
        fm = yaml.safe_load(text[3:end])
        assert fm["merged_pr"] == 125
        assert fm["archived_at"] == "2026-04-29"
        assert fm["status"] == "archived"

        git_mv_calls = [c for c in mock_run.call_args_list if c.args[0][:2] == ["git", "mv"]]
        regen_calls = [c for c in mock_run.call_args_list if "regen_tickets_index" in str(c)]
        assert len(git_mv_calls) == 1
        assert len(regen_calls) == 1

    with patch(regen_target, side_effect=_make_fake_run()) as mock_run2:
        archive_workflow_only_ticket(
            slug="fast-path-ticket-archival-hygiene",
            ticket_number=82,
            pr_number=125,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )
        assert mock_run2.call_count == 0, "Second call should be a no-op (idempotent)"


def test_rejects_missing_ticket_file(tmp_path):
    from scripts.archive_workflow_only_ticket import archive_workflow_only_ticket

    repo_root = tmp_path
    (repo_root / "task2" / "tickets" / "active").mkdir(parents=True, exist_ok=True)
    (repo_root / "task2" / "tickets" / "archive").mkdir(parents=True, exist_ok=True)

    with pytest.raises(FileNotFoundError):
        archive_workflow_only_ticket(
            slug="nonexistent-ticket",
            ticket_number=99,
            pr_number=200,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )


def test_rejects_mismatched_ticket_number(tmp_path):
    from scripts.archive_workflow_only_ticket import archive_workflow_only_ticket

    repo_root = tmp_path
    active_dir = repo_root / "task2" / "tickets" / "active"
    (repo_root / "task2" / "tickets" / "archive").mkdir(parents=True, exist_ok=True)

    _write_ticket(active_dir, 82, "fast-path-ticket-archival-hygiene", MINIMAL_FRONTMATTER)

    with pytest.raises(ValueError):
        archive_workflow_only_ticket(
            slug="fast-path-ticket-archival-hygiene",
            ticket_number=99,
            pr_number=125,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )

    archive_dir = repo_root / "task2" / "tickets" / "archive"
    assert not list(archive_dir.glob("*.md")), "No files should exist in archive/ after ValueError"


def test_rejects_archived_ticket_with_mismatched_metadata(tmp_path):
    from scripts.archive_workflow_only_ticket import archive_workflow_only_ticket

    repo_root = tmp_path
    archive_dir = repo_root / "task2" / "tickets" / "archive"
    (repo_root / "task2" / "tickets" / "active").mkdir(parents=True, exist_ok=True)

    archived_fm = dict(MINIMAL_FRONTMATTER)
    archived_fm["status"] = "archived"
    archived_fm["merged_pr"] = 125
    archived_fm["archived_at"] = "2026-04-29"
    archived_path = _write_ticket(archive_dir, 82, "fast-path-ticket-archival-hygiene", archived_fm)

    _setup_git_repo(repo_root)
    _git_add_and_commit(repo_root, [archived_path])

    with pytest.raises(ValueError):
        archive_workflow_only_ticket(
            slug="fast-path-ticket-archival-hygiene",
            ticket_number=82,
            pr_number=999,
            iso_date="2026-04-29",
            repo_root=repo_root,
        )

    text = archived_path.read_text()
    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end])
    assert fm["merged_pr"] == 125, "Archive file must not be modified after ValueError"
