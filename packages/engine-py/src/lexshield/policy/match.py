"""Rule matching for policy evaluation."""

from __future__ import annotations

import fnmatch

from lexshield.models import Classification, ToolCallRequest
from lexshield.policy.loader import CompiledRule


def _matching_intents(classifications: list[Classification]) -> set[str]:
    intents: set[str] = set()
    if not classifications:
        return intents
    primary = classifications[0]
    intents.add(primary.intent)
    for alternative in primary.alternatives:
        intents.add(alternative.intent)
    return intents


def _tool_matches(patterns: list[str], tool_name: str) -> bool:
    return any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in patterns)


def _tags_match(
    required: dict[str, list[str]], context_tags: dict[str, str] | None
) -> bool:
    if context_tags is None:
        return False
    for key, allowed_values in required.items():
        actual = context_tags.get(key)
        if actual is None or actual not in allowed_values:
            return False
    return True


def build_expression_bindings(
    request: ToolCallRequest,
    classifications: list[Classification],
) -> dict[str, object]:
    """Build variable bindings for expression evaluation."""
    bindings: dict[str, object] = {
        "tool.name": request.tool.name,
        "tool.namespace": request.tool.namespace or "",
        "caller.id": request.caller.id,
        "caller.type": request.caller.type.value,
        "env": request.context.environment or "",
    }

    if request.caller.roles:
        bindings["caller.roles"] = list(request.caller.roles)

    if classifications:
        primary = classifications[0]
        bindings["intent"] = primary.intent
        bindings["confidence"] = primary.confidence

    for key, value in (request.context.tags or {}).items():
        bindings[f"tags.{key}"] = value

    for key, value in request.arguments.items():
        bindings[f"args.{key}"] = _stringify_arg(value)

    return bindings


def _stringify_arg(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return ""
    return str(value)


def rule_matches(
    compiled_rule: CompiledRule,
    request: ToolCallRequest,
    classifications: list[Classification],
) -> bool:
    """Return True when all present match criteria on the rule are satisfied."""
    rule = compiled_rule.rule
    if not rule.enabled:
        return False

    match = rule.match
    primary = classifications[0] if classifications else None

    if match.tools:
        if not _tool_matches(match.tools, request.tool.name):
            return False

    if match.intents:
        intents = _matching_intents(classifications)
        if not any(intent in intents for intent in match.intents):
            return False

    if match.environments:
        env = request.context.environment
        if env is None or env not in match.environments:
            return False

    if match.callers:
        if request.caller.id not in match.callers:
            return False

    if match.roles:
        caller_roles = request.caller.roles or []
        if not any(role in caller_roles for role in match.roles):
            return False

    if match.tags:
        if not _tags_match(match.tags, request.context.tags):
            return False

    if match.min_confidence is not None:
        if primary is None or primary.confidence < match.min_confidence:
            return False

    if compiled_rule.expression is not None:
        bindings = build_expression_bindings(request, classifications)
        if not compiled_rule.expression.evaluate(bindings):
            return False

    return True


def sort_rules(compiled_rules: list[CompiledRule]) -> list[CompiledRule]:
    """Sort rules by priority descending, then id ascending."""
    enabled = [rule for rule in compiled_rules if rule.rule.enabled]
    return sorted(
        enabled,
        key=lambda item: (-item.rule.priority, item.rule.id),
    )
