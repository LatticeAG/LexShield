"""Built-in policy pack discovery and apply (SPEC §9.E packs)."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

PACK_NAMES = ("baseline-deny", "pii-guard", "change-window")


def _find_packs_root() -> Path | None:
    """Locate packs/ with baseline-deny/policy.yaml (repo or cwd)."""
    for start in [Path.cwd(), *Path.cwd().parents]:
        packs = start / "packs"
        if (packs / "baseline-deny" / "policy.yaml").is_file():
            return packs
    workspace = Path("/workspace/packs")
    if (workspace / "baseline-deny" / "policy.yaml").is_file():
        return workspace
    return None


def _pack_dir(name: str) -> Path | None:
    root = _find_packs_root()
    if root is None:
        return None
    directory = root / name
    if (directory / "policy.yaml").is_file():
        return directory
    return None


def list_packs() -> None:
    """List available policy packs."""
    root = _find_packs_root()
    table = Table(title="Policy packs")
    table.add_column("Name")
    table.add_column("Policy")
    table.add_column("Rules")
    table.add_column("Status")

    for name in PACK_NAMES:
        pack_dir = _pack_dir(name) if root else None
        if pack_dir is not None:
            policy = pack_dir / "policy.yaml"
            rules = pack_dir / "rules.yaml"
            rules_status = "[green]yes[/green]" if rules.exists() else "[yellow]missing[/yellow]"
            table.add_row(name, str(policy), rules_status, "[green]available[/green]")
        elif root is not None:
            table.add_row(
                name,
                str(root / name / "policy.yaml"),
                "—",
                "[yellow]missing[/yellow]",
            )
        else:
            table.add_row(name, f"packs/{name}/policy.yaml", "—", "[dim]packs/ not found[/dim]")

    console.print(table)


def apply_pack(
    name: str = typer.Argument(help="Pack name (baseline-deny, pii-guard, change-window)."),
    output: Path = typer.Option(
        Path("policy.yaml"),
        "--output",
        "-o",
        help="Destination policy file.",
        resolve_path=True,
    ),
    rules_output: Path | None = typer.Option(
        None,
        "--rules-output",
        help="Also copy rules.yaml to this path (default: ./rules.yaml when pack has rules).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing output files."),
) -> None:
    """Copy a pack policy (and optional rules) into the current directory."""
    if name not in PACK_NAMES:
        console.print(f"[red]Unknown pack:[/red] {name}")
        raise typer.Exit(code=1)

    pack_dir = _pack_dir(name)
    if pack_dir is None:
        root = _find_packs_root()
        if root is None:
            console.print("[yellow]packs/ not found[/yellow]; run from repo root or set up packs/")
        else:
            console.print(f"[red]Pack missing:[/red] {root / name / 'policy.yaml'}")
        raise typer.Exit(code=1)

    policy_src = pack_dir / "policy.yaml"
    if output.exists() and not force:
        console.print(f"[red]Refusing to overwrite[/red] {output} (use --force)")
        raise typer.Exit(code=1)

    shutil.copy2(policy_src, output)
    console.print(f"[green]applied[/green] {name} policy → {output}")

    rules_src = pack_dir / "rules.yaml"
    if rules_src.is_file():
        dest_rules = rules_output or Path("rules.yaml")
        if dest_rules.exists() and not force:
            console.print(f"[yellow]skip[/yellow] rules (exists: {dest_rules})")
        else:
            shutil.copy2(rules_src, dest_rules, follow_symlinks=True)
            console.print(f"[green]applied[/green] {name} rules → {dest_rules}")
