import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
TASK2 = REPO_ROOT / "task2"
TICKETS_DIR = TASK2 / "tickets"
ACTIVE_DIR = TICKETS_DIR / "active"
ARCHIVE_DIR = TICKETS_DIR / "archive"
INDEX_MD = TICKETS_DIR / "INDEX.md"
REGEN_SCRIPT = TASK2 / "scripts" / "regen_tickets_index.py"

_REQUIRED_FIELDS = frozenset(
    [
        "id",
        "slug",
        "status",
        "tier",
        "urgency",
        "axes",
        "dependencies",
        "pre_flight_gates",
        "evidence",
        "related",
        "filed_pr",
        "merged_pr",
        "archived_at",
        "trigger",
    ]
)
_VALID_STATUSES_ACTIVE = frozenset(["active", "in-flight"])
_VALID_STATUSES_ARCHIVE = frozenset(["merged", "archived", "dropped"])
_VALID_TIERS = frozenset(range(1, 7))
_VALID_GATES = frozenset(["no-other-task2-prs-open", "qwen-reachable", "no-benchmark-in-flight"])
_VALID_URGENCIES = frozenset(["P0", "P1", "P2", "P3"])


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---"), f"{path}: file must start with ---"
    end = text.index("---", 3)
    return yaml.safe_load(text[3:end])


def _all_ticket_files() -> list[tuple[Path, str]]:
    result = []
    for f in sorted(ACTIVE_DIR.glob("*.md")):
        result.append((f, "active"))
    for f in sorted(ARCHIVE_DIR.glob("*.md")):
        result.append((f, "archive"))
    return result


