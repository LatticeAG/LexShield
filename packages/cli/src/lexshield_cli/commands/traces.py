"""Local NDJSON trace queries (SPEC §9.E traces)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console()

DEFAULT_TRACE_PATH = Path("traces.ndjson")


def _iter_traces(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def list_traces(
    decision: str | None = typer.Option(None, "--decision", help="Filter by verdict decision."),
    limit: int = typer.Option(50, "--limit", help="Maximum traces to show."),
    path: Path = typer.Option(
        DEFAULT_TRACE_PATH,
        "--path",
        help="NDJSON trace file path.",
        resolve_path=True,
    ),
) -> None:
    """List traces from local NDJSON sink."""
    if not path.exists():
        console.print(f"[yellow]No traces at[/yellow] {path}")
        raise typer.Exit(code=0)

    shown = 0
    for event in _iter_traces(path):
        verdict = event.get("verdict", {})
        if decision and verdict.get("decision") != decision:
            continue
        request_id = event.get("id") or event.get("request", {}).get("id", "?")
        console.print(f"{request_id}  {verdict.get('decision', '?')}  {verdict.get('reason', '')}")
        shown += 1
        if shown >= limit:
            break

    if shown == 0:
        console.print("[dim]No matching traces[/dim]")


def show_trace(
    request_id: str = typer.Argument(help="Trace / request id to display."),
    path: Path = typer.Option(
        DEFAULT_TRACE_PATH,
        "--path",
        help="NDJSON trace file path.",
        resolve_path=True,
    ),
) -> None:
    """Show a single trace event."""
    if not path.exists():
        console.print(f"[red]Trace file not found:[/red] {path}")
        raise typer.Exit(code=1)

    for event in _iter_traces(path):
        event_id = event.get("id") or event.get("request", {}).get("id")
        if event_id == request_id:
            console.print_json(data=event)
            raise typer.Exit(code=0)

    console.print(f"[red]Trace not found:[/red] {request_id}")
    raise typer.Exit(code=1)
