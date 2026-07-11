"""Start local LexShield API server (SPEC §9.E run)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lexshield.errors import LexShieldConfigError
from lexshield.shield import Shield

console = Console()


def _resolve_config_path(config: Path) -> Path:
    """Accept a lexshield.yaml path or directory containing it."""
    if config.is_dir():
        candidate = config / "lexshield.yaml"
        if candidate.is_file():
            return candidate
        raise LexShieldConfigError(f"No lexshield.yaml found in directory: {config}")
    return config


def run(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8787, "--port", help="Bind port."),
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml or config directory.",
    ),
    i_understand_bind_all: bool = typer.Option(
        False,
        "--i-understand-bind-all",
        help="Allow binding to 0.0.0.0 (insecure on shared networks).",
    ),
) -> None:
    """Start the local API via uvicorn."""
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

    config_path = _resolve_config_path(config)
    if not config_path.exists():
        console.print(f"[red]Config not found:[/red] {config_path}")
        raise typer.Exit(code=1)

    shield = Shield.from_config(config_path)
    from lexshield.server.app import create_app

    app = create_app(shield)

    console.print(f"[green]Starting LexShield API[/green] at http://{host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
