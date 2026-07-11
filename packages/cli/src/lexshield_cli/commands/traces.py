"""Local NDJSON trace queries (SPEC §9.E traces)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from lexshield_cli.config import resolve_config_path, resolve_trace_path

console = Console()


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


def _request_id(event: dict) -> str:
    return event.get("id") or event.get("request", {}).get("id", "?")


def _verdict_decision(event: dict) -> str:
    return event.get("verdict", {}).get("decision", "?")


def _verdict_reason(event: dict) -> str:
    return event.get("verdict", {}).get("reason", "")


def _tool_name(event: dict) -> str:
    request = event.get("request", {})
    tool = request.get("tool", {})
    return tool.get("name", "?")


def list_traces(
    decision: str | None = typer.Option(None, "--decision", help="Filter by verdict decision."),
    limit: int = typer.Option(50, "--limit", help="Maximum traces to show."),
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
    trace_file: Path | None = typer.Option(
        None,
        "--trace-file",
        help="NDJSON trace file path (overrides config sink).",
        resolve_path=True,
    ),
) -> None:
    """List traces from local NDJSON sink."""
    config_path = resolve_config_path(config) if config.exists() else config
    path = resolve_trace_path(config_path, trace_file=trace_file)

    if not path.exists():
        console.print(f"[yellow]No traces at[/yellow] {path}")
        raise typer.Exit(code=0)

    table = Table(title=f"Traces ({path})", show_header=True, header_style="bold")
    table.add_column("Request ID")
    table.add_column("Decision")
    table.add_column("Tool")
    table.add_column("Reason")

    shown = 0
    for event in _iter_traces(path):
        verdict = event.get("verdict", {})
        if decision and verdict.get("decision") != decision:
            continue
        table.add_row(
            _request_id(event),
            _verdict_decision(event),
            _tool_name(event),
            _verdict_reason(event),
        )
        shown += 1
        if shown >= limit:
            break

    if shown == 0:
        console.print("[dim]No matching traces[/dim]")
    else:
        console.print(table)


def show_trace(
    request_id: str = typer.Argument(help="Trace / request id to display."),
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
    trace_file: Path | None = typer.Option(
        None,
        "--trace-file",
        help="NDJSON trace file path (overrides config sink).",
        resolve_path=True,
    ),
) -> None:
    """Show a single trace event."""
    config_path = resolve_config_path(config) if config.exists() else config
    path = resolve_trace_path(config_path, trace_file=trace_file)

    if not path.exists():
        console.print(f"[red]Trace file not found:[/red] {path}")
        raise typer.Exit(code=1)

    for event in _iter_traces(path):
        if _request_id(event) == request_id:
            _print_trace(event)
            raise typer.Exit(code=0)

    console.print(f"[red]Trace not found:[/red] {request_id}")
    raise typer.Exit(code=1)


def _print_trace(event: dict) -> None:
    verdict = event.get("verdict", {})
    request = event.get("request", {})
    tool = request.get("tool", {})
    context = request.get("context", {})
    classifications = verdict.get("classifications", [])

    table = Table(title="Trace", show_header=True, header_style="bold")
    table.add_column("Field", style="dim")
    table.add_column("Value")

    table.add_row("id", _request_id(event))
    table.add_row("decision", _verdict_decision(event))
    table.add_row("reason", _verdict_reason(event))
    table.add_row("tool", tool.get("name", "?"))
    table.add_row("environment", context.get("environment", "—"))
    table.add_row("matchedRuleId", verdict.get("matchedRuleId") or "—")
    if classifications:
        table.add_row("intent", classifications[0].get("intent", "—"))
        table.add_row("confidence", str(classifications[0].get("confidence", "—")))
    if event.get("ts"):
        table.add_row("ts", event["ts"])

    console.print(table)
