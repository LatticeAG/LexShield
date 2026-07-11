"""Export LexShield OpenAPI schema."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from lexshield.server.app import create_app

console = Console()


def export_openapi(
    output: Path = typer.Option(
        Path("openapi.json"),
        "--output",
        "-o",
        help="Destination file for the OpenAPI schema.",
        resolve_path=True,
    ),
) -> None:
    """Write the LexShield API OpenAPI schema to a JSON file."""
    app = create_app(None)
    schema = app.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    console.print(f"[green]Wrote OpenAPI schema[/green] to {output}")
