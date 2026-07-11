"""Offline tool-call evaluation (SPEC §9.E evaluate)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from lexshield.errors import LexShieldConfigError
from lexshield.models import ToolCallRequest, Verdict
from lexshield.shield import Shield
from lexshield.traces.sink import NDJSONTraceSink, StdoutTraceSink
from lexshield_cli.config import resolve_config_path, resolve_policy_and_rules
from lexshield_cli.context import config_option, resolve_command_config

console = Console()


def _resolve_rules_path(config: Path) -> Path | None:
    _, rules_path = resolve_policy_and_rules(config)
    return rules_path


def _without_stdout_sinks(shield: Shield) -> Shield:
    """CLI evaluate prints verdicts to stdout; omit stdout trace summaries."""
    shield.trace_sinks = [
        sink for sink in shield.trace_sinks if not isinstance(sink, StdoutTraceSink)
    ]
    shield.trace_sink = next(
        (sink for sink in shield.trace_sinks if isinstance(sink, NDJSONTraceSink)),
        shield.trace_sinks[0] if shield.trace_sinks else None,
    )
    return shield


def _load_shield(
    *,
    config: Path,
    policy: Path | None,
    rules: Path | None,
) -> Shield:
    if policy is not None:
        rules_path = rules
        if rules_path is None and config.exists():
            try:
                rules_path = _resolve_rules_path(resolve_config_path(config))
            except LexShieldConfigError:
                rules_path = None
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

    config_path = resolve_config_path(config)
    if rules is not None:
        base = Shield.from_config(config_path)
        return Shield(
            shield_id=base.shield_id,
            name=base.name,
            policy_path=base.policy_path,
            rules_path=rules,
            trace_sink_path=base.trace_sink.path if base.trace_sink else None,
            challenge_store_path=base.challenge_store.base_path,
            fail_on_classifier_error=base.fail_on_classifier_error,
            redact_emails=base.redact_emails,
        )

    return _without_stdout_sinks(Shield.from_config(config_path))


def _parse_caller(
    caller: str | None,
    *,
    caller_type: str = "agent",
) -> dict[str, Any]:
    if caller is None:
        return {"id": "anonymous", "type": caller_type}
    caller = caller.strip()
    if caller.startswith("{"):
        parsed = json.loads(caller)
        if not isinstance(parsed, dict):
            raise ValueError("--caller JSON must be an object")
        return parsed
    return {"id": caller, "type": caller_type}


def _build_context(
    *,
    environment: str | None,
    tags_json: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if environment:
        context["environment"] = environment
    try:
        tags = json.loads(tags_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid --tags JSON: {exc}") from exc
    if tags:
        if not isinstance(tags, dict):
            raise ValueError("--tags must be a JSON object")
        context["tags"] = tags
    return context


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
    caller: dict[str, Any],
    request_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> Verdict:
    return await shield.evaluate(
        tool=tool,
        arguments=arguments,
        caller=caller,
        context=context,
        request_id=request_id,
    )


def evaluate(
    ctx: typer.Context,
    tool: str | None = typer.Option(None, "--tool", help="Tool name to evaluate."),
    args: str = typer.Option("{}", "--args", help="Tool arguments as JSON."),
    caller: str | None = typer.Option(
        None,
        "--caller",
        help="Caller id or JSON object (e.g. '{\"id\":\"a1\",\"type\":\"agent\"}').",
    ),
    caller_type: str = typer.Option(
        "agent",
        "--caller-type",
        help="Caller type when --caller is a plain id.",
    ),
    environment: str | None = typer.Option(
        None,
        "--environment",
        "--env",
        help="Sets context.environment.",
    ),
    tags: str = typer.Option("{}", "--tags", help="Context tags as JSON object."),
    config: Path | None = config_option(),
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
    """Evaluate a tool call against loaded policy (offline).

    Examples:

        lexshield evaluate --tool health_check --args '{}'

        lexshield evaluate --tool send_email \\
          --args '{"to":"user@example.com","body":"AKIA0123456789012345"}' \\
          --json

        lexshield -c ./lexshield.yaml evaluate --tool delete_resource \\
          --args '{"resource_id":"db-1"}' --environment production --json

        echo '{"tool":{"name":"health_check"},"arguments":{}}' | lexshield evaluate --stdin --json
    """
    resolved = resolve_command_config(ctx, config)
    try:
        config_path = resolve_config_path(resolved) if resolved.exists() else resolved
        shield = _load_shield(config=config_path, policy=policy, rules=rules)
    except LexShieldConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if stdin:
        payload: dict[str, Any] = json.load(sys.stdin)
        if "shieldId" not in payload and "shield_id" not in payload:
            payload["shieldId"] = shield.shield_id
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

        try:
            caller_payload = _parse_caller(caller, caller_type=caller_type)
            context_payload = _build_context(environment=environment, tags_json=tags)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        verdict = asyncio.run(
            _evaluate_request(
                shield,
                tool=tool,
                arguments=arguments,
                caller=caller_payload,
                context=context_payload or None,
            )
        )

    if json_output:
        console.print_json(data=verdict.model_dump(by_alias=True, mode="json"))
    else:
        _print_verdict_table(verdict)

    raise typer.Exit(code=0)
