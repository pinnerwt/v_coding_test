import argparse
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
TICKETS_DIR = REPO_ROOT / "task2" / "tickets"


def _parse_ticket(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---"), f"{path}: missing frontmatter"
    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end])
    body = text[end + 3 :].strip()
    summary = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            summary = stripped
            break
    fm["_summary"] = summary
    fm["_path"] = path
    return fm


def _fmt_list(val: list) -> str:
    if not val:
        return ""
    return " ".join(str(v) for v in val)


def _escape_cell(s: str) -> str:
    return s.replace("|", "\\|")


def _render_table(tickets: list[dict], rel_base: Path) -> str:
    header = (
        "| id | urgency | tier | pass_rate | tokens_pct | latency_pct"
        " | dependencies | pre_flight_gates | summary | file |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for fm in tickets:
        axes = fm.get("axes", {})
        rel = fm["_path"].relative_to(rel_base)
        rows.append(
            f"| {fm['id']} | {fm['urgency']} | {fm['tier']}"
            f" | {axes.get('pass_rate', 0)} | {axes.get('tokens_pct', 0)}"
            f" | {axes.get('latency_pct', 0)}"
            f" | {_fmt_list(fm.get('dependencies', []))}"
            f" | {_fmt_list(fm.get('pre_flight_gates', []))}"
            f" | {_escape_cell(fm['_summary'])}"
            f" | {rel} |"
        )
    return header + "\n".join(rows) + "\n"


def regen(tickets_dir: Path, repo_root: Path) -> None:
    active_dir = tickets_dir / "active"
    archive_dir = tickets_dir / "archive"

    active_tickets = [_parse_ticket(p) for p in active_dir.glob("*.md")]
    archive_tickets = [_parse_ticket(p) for p in archive_dir.glob("*.md")]

    active_tickets.sort(key=lambda fm: fm["id"])
    archive_tickets.sort(key=lambda fm: (fm.get("archived_at") or "", fm["id"]))

    lines = ["# Tickets INDEX\n\n"]
    lines.append("## Active\n\n")
    lines.append(_render_table(active_tickets, repo_root))
    lines.append("\n## Archive\n\n")
    lines.append(_render_table(archive_tickets, repo_root))

    content = "".join(lines)
    index_path = tickets_dir / "INDEX.md"
    index_path.write_text(content)
    print(f"Wrote {index_path} ({len(active_tickets)} active, {len(archive_tickets)} archive)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets-dir", type=Path, default=TICKETS_DIR)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    regen(args.tickets_dir, args.repo_root)


if __name__ == "__main__":
    main()
