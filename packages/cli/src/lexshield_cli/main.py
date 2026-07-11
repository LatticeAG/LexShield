"""LexShield CLI entrypoint (SPEC §9 / §16)."""

from __future__ import annotations

import typer

from lexshield_cli.commands import challenge, check, evaluate, init, packs, run, traces

app = typer.Typer(
    name="lexshield",
    help="LexShield — open-source policy firewall for agent tool calls.",
    no_args_is_help=True,
)

app.command()(init.init)
app.command()(check.check)
app.command()(run.run)
app.command()(evaluate.evaluate)

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