def test_regen_tickets_index_idempotent():
    result1 = subprocess.run(
        [sys.executable, str(REGEN_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result1.returncode == 0, f"First regen failed:\n{result1.stderr}"
    content1 = INDEX_MD.read_text()
    result2 = subprocess.run(
        [sys.executable, str(REGEN_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result2.returncode == 0, f"Second regen failed:\n{result2.stderr}"
    content2 = INDEX_MD.read_text()
    assert content1 == content2, (
        "regen_tickets_index.py is not idempotent: two consecutive runs differ"
    )


def test_schema_all_required_fields():
    for path, _folder in _all_ticket_files():
        fm = _parse_frontmatter(path)
        missing = _REQUIRED_FIELDS - set(fm.keys())
        assert not missing, f"{path.name}: missing fields {missing}"
        axes = fm["axes"]
        assert isinstance(axes, dict), f"{path.name}: axes must be a dict"
        for subfield in ("pass_rate", "tokens_pct", "latency_pct"):
            assert subfield in axes, f"{path.name}: axes.{subfield} missing"
            assert isinstance(axes[subfield], int), f"{path.name}: axes.{subfield} must be int"
        assert fm["tier"] in _VALID_TIERS, f"{path.name}: tier={fm['tier']} not in 1..6"
        assert isinstance(fm["dependencies"], list), f"{path.name}: dependencies must be list"
        for dep in fm["dependencies"]:
            assert isinstance(dep, int), f"{path.name}: dependency {dep!r} must be int"
        assert isinstance(fm["pre_flight_gates"], list), (
            f"{path.name}: pre_flight_gates must be list"
        )
        for gate in fm["pre_flight_gates"]:
            assert gate in _VALID_GATES, f"{path.name}: unknown gate {gate!r}"


def test_directory_status_consistency():
    for path, folder in _all_ticket_files():
        fm = _parse_frontmatter(path)
        status = fm["status"]
        if folder == "active":
            assert status in _VALID_STATUSES_ACTIVE, (
                f"{path.name}: active/ file has status={status!r} (must be active or in-flight)"
            )
        else:
            assert status in _VALID_STATUSES_ARCHIVE, (
                f"{path.name}: archive/ file has status={status!r}"
                " (must be merged/archived/dropped)"
            )


def test_dependency_resolution():
    all_ids: set[int] = set()
    for path, _ in _all_ticket_files():
        fm = _parse_frontmatter(path)
        all_ids.add(fm["id"])
    for path, _ in _all_ticket_files():
        fm = _parse_frontmatter(path)
        for dep_id in fm["dependencies"]:
            assert dep_id in all_ids, (
                f"{path.name}: dependency id={dep_id} not found in any active/archive ticket file"
            )


def _parse_index_rows() -> dict[int, dict]:
    if not INDEX_MD.exists():
        return {}
    rows: dict[int, dict] = {}
    header_seen = False
    for line in INDEX_MD.read_text().splitlines():
        line = line.strip()
        if line.startswith("| id"):
            header_seen = True
            continue
        if header_seen and line.startswith("|---"):
            continue
        if header_seen and line.startswith("|") and not line.startswith("## "):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) < 9:
                continue
            try:
                tid = int(parts[0])
            except ValueError:
                continue
            rows[tid] = {
                "id": tid,
                "urgency": parts[1],
                "tier": int(parts[2]) if parts[2].isdigit() else None,
                "pass_rate": int(parts[3]) if parts[3].lstrip("-").isdigit() else None,
                "tokens_pct": int(parts[4]) if parts[4].lstrip("-").isdigit() else None,
                "latency_pct": int(parts[5]) if parts[5].lstrip("-").isdigit() else None,
                "dependencies": parts[6],
                "pre_flight_gates": parts[7],
                "summary": parts[8],
                "file": parts[9] if len(parts) > 9 else "",
            }
        elif header_seen and line.startswith("## "):
            header_seen = False
            if line.startswith("## "):
                if "Active" in line or "Archive" in line:
                    header_seen = False
    return rows


def test_index_mirrors_frontmatter():
    index_rows = _parse_index_rows()
    assert index_rows, "INDEX.md has no parseable rows — run regen_tickets_index.py first"
    for path, _ in _all_ticket_files():
        fm = _parse_frontmatter(path)
        tid = fm["id"]
        assert tid in index_rows, f"Ticket #{tid} ({path.name}) not found in INDEX.md"
        row = index_rows[tid]
        assert row["urgency"] == fm["urgency"], (
            f"Ticket #{tid}: INDEX urgency={row['urgency']!r} != fm urgency={fm['urgency']!r}"
        )
        assert row["tier"] == fm["tier"], (
            f"Ticket #{tid}: INDEX tier={row['tier']} != fm tier={fm['tier']}"
        )
        assert row["pass_rate"] == fm["axes"]["pass_rate"], (
            f"Ticket #{tid}: INDEX pass_rate={row['pass_rate']}"
            f" != fm pass_rate={fm['axes']['pass_rate']}"
        )
        assert row["tokens_pct"] == fm["axes"]["tokens_pct"], (
            f"Ticket #{tid}: INDEX tokens_pct={row['tokens_pct']} != fm={fm['axes']['tokens_pct']}"
        )
        assert row["latency_pct"] == fm["axes"]["latency_pct"], (
            f"Ticket #{tid}: INDEX latency_pct={row['latency_pct']}"
            f" != fm={fm['axes']['latency_pct']}"
        )


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_archive_tickets_have_non_null_archived_at():
    for path in sorted(ARCHIVE_DIR.glob("*.md")):
        fm = _parse_frontmatter(path)
        merged_pr = fm.get("merged_pr")
        assert merged_pr is None or isinstance(merged_pr, int), (
            f"{path.name}: merged_pr must be null or int, got {merged_pr!r}"
        )
        archived_at = fm.get("archived_at")
        assert archived_at is not None, (
            f"{path.name}: archive ticket must have non-null archived_at"
        )
        assert _ISO_DATE_RE.match(str(archived_at)), (
            f"{path.name}: archived_at={archived_at!r} is not ISO-8601 YYYY-MM-DD"
        )


def test_all_tickets_have_nonempty_trigger():
    for path, _folder in _all_ticket_files():
        fm = _parse_frontmatter(path)
        trigger = fm.get("trigger", "")
        assert trigger and str(trigger).strip(), (
            f"{path.name}: trigger must be a non-empty string, got {trigger!r}"
        )


def test_regen_after_add_reflects_new_entry():
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tickets_copy = tmp / "tickets"
        shutil.copytree(TICKETS_DIR, tickets_copy)
        sentinel = tickets_copy / "active" / "999-test-sentinel.md"
        frontmatter = {
            "id": 999,
            "slug": "test-sentinel",
            "status": "active",
            "tier": 6,
            "urgency": "P3",
            "axes": {"pass_rate": 0, "tokens_pct": 0, "latency_pct": 0},
            "dependencies": [],
            "pre_flight_gates": [],
            "evidence": [],
            "related": [],
            "filed_pr": None,
            "merged_pr": None,
            "archived_at": None,
            "trigger": "test sentinel for regen_after_add scenario",
        }
        sentinel.write_text(
            "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\nsentinel body\n"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(REGEN_SCRIPT),
                "--tickets-dir",
                str(tickets_copy),
                "--repo-root",
                str(tmp),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"regen failed:\n{result.stderr}"
        index_content = (tickets_copy / "INDEX.md").read_text()
        assert "999" in index_content, (
            "INDEX.md does not contain newly added ticket #999 after regen"
        )
