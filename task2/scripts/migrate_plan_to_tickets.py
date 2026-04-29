import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent

_TICKET_SECTION_HEADERS = frozenset(
    ["## TDD tickets (each is red → green → refactor)", "## Benchmark improvements (candidates)"]
)
_STOP_HEADER = "## Undone"

_KNOWN_GATE_VOCAB: frozenset[str] = frozenset(
    ["no-other-task2-prs-open", "qwen-reachable", "no-benchmark-in-flight"]
)

_DEPENDENCY_RE = re.compile(
    r"after #(\d+) lands|blocked on #(\d+)|requires #(\d+)|depends on #(\d+)"
)
_GATE_RE = re.compile(r"must run with no other task2 PRs open", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"task2/benchmark/[^\s\"']+\.json")
_RELATED_RE = re.compile(r"#(\d+)")
_TRIGGER_RE = re.compile(r"\*Trigger:\*\s*(.+)")


def _slug(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[`'\"\.\(\)\[\]\{\}:/\\]", " ", title)
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    words = [
        w
        for w in title.split()
        if w
        not in {
            "the",
            "a",
            "an",
            "and",
            "or",
            "of",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "by",
            "from",
            "up",
            "out",
            "is",
            "are",
            "be",
            "as",
            "that",
        }
    ]
    return "-".join(words[:6])


def _extract_tickets(plan_text: str) -> list[dict]:
    lines = plan_text.splitlines()
    in_section = False
    tickets: list[dict] = []
    current: dict | None = None
    body_lines: list[str] = []
    ticket_re = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*")

    def _flush() -> None:
        if current is not None:
            current["body"] = "\n".join(body_lines).strip()
            tickets.append(current)

    for line in lines:
        stripped = line.rstrip()
        for header in _TICKET_SECTION_HEADERS:
            if stripped.startswith(header):
                in_section = True
                break
        if stripped.startswith(_STOP_HEADER) and in_section:
            _flush()
            break
        if stripped.startswith("## ") and in_section:
            continue
        if not in_section:
            continue
        m = ticket_re.match(stripped)
        if m:
            _flush()
            ticket_id = int(m.group(1))
            title = m.group(2)
            current = {"id": ticket_id, "title": title}
            body_lines = [stripped]
        elif current is not None:
            body_lines.append(stripped)

    _flush()
    return tickets


def _extract_urgency_map(plan_text: str) -> dict[int, str]:
    lines = plan_text.splitlines()
    in_undone = False
    current_urgency = "P3"
    result: dict[int, str] = {}
    for line in lines:
        s = line.rstrip()
        if s == "## Undone":
            in_undone = True
            continue
        if in_undone:
            if s.startswith("## "):
                break
            m = re.match(r"### (P[0-3])", s)
            if m:
                current_urgency = m.group(1)
                continue
            m2 = re.match(r"- \*\*#(\d+)\*\*", s)
            if m2:
                result[int(m2.group(1))] = current_urgency
    return result


def _get_pr_for_archive_dir(change_name: str, repo_root: Path) -> int | None:
    pr_m = re.search(r"#(\d+)", change_name)
    if pr_m:
        return int(pr_m.group(1))
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", change_name)
    try:
        out = subprocess.check_output(
            ["git", "log", "--oneline", "--all"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            if "Merge pull request" in line and slug in line:
                m = re.search(r"#(\d+)", line)
                if m:
                    return int(m.group(1))
    except subprocess.CalledProcessError:
        pass
    return None


_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def _extract_merged_ticket_map(
    repo_root: Path, fallback_date: str
) -> tuple[dict[int, int | None], dict[int, str]]:
    merged: dict[int, int | None] = {}
    archived_at: dict[int, str] = {}
    for proposal in (repo_root / "openspec" / "changes" / "archive").glob("*/proposal.md"):
        text = proposal.read_text()
        ticket_ids = [int(m) for m in re.findall(r"ticket #(\d+)", text)]
        change_name = proposal.parent.name
        archive_pr = _get_pr_for_archive_dir(change_name, repo_root)
        date_m = _DATE_PREFIX_RE.match(change_name)
        date_iso = date_m.group(1) if date_m else fallback_date
        for tid in ticket_ids:
            pr_num = archive_pr or _git_filed_pr(tid, repo_root)
            if tid not in merged or (merged[tid] is None and pr_num is not None):
                merged[tid] = pr_num
                archived_at[tid] = date_iso
    return merged, archived_at


def _git_filed_pr(ticket_id: int, repo_root: Path) -> int | None:
    try:
        out = subprocess.check_output(
            ["git", "log", "--oneline", "--all"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        ticket_then_pr_pat = re.compile(rf"\(#{ticket_id}\)\s+\(#(\d+)\)")
        for line in out.splitlines():
            m = ticket_then_pr_pat.search(line)
            if m:
                return int(m.group(1))
    except subprocess.CalledProcessError:
        pass
    return None


def _assign_tier(title: str, body: str) -> int:
    combined = (title + " " + body).lower()
    if any(
        k in combined for k in [".claude/", "skill files", "new_task2", "done_pr", "review_task2"]
    ):
        return 1
    if any(
        k in combined for k in ["bench.py", "trends.py", "scoreboard", "validators", "score.py"]
    ):
        return 2
    if "wrong" in combined and "every run" in combined:
        return 3
    if any(k in combined for k in ["produces an artifact", "blocks ticket #", "diagnostic"]):
        return 4
    if any(k in combined for k in ["refactor", "doc-only", "hygiene", "dead-code", "doc only"]):
        return 6
    return 5


def _extract_dependencies(body: str) -> list[int]:
    deps: list[int] = []
    for m in _DEPENDENCY_RE.finditer(body):
        val = next(g for g in m.groups() if g is not None)
        deps.append(int(val))
    return list(dict.fromkeys(deps))


def _extract_pre_flight_gates(body: str) -> list[str]:
    gates: list[str] = []
    if _GATE_RE.search(body):
        gates.append("no-other-task2-prs-open")
    return gates


def _extract_evidence(body: str) -> list[str]:
    return list(dict.fromkeys(_EVIDENCE_RE.findall(body)))


def _extract_related(body: str, ticket_id: int, deps: list[int], known_ids: set[int]) -> list[int]:
    all_refs = [int(m) for m in _RELATED_RE.findall(body) if int(m) != ticket_id]
    return list(dict.fromkeys(r for r in all_refs if r not in deps and r in known_ids))


def _extract_trigger(body: str, title: str) -> str:
    m = _TRIGGER_RE.search(body)
    if m:
        return m.group(1).strip()
    return title.strip()


def _build_frontmatter(
    ticket: dict,
    urgency: str,
    merged_pr: int | None,
    filed_pr: int | None,
    status: str,
    archived_at: str | None,
    known_ids: set[int],
) -> str:
    body = ticket.get("body", "")
    deps = _extract_dependencies(body)
    gates = _extract_pre_flight_gates(body)
    evidence = _extract_evidence(body)
    related = _extract_related(body, ticket["id"], deps, known_ids)
    trigger = _extract_trigger(body, ticket["title"])
    tier = _assign_tier(ticket["title"], body)
    slug = _slug(ticket["title"])

    fm: dict = {
        "id": ticket["id"],
        "slug": slug,
        "status": status,
        "tier": tier,
        "urgency": urgency,
        "axes": {"pass_rate": 0, "tokens_pct": 0, "latency_pct": 0},
        "dependencies": deps,
        "pre_flight_gates": gates,
        "evidence": evidence,
        "related": related,
        "filed_pr": filed_pr,
        "merged_pr": merged_pr,
        "archived_at": archived_at,
        "trigger": trigger,
    }
    return yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)


def migrate(plan_path: Path, out_dir: Path, repo_root: Path) -> None:
    plan_text = plan_path.read_text()
    tickets = _extract_tickets(plan_text)
    pre_count = len(tickets)

    today_iso = date.today().isoformat()
    urgency_map = _extract_urgency_map(plan_text)
    merged_map, merged_archived_at = _extract_merged_ticket_map(repo_root, today_iso)
    known_ids = {t["id"] for t in tickets}

    active_dir = out_dir / "active"
    archive_dir = out_dir / "archive"
    active_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    emitted = 0
    for ticket in tickets:
        tid = ticket["id"]
        merged_pr = merged_map.get(tid)
        filed_pr = _git_filed_pr(tid, repo_root)
        is_undone = tid in urgency_map
        status = "active" if is_undone else "archived"
        archived_at = None if is_undone else merged_archived_at.get(tid, today_iso)
        urgency = urgency_map.get(tid, "P3")

        fm_text = _build_frontmatter(
            ticket, urgency, merged_pr, filed_pr, status, archived_at, known_ids
        )
        slug = _slug(ticket["title"])
        filename = f"{tid:03d}-{slug}.md"
        dest_dir = archive_dir if status == "archived" else active_dir
        dest = dest_dir / filename
        content = f"---\n{fm_text}---\n\n{ticket.get('body', '')}\n"
        try:
            dest.write_text(content)
            emitted += 1
        except OSError as exc:
            print(f"WARNING: could not write {dest}: {exc}", file=sys.stderr)

    if emitted != pre_count:
        print(
            f"ERROR: pre_count={pre_count} but emitted={emitted}; aborting",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Migrated {emitted} tickets ({active_dir.name}: active, {archive_dir.name}: archive)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=REPO_ROOT / "task2" / "plan.md")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "task2" / "tickets")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    migrate(args.plan, args.out, args.repo_root)


if __name__ == "__main__":
    main()
