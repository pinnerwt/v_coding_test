import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
TASK2 = REPO_ROOT / "task2"
PLAN_MD = TASK2 / "plan.md"
MIGRATE_SCRIPT = TASK2 / "scripts" / "migrate_plan_to_tickets.py"
ARCHIVE_DIR = REPO_ROOT / "openspec" / "changes" / "archive"
TICKETS_ARCHIVE_DIR = TASK2 / "tickets" / "archive"


def _count_tickets_in_plan(plan_path: Path) -> int:
    in_ticket_section = False
    count = 0
    for line in plan_path.read_text().splitlines():
        if line.startswith("## TDD tickets") or line.startswith("## Benchmark improvements"):
            in_ticket_section = True
        elif line.startswith("## ") and in_ticket_section:
            in_ticket_section = False
        if in_ticket_section and re.match(r"^[0-9]+\. \*\*", line):
            count += 1
    return count


def test_migration_count_matches_plan_md(tmp_path):
    plan_copy = tmp_path / "plan.md"
    shutil.copy(PLAN_MD, plan_copy)
    active_dir = tmp_path / "tickets" / "active"
    archive_dir = tmp_path / "tickets" / "archive"
    active_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)
    result = subprocess.run(
        [
            sys.executable,
            str(MIGRATE_SCRIPT),
            "--plan",
            str(plan_copy),
            "--out",
            str(tmp_path / "tickets"),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Migration failed:\n{result.stderr}"
    emitted = list(active_dir.glob("*.md")) + list(archive_dir.glob("*.md"))
    expected = _count_tickets_in_plan(PLAN_MD)
    assert len(emitted) == expected, (
        f"emitted {len(emitted)} files but expected {expected} (from plan.md ticket sections)"
    )


def _git_has_pr_for_ticket(ticket_id: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["git", "log", "--oneline", "--all"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        ticket_pat = re.compile(rf"\(#{ticket_id}\)")
        for line in out.splitlines():
            if ticket_pat.search(line):
                all_prs = re.findall(r"\(#(\d+)\)", line)
                non_ticket = [int(p) for p in all_prs if int(p) != ticket_id]
                if non_ticket:
                    return non_ticket[-1]
    except subprocess.CalledProcessError:
        pass
    return None


def test_archived_changes_produce_archive_ticket_with_merged_pr(tmp_path):
    plan_copy = tmp_path / "plan.md"
    shutil.copy(PLAN_MD, plan_copy)
    tickets_dir = tmp_path / "tickets"
    active_dir = tickets_dir / "active"
    archive_dir = tickets_dir / "archive"
    active_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT), "--plan", str(plan_copy), "--out", str(tickets_dir)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Migration failed:\n{result.stderr}"
    cited_ticket_ids: set[int] = set()
    for proposal in ARCHIVE_DIR.glob("*/proposal.md"):
        for m in re.finditer(r"ticket #(\d+)", proposal.read_text()):
            cited_ticket_ids.add(int(m.group(1)))
    assert cited_ticket_ids, "No ticket citations found in archived proposals — check archive dir"
    verifiable_ids = {tid for tid in cited_ticket_ids if _git_has_pr_for_ticket(tid) is not None}
    assert verifiable_ids, "No verifiable ticket citations found — git log has no PR refs for any"
    archive_files = list(archive_dir.glob("*.md"))
    if not archive_files:
        archive_files = list(TICKETS_ARCHIVE_DIR.glob("*.md"))
    archive_ids_with_merged_pr: set[int] = set()
    for f in archive_files:
        text = f.read_text()
        if text.startswith("---"):
            end = text.index("---", 3)
            fm = yaml.safe_load(text[3:end])
            if fm.get("merged_pr") is not None:
                archive_ids_with_merged_pr.add(fm["id"])
    for tid in verifiable_ids:
        assert tid in archive_ids_with_merged_pr, (
            f"Ticket #{tid} cited in archived proposal, git-verifiable PR found, "
            f"but no archive file with merged_pr set"
        )
