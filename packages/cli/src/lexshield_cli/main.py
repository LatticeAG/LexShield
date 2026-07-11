"""LexShield CLI entrypoint (SPEC §9 / §16)."""

from __future__ import annotations

from pathlib import Path

import typer

from lexshield_cli.commands import (
    challenge,
    check,
    evaluate,
    export_openapi,
    init,
    packs,
    run,
    traces,
)
from lexshield_cli.completion import SUPPORTED_SHELLS, render_completion_script
from lexshield_cli.context import CliState

app = typer.Typer(
    name="lexshield",
    help="LexShield — open-source policy firewall for agent tool calls.",
    no_args_is_help=True,
)


@app.callback()
def main(
    ctx: typer.Context,
    config: Path = typer.Option(
        Path("lexshield.yaml"),
        "--config",
        "-c",
        help="Path to lexshield.yaml or config directory (default: ./lexshield.yaml).",
        exists=False,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Global options applied before subcommands."""
    ctx.ensure_object(CliState)
    ctx.obj.config = config


app.command()(init.init)
app.command()(check.check)
app.command()(run.run)
app.command()(evaluate.evaluate)
app.command("export-openapi")(export_openapi.export_openapi)

traces_app = typer.Typer(help="Query local NDJSON traces.")
traces_app.command("list")(traces.list_traces)
traces_app.command("show")(traces.show_trace)
app.add_typer(traces_app, name="traces")

challenge_app = typer.Typer(help="Manage local human-in-the-loop challenges.")
challenge_app.command("list")(challenge.list_challenges)
challenge_app.command("approve")(challenge.approve_challenge)
challenge_app.command("deny")(challenge.deny_challenge)
app.add_typer(challenge_app, name="challenge")

packs_app = typer.Typer(help="List and apply built-in policy packs.")
packs_app.command("list")(packs.list_packs)
packs_app.command("apply")(packs.apply_pack)
app.add_typer(packs_app, name="packs")


@app.command()
def completion(
    shell: str = typer.Argument(help="Shell name (bash, zsh, fish)."),
) -> None:
    """Generate shell completion script for lexshield subcommands."""
    import sys

    from rich.console import Console

    console = Console(stderr=True)
    if shell not in SUPPORTED_SHELLS:
        supported = ", ".join(sorted(SUPPORTED_SHELLS))
        console.print(f"[red]Unsupported shell:[/red] {shell} (choose: {supported})")
        raise typer.Exit(code=1)

    try:
        script = render_completion_script(app, shell)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    sys.stdout.write(script)
    if not script.endswith("\n"):
        sys.stdout.write("\n")


@app.command()
def version() -> None:
    """Print CLI semver and git sha when available (SPEC §9.E)."""
    import subprocess

    from rich.console import Console

    from lexshield_cli import __version__

    console = Console()
    sha = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        sha = result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    if sha:
        console.print(f"lexshield {__version__} ({sha})")
    else:
        console.print(f"lexshield {__version__}")


if __name__ == "__main__":
    app()
