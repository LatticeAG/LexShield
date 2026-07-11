"""Local challenge queue management (SPEC §9.E challenge)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

DEFAULT_CHALLENGES_DIR = Path(".lexshield/challenges")


def _list_challenge_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def list_challenges(
    directory: Path = typer.Option(
        DEFAULT_CHALLENGES_DIR,
        "--dir",
        help="Local challenge store directory.",
        resolve_path=True,
    ),
) -> None:
    """List open challenges from the local store."""
    files = _list_challenge_files(directory)
    if not files:
        console.print(f"[dim]No open challenges in[/dim] {directory}")
        raise typer.Exit(code=0)

    table = Table(title="Open challenges")
    table.add_column("ID")
    table.add_column("Tool")
    table.add_column("Reason")
    for file_path in files:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        table.add_row(
            data.get("id", file_path.stem),
            data.get("tool", {}).get("name", "?"),
            data.get("reason", ""),
        )
    console.print(table)


def _resolve_challenge(
    challenge_id: str,
    decision: str,
    *,
    directory: Path,
) -> None:
    target = directory / f"{challenge_id}.json"
    if not target.exists():
        console.print(f"[red]Challenge not found:[/red] {challenge_id}")
        raise typer.Exit(code=1)

    data = json.loads(target.read_text(encoding="utf-8"))
    data["resolution"] = {"decision": decision, "actor": "cli"}
    resolved = directory / f"{challenge_id}.resolved.json"
    resolved.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    target.unlink()
    console.print(f"[green]{decision}[/green] challenge {challenge_id}")


def approve_challenge(
    challenge_id: str = typer.Argument(help="Challenge id to approve."),
    directory: Path = typer.Option(
        DEFAULT_CHALLENGES_DIR,
        "--dir",
        help="Local challenge store directory.",
        resolve_path=True,
    ),
) -> None:
    """Approve a pending challenge."""
    _resolve_challenge(challenge_id, "approve", directory=directory)


def deny_challenge(
    challenge_id: str = typer.Argument(help="Challenge id to deny."),
    directory: Path = typer.Option(
        DEFAULT_CHALLENGES_DIR,
        "--dir",
        help="Local challenge store directory.",
        resolve_path=True,
    ),
) -> None:
    """Deny a pending challenge."""
    _resolve_challenge(challenge_id, "deny", directory=directory)
