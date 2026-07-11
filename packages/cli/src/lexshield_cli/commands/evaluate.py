"""Offline tool-call evaluation (SPEC §9.E evaluate)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()


def evaluate(
    tool: str | None = typer.Option(None, "--tool", help="Tool name to evaluate."),
    args: str = typer.Option("{}", "--args", help="Tool arguments as JSON."),
    caller: str | None = typer.Option(None, "--caller", help="Caller id."),
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml.",
        exists=False,
        dir_okay=False,
        resolve_path=True,
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable verdict JSON."),
    stdin: bool = typer.Option(False, "--stdin", help="Read ToolCallRequest JSON from stdin."),
) -> None:
    """Evaluate a tool call against loaded policy (offline)."""
    if stdin:
        payload: dict[str, Any] = json.load(sys.stdin)
        console.print("[dim]evaluate --stdin[/dim]", payload)
    elif tool is None:
        console.print("[red]Provide --tool or --stdin[/red]")
        raise typer.Exit(code=1)
    else:
        try:
            arguments = json.loads(args)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Invalid --args JSON:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(
            f"[dim]evaluate[/dim] tool={tool} config={config} caller={caller} args={arguments}"
        )

    if json_output:
        stub_verdict = {
            "decision": "BLOCK",
            "reason": "stub: engine evaluate not yet implemented",
            "matchedRuleId": None,
            "requestId": "stub",
        }
        console.print_json(data=stub_verdict)
    else:
        console.print("[yellow]stub[/yellow]: engine evaluate not yet implemented")

    raise typer.Exit(code=0)
