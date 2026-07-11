"""YAML policy loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from lexshield.errors import LexShieldConfigError
from lexshield.models import Policy, PolicyRule
from lexshield.policy.expressions import Expression, ExpressionError


@dataclass
class CompiledRule:
    """Policy rule with a pre-compiled match expression."""

    rule: PolicyRule
    expression: Expression | None = None


@dataclass
class CompiledPolicy:
    """Policy with compiled rule expressions."""

    policy: Policy
    rules: list[CompiledRule]

    @classmethod
    def from_policy(cls, policy: Policy) -> CompiledPolicy:
        """Compile expressions for an already-parsed policy."""
        compiled_rules: list[CompiledRule] = []
        for rule in policy.rules:
            expression: Expression | None = None
            if rule.match.expression:
                try:
                    expression = Expression.parse(rule.match.expression)
                except ExpressionError as exc:
                    raise LexShieldConfigError(
                        f"Invalid expression in rule {rule.id!r}: {exc}"
                    ) from exc
            compiled_rules.append(CompiledRule(rule=rule, expression=expression))
        return cls(policy=policy, rules=compiled_rules)


def _normalize_policy_data(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce YAML quirks (numeric version, missing rule names) before validation."""
    normalized = dict(data)
    if "version" in normalized and not isinstance(normalized["version"], str):
        normalized["version"] = str(normalized["version"])

    rules = normalized.get("rules", [])
    if isinstance(rules, list):
        normalized_rules: list[Any] = []
        for rule in rules:
            if isinstance(rule, dict) and "name" not in rule:
                normalized_rules.append({**rule, "name": rule.get("id", "rule")})
            else:
                normalized_rules.append(rule)
        normalized["rules"] = normalized_rules

    return normalized


def _validate_policy_structure(data: dict[str, Any]) -> None:
    """Validate minimal policy structure before Pydantic parse."""
    required = ("version", "id", "name", "defaultVerdict", "rules")
    missing = [field for field in required if field not in data]
    if missing:
        raise LexShieldConfigError(
            f"Policy missing required fields: {', '.join(missing)}"
        )
    if not isinstance(data.get("rules"), list):
        raise LexShieldConfigError("Policy 'rules' must be a list")


def load_policy(path: str | Path, *, strict: bool = False) -> CompiledPolicy:
    """Load, validate, and compile a YAML policy file.

    Args:
        path: Path to policy.yaml.
        strict: When True, reject unknown top-level fields.

    Returns:
        Compiled policy with parsed expressions on rules.
    """
    policy_path = Path(path)
    if not policy_path.exists():
        raise LexShieldConfigError(f"Policy file not found: {policy_path}")

    with policy_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise LexShieldConfigError("Policy root must be a mapping")

    if "version" in raw and not isinstance(raw["version"], str):
        raw = {**raw, "version": str(raw["version"])}

    raw = _normalize_policy_data(raw)

    if strict:
        allowed = {
            "version",
            "id",
            "name",
            "description",
            "defaultVerdict",
            "rules",
            "taxonomyRef",
            "severity_threshold",
        }
        unknown = set(raw.keys()) - allowed
        if unknown:
            raise LexShieldConfigError(
                f"Unknown policy fields in strict mode: {', '.join(sorted(unknown))}"
            )

    _validate_policy_structure(raw)

    try:
        policy = Policy.model_validate(raw)
    except Exception as exc:
        raise LexShieldConfigError(f"Invalid policy: {exc}") from exc

    return CompiledPolicy.from_policy(policy)


def load_policy_data(data: dict[str, Any], *, strict: bool = False) -> CompiledPolicy:
    """Load and validate a policy mapping."""
    normalized = _normalize_policy_data(data)

    if strict:
        allowed = {
            "version",
            "id",
            "name",
            "description",
            "defaultVerdict",
            "rules",
            "taxonomyRef",
            "severity_threshold",
        }
        unknown = set(normalized.keys()) - allowed
        if unknown:
            raise LexShieldConfigError(
                f"Unknown policy fields in strict mode: {', '.join(sorted(unknown))}"
            )

    _validate_policy_structure(normalized)

    try:
        policy = Policy.model_validate(normalized)
    except Exception as exc:
        raise LexShieldConfigError(f"Invalid policy: {exc}") from exc

    return CompiledPolicy.from_policy(policy)
