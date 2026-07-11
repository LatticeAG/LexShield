"""Contrib sketch — OpenAI Agents SDK tool interception with LexShield.

Dev deps: openai-agents (see README.md)
LexShield: lexshield (monorepo: uv sync)

Recommended pattern: wrap handlers with shield.guard before function_tool.
Lifecycle hooks are useful for audit; use guard for enforceable policy.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, TypeVar

from lexshield import Shield
from lexshield.errors import LexShieldBlockedError

try:
    from agents import RunHooksBase, function_tool
except ImportError:  # pragma: no cover - optional dev dep
    RunHooksBase = object  # type: ignore[misc, assignment]
    function_tool = None  # type: ignore[assignment]

F = TypeVar("F", bound=Callable[..., Any])

EXAMPLE_POLICY_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "python-block-exfil"


def lexshield_function_tool(
    shield: Shield,
    *,
    name: str | None = None,
    **function_tool_kwargs: Any,
) -> Callable[[F], Any]:
    """Decorator: shield.guard → agents.function_tool."""

    def decorator(fn: F) -> Any:
        if function_tool is None:
            raise RuntimeError("openai-agents is required: uv pip install openai-agents")

        tool_name = name or fn.__name__
        guarded = shield.guard(tool=tool_name)(fn)
        return function_tool(name=tool_name, **function_tool_kwargs)(guarded)

    return decorator


class LexShieldAuditHooks(RunHooksBase):
    """Observe tool calls; evaluate for traces (blocking still happens in guarded tools)."""

    def __init__(self, shield: Shield) -> None:
        self.shield = shield

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        tool_name = getattr(context, "tool_name", getattr(tool, "name", "unknown"))
        raw_args = getattr(context, "tool_arguments", "{}")
        try:
            import json

            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, TypeError):
            arguments = {"raw": raw_args}

        verdict = await self.shield.evaluate(tool=tool_name, arguments=arguments)
        # In production: emit to your trace sink / SIEM. Do not rely on this hook alone to block.
        print(f"[lexshield-audit] {tool_name} → {verdict.decision} ({verdict.matched_rule_id})")


async def _policy_demo() -> None:
    """Offline demo — no OpenAI API key required."""
    shield = Shield.from_config(EXAMPLE_POLICY_DIR / "lexshield.yaml")

    @shield.guard(tool="send_email")
    async def send_email(to: str, subject: str, body: str) -> dict[str, str]:
        return {"status": "sent", "to": to}

    try:
        await send_email(
            to="recipient@example.com",
            subject="keys",
            body="AKIAIOSFODNN7EXAMPLE",
        )
        print("Unexpected: tool call was allowed")
    except LexShieldBlockedError as exc:
        rule_id = exc.verdict.matched_rule_id if exc.verdict else "unknown"
        print(f"BLOCKED (expected): {exc.message} (rule={rule_id})")

    print("\nTo wire into Agents SDK:")
    print("  @lexshield_function_tool(shield, name='send_email')")
    print("  async def send_email(...): ...")
    print("  agent = Agent(..., tools=[send_email])")


if __name__ == "__main__":
    asyncio.run(_policy_demo())
