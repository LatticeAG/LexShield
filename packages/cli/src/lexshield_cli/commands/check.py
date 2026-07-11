"""Validate config and policy (SPEC §9.E check)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console

from lexshield.errors import LexShieldConfigError
from lexshield.models import VerdictType
from lexshield.policy.loader import load_policy

console = Console()


def _resolve_config_path(config: Path) -> Path:
    """Accept a lexshield.yaml path or directory containing it."""
    if config.is_dir():
        candidate = config / "lexshield.yaml"
        if candidate.is_file():
            return candidate
        raise LexShieldConfigError(f"No lexshield.yaml found in directory: {config}")
    return config


def _resolve_paths_from_config(config: Path) -> tuple[Path, Path | None]:
    """Return policy and optional rules paths relative to config directory."""
    with config.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict) or "shield" not in raw:
        raise LexShieldConfigError("Config must contain a 'shield' section")

    shield_cfg = raw["shield"]
    if not isinstance(shield_cfg, dict):
        raise LexShieldConfigError("'shield' section must be a mapping")

    base_dir = config.parent
    policy_path = base_dir / shield_cfg.get("policy", "./policy.yaml")
    rules_path: Path | None = None
    for classifier in shield_cfg.get("classifiers", []):
        if isinstance(classifier, dict) and classifier.get("type") == "deterministic":
            rules_path = base_dir / classifier.get("path", "./rules.yaml")
            break

    return policy_path, rules_path


def _validate_rules_file(path: Path) -> list[str]:
    """Validate rules.yaml exists and has a usable structure."""
    errors: list[str] = []
    if not path.exists():
        errors.append(f"Rules file not found: {path}")
        return errors

    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if raw is None:
        errors.append(f"Rules file is empty: {path}")
        return errors

    if not isinstance(raw, dict):
        errors.append(f"Rules root must be a mapping: {path}")
        return errors

    tool_map = raw.get("tool_map")
    patterns = raw.get("patterns")
    if tool_map is not None and not isinstance(tool_map, dict):
        errors.append(f"Rules 'tool_map' must be a mapping: {path}")
    if patterns is not None and not isinstance(patterns, list):
        errors.append(f"Rules 'patterns' must be a list: {path}")

    return errors


def _collect_intent_refs(policy_data: dict[str, Any]) -> set[str]:
    intents: set[str] = set()
    for rule in policy_data.get("rules", []):
        if not isinstance(rule, dict):
            continue
        match = rule.get("match", {})
        if isinstance(match, dict):
            for intent in match.get("intents", []) or []:
                intents.add(str(intent))
    return intents


def check(
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
    strict: bool = typer.Option(False, "--strict", help="Reject unknown fields and warnings."),
) -> None:
    """Validate config + policy + taxonomy; exit non-zero on errors."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        config_path = _resolve_config_path(config) if config.exists() else config

        if policy is not None:
            policy_path = policy
            rules_path = rules
        elif config_path.exists():
            policy_path, rules_path = _resolve_paths_from_config(config_path)
            if rules is not None:
                rules_path = rules
        else:
            console.print(
                "[red]error[/red]: provide --policy or an existing --config lexshield.yaml"
            )
            raise typer.Exit(code=1)

        loaded = load_policy(policy_path, strict=strict)
        rule_count = len(loaded.policy.rules)

        if rules_path is None:
            warnings.append("No deterministic classifier rules path in config")
        else:
            errors.extend(_validate_rules_file(rules_path))

        if loaded.policy.default_verdict == VerdictType.ALLOW:
            warnings.append(
                "defaultVerdict is ALLOW; default deny (BLOCK) is recommended for production"
            )

        with policy_path.open(encoding="utf-8") as handle:
            policy_raw = yaml.safe_load(handle)
        intent_refs = _collect_intent_refs(policy_raw if isinstance(policy_raw, dict) else {})

        console.print(f"[green]OK[/green] policy={policy_path}")
        console.print(f"  rules: {rule_count} policy rule(s)")
        if rules_path is not None and rules_path.exists():
            console.print(f"  rules.yaml: {rules_path}")
        if intent_refs:
            console.print(f"  intent refs: {', '.join(sorted(intent_refs))}")

        for warning in warnings:
            console.print(f"[yellow]warning[/yellow]: {warning}")

        if errors:
            for error in errors:
                console.print(f"[red]error[/red]: {error}")
            raise typer.Exit(code=1)

        if strict and warnings:
            raise typer.Exit(code=1)

    except LexShieldConfigError as exc:
        console.print(f"[red]error[/red]: {exc}")
        raise typer.Exit(code=1) from exc
