import argparse
import subprocess
from pathlib import Path

import yaml


def archive_workflow_only_ticket(
    slug: str,
    ticket_number: int,
    pr_number: int,
    iso_date: str,
    repo_root: Path,
) -> None:
    tickets_dir = repo_root / "task2" / "tickets"
    filename = f"{ticket_number:03d}-{slug}.md"
    active_path = tickets_dir / "active" / filename
    archive_path = tickets_dir / "archive" / filename

    if archive_path.exists():
        text = archive_path.read_text()
        end = text.index("---", 3)
        fm = yaml.safe_load(text[3:end])
        stored_pr = fm.get("merged_pr")
        if stored_pr is not None:
            if stored_pr != pr_number or fm.get("archived_at") != iso_date:
                raise ValueError(
                    f"Ticket already archived with merged_pr={stored_pr}, "
                    f"archived_at={fm.get('archived_at')!r}; refusing to overwrite "
                    f"with pr_number={pr_number}, iso_date={iso_date!r}"
                )
            return

    slug_pattern = f"*-{slug}.md"
    matches = list((tickets_dir / "active").glob(slug_pattern)) + list(
        (tickets_dir / "archive").glob(slug_pattern)
    )
    if not matches:
        raise FileNotFoundError(f"Ticket file not found in active/ or archive/ for slug: {slug}")

    leading_int = int(matches[0].stem.split("-")[0])
    if leading_int != ticket_number:
        raise ValueError(
            f"Filename leading number {leading_int} does not match ticket_number={ticket_number}"
        )

    if not active_path.exists():
        raise FileNotFoundError(f"Ticket file not found in active/: {filename}")

    _, fm_text, body = active_path.read_text().split("---", 2)
    fm = yaml.safe_load(fm_text)
    if body.startswith("\n"):
        body = body[1:]

    fm["status"] = "archived"
    fm["merged_pr"] = pr_number
    fm["archived_at"] = iso_date

    new_text = (
        "---\n"
        + yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
        + "---\n"
        + body
    )

    subprocess.run(
        ["git", "mv", str(active_path), str(archive_path)],
        cwd=str(repo_root),
        check=True,
    )

    archive_path.write_text(new_text)

    subprocess.run(
        ["git", "add", str(archive_path)],
        cwd=str(repo_root),
        check=True,
    )

    subprocess.run(
        ["uv", "run", "python", "scripts/regen_tickets_index.py"],
        cwd=str(repo_root / "task2"),
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive a workflow-only ticket after its PR merges."
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--ticket-number", type=int, required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).parent.parent.parent)
    args = parser.parse_args()
    archive_workflow_only_ticket(
        slug=args.slug,
        ticket_number=args.ticket_number,
        pr_number=args.pr_number,
        iso_date=args.date,
        repo_root=args.repo_root,
    )


if __name__ == "__main__":
    main()
