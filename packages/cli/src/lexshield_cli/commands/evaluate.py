"""Offline tool-call evaluation (SPEC §9.E evaluate)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from lexshield.errors import LexShieldConfigError
from lexshield.models import ToolCallRequest, Verdict
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


def _resolve_rules_path(config: Path) -> Path | None:
    with config.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        return None

    shield_cfg = raw.get("shield", {})
    if not isinstance(shield_cfg, dict):
        return None

    base_dir = config.parent
    for classifier in shield_cfg.get("classifiers", []):
        if isinstance(classifier, dict) and classifier.get("type") == "deterministic":
            return base_dir / classifier.get("path", "./rules.yaml")
    return None


def _load_shield(
    *,
    config: Path,
    policy: Path | None,
    rules: Path | None,
) -> Shield:
    if policy is not None:
        rules_path = rules
        if rules_path is None and config.exists():
            rules_path = _resolve_rules_path(config)
        return Shield(
            shield_id="cli",
            name="cli-evaluate",
            policy_path=policy,
            rules_path=rules_path,
        )

    if not config.exists():
        raise LexShieldConfigError(
            f"Config file not found: {config} (use --policy or create config with lexshield init)"
        )

    if rules is not None:
        base = Shield.from_config(config)
        return Shield(
            shield_id=base.shield_id,
            name=base.name,
            policy_path=base.policy_path,
            rules_path=rules,
            trace_sink_path=base.trace_sink.path if base.trace_sink else None,
        )

    return Shield.from_config(config)


def _print_verdict_table(verdict: Verdict) -> None:
    table = Table(title="Verdict", show_header=True, header_style="bold")
    table.add_column("Field", style="dim")
    table.add_column("Value")

    table.add_row("decision", verdict.decision.value)
    table.add_row("reason", verdict.reason)
    table.add_row("requestId", verdict.request_id)
    table.add_row(
        "matchedRuleId",
        verdict.matched_rule_id if verdict.matched_rule_id else "—",
    )
    if verdict.policy_version:
        table.add_row("policyVersion", verdict.policy_version)
    table.add_row("durationMs", f"{verdict.duration_ms:.2f}")

    if verdict.classifications:
        primary = verdict.classifications[0]
        table.add_row("intent", primary.intent)
        table.add_row("confidence", f"{primary.confidence:.2f}")
        table.add_row("classifier", primary.classifier)

    console.print(table)


async def _evaluate_request(
    shield: Shield,
    *,
    tool: str,
    arguments: dict[str, Any],
    caller: str | None,
    request_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> Verdict:
    caller_payload: dict[str, Any] = {"id": caller or "anonymous", "type": "agent"}
    return await shield.evaluate(
        tool=tool,
        arguments=arguments,
        caller=caller_payload,
        context=context,
        request_id=request_id,
    )


def evaluate(
    tool: str | None = typer.Option(None, "--tool", help="Tool name to evaluate."),
    args: str = typer.Option("{}", "--args", help="Tool arguments as JSON."),
    caller: str | None = typer.Option(None, "--caller", help="Caller id."),
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
    policy: Path | None = typer.Option(
        None,
        "--policy",
        help="Policy file path (overrides config).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    rules: Path | None = typer.Option(
        None,
        "--rules",
        help="Rules file path (overrides config).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable verdict JSON."),
    stdin: bool = typer.Option(False, "--stdin", help="Read ToolCallRequest JSON from stdin."),
) -> None:
    """Evaluate a tool call against loaded policy (offline)."""
    try:
        config_path = _resolve_config_path(config)
        shield = _load_shield(config=config_path, policy=policy, rules=rules)
    except LexShieldConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if stdin:
        payload: dict[str, Any] = json.load(sys.stdin)
        try:
            request = ToolCallRequest.model_validate(payload)
        except Exception as exc:
            console.print(f"[red]Invalid stdin ToolCallRequest:[/red] {exc}")
            raise typer.Exit(code=1) from exc

        verdict = asyncio.run(
            shield.evaluate(
                tool=request.tool.name,
                arguments=request.arguments,
                caller=request.caller,
                context=request.context,
                request_id=request.id,
            )
        )
    elif tool is None:
        console.print("[red]Provide --tool or --stdin[/red]")
        raise typer.Exit(code=1)
    else:
        try:
            arguments = json.loads(args)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Invalid --args JSON:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        if not isinstance(arguments, dict):
            console.print("[red]--args must be a JSON object[/red]")
            raise typer.Exit(code=1)

        verdict = asyncio.run(
            _evaluate_request(
                shield,
                tool=tool,
                arguments=arguments,
                caller=caller,
            )
        )

    if json_output:
        console.print_json(data=verdict.model_dump(by_alias=True, mode="json"))
    else:
        _print_verdict_table(verdict)

    raise typer.Exit(code=0)
