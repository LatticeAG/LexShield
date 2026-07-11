"""Start local LexShield API server (SPEC §9.E run)."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()


def run(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8787, "--port", help="Bind port."),
    i_understand_bind_all: bool = typer.Option(
        False,
        "--i-understand-bind-all",
        help="Allow binding to 0.0.0.0 (insecure on shared networks).",
    ),
) -> None:
    """Start the local API via uvicorn (lexshield.server.app)."""
    if host == "0.0.0.0" and not i_understand_bind_all:
        console.print(
            "[red]Refusing to bind 0.0.0.0[/red] without --i-understand-bind-all "
            "(SPEC §9.E: localhost by default)."
        )
        raise typer.Exit(code=1)

    try:
        import uvicorn
    except ImportError as exc:
        console.print(f"[red]uvicorn is required:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Starting LexShield API[/green] at http://{host}:{port}")
    uvicorn.run(
        "lexshield.server.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
