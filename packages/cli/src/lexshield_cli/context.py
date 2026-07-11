"""Shared Typer callback state for global CLI options."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer


@dataclass
class CliState:
    """Global options propagated to subcommands via Typer context."""

    config: Path = field(default_factory=lambda: Path("lexshield.yaml"))


def get_config(ctx: typer.Context) -> Path:
    """Return the resolved global --config path from callback context."""
    state = ctx.ensure_object(CliState)
    return state.config


def config_option() -> typer.Option:
    """Reusable per-command --config override (inherits global default)."""
    return typer.Option(
        None,
        "--config",
        "-c",
        help="Path to lexshield.yaml or config directory (overrides global -c).",
        exists=False,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    )


def resolve_command_config(ctx: typer.Context, config: Path | None) -> Path:
    """Prefer explicit per-command -c, else global callback value."""
    if config is not None:
        return config
    return get_config(ctx)
