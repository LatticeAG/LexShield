"""Shell completion script generation for the LexShield CLI."""

from __future__ import annotations

import sys

from click.shell_completion import get_completion_class
from typer.main import get_command

SUPPORTED_SHELLS = frozenset({"bash", "zsh", "fish"})


def render_completion_script(app, shell: str) -> str:
    """Return a shell completion script for the given Typer app."""
    if shell not in SUPPORTED_SHELLS:
        supported = ", ".join(sorted(SUPPORTED_SHELLS))
        raise ValueError(f"Unsupported shell {shell!r}; choose one of: {supported}")

    command = get_command(app)
    env_name = f"_{command.name.replace('-', '_').upper()}_COMPLETE"
    completion_class = get_completion_class(shell)
    source = completion_class(command, {}, command.name, env_name)
    return source.source()
