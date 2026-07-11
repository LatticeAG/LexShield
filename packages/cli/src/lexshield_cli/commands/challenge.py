"""Local challenge queue management (SPEC §9.E challenge)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from lexshield.challenges.store import ChallengeStore
from lexshield_cli.config import resolve_challenges_path, resolve_config_path

console = Console()


def list_challenges(
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml or config directory.",
        exists=False,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    ),
    directory: Path | None = typer.Option(
        None,
        "--dir",
        help="Local challenge store directory (overrides config).",
        resolve_path=True,
    ),
) -> None:
    """List open challenges from the local store."""
    config_path = resolve_config_path(config) if config.exists() else config
    store_path = resolve_challenges_path(config_path, challenges_dir=directory)
    store = ChallengeStore(store_path)
    challenges = store.list_open()

    if not challenges:
        console.print(f"[dim]No open challenges in[/dim] {store_path}")
        raise typer.Exit(code=0)

    table = Table(title="Open challenges")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Request ID")
    table.add_column("Reason")
    for record in challenges:
        table.add_row(
            record.get("id", "?"),
            record.get("status", "?"),
            record.get("requestId", "—"),
            record.get("reason", ""),
        )
    console.print(table)


def _resolve_challenge(
    challenge_id: str,
    decision: str,
    *,
    config: Path,
    directory: Path | None,
) -> None:
    config_path = resolve_config_path(config) if config.exists() else config
    store_path = resolve_challenges_path(config_path, challenges_dir=directory)
    store = ChallengeStore(store_path)
    record = store.resolve(challenge_id, decision=decision, actor="cli")
    if record is None:
        console.print(f"[red]Challenge not found:[/red] {challenge_id}")
        raise typer.Exit(code=1)

    console.print(
        f"[green]{decision}[/green] challenge {record['id']} "
        f"(status: {record['status']})"
    )


def approve_challenge(
    challenge_id: str = typer.Argument(help="Challenge id to approve."),
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml or config directory.",
        exists=False,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    ),
    directory: Path | None = typer.Option(
        None,
        "--dir",
        help="Local challenge store directory (overrides config).",
        resolve_path=True,
    ),
) -> None:
    """Approve a pending challenge."""
    _resolve_challenge(challenge_id, "approve", config=config, directory=directory)


def deny_challenge(
    challenge_id: str = typer.Argument(help="Challenge id to deny."),
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml or config directory.",
        exists=False,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    ),
    directory: Path | None = typer.Option(
        None,
        "--dir",
        help="Local challenge store directory (overrides config).",
        resolve_path=True,
    ),
) -> None:
    """Deny a pending challenge."""
    _resolve_challenge(challenge_id, "deny", config=config, directory=directory)
