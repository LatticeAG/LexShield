"""Validate config and policy (SPEC §9.E check)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()


def check(
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    strict: bool = typer.Option(False, "--strict", help="Reject unknown fields and warnings."),
) -> None:
    """Validate config + policy + taxonomy; exit non-zero on errors."""
    console.print(f"[dim]check[/dim] config={config} strict={strict}")
    console.print("[yellow]stub[/yellow]: policy validation not yet implemented")
    raise typer.Exit(code=0)
