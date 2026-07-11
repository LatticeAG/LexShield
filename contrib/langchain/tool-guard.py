"""Contrib example — wrap LangChain StructuredTool with LexShield guard.

Dev deps: langchain-core (see README.md)
LexShield: lexshield (monorepo: uv sync)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from lexshield import Shield
from lexshield.errors import LexShieldBlockedError

try:
    from langchain_core.tools import StructuredTool
except ImportError as exc:  # pragma: no cover - optional dev dep
    raise SystemExit(
        "langchain-core is required for this contrib example. "
        "Install with: uv pip install langchain-core"
    ) from exc

EXAMPLE_POLICY_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "python-block-exfil"


def guard_structured_tool(shield: Shield, tool: StructuredTool) -> StructuredTool:
    """Return a copy of `tool` whose handler runs through `shield.guard`."""
    tool_name = tool.name

    if tool.coroutine is not None:
        guarded_coro = shield.guard(tool=tool_name)(tool.coroutine)
        return tool.model_copy(update={"coroutine": guarded_coro})

    if tool.func is not None:
        guarded_func = shield.guard_sync(tool=tool_name)(tool.func)
        return tool.model_copy(update={"func": guarded_func})

    raise ValueError(f"StructuredTool {tool_name!r} has no func or coroutine to guard")


async def _demo() -> None:
    shield = Shield.from_config(EXAMPLE_POLICY_DIR / "lexshield.yaml")

    async def send_email(to: str, subject: str, body: str) -> dict[str, str]:
        return {"status": "sent", "to": to}

    raw_tool = StructuredTool.from_function(
        coroutine=send_email,
        name="send_email",
        description="Send an email",
    )
    guarded = guard_structured_tool(shield, raw_tool)

    try:
        await guarded.ainvoke(
            {
                "to": "recipient@example.com",
                "subject": "Status",
                "body": "Here is the key: AKIAIOSFODNN7EXAMPLE",
            }
        )
        print("Unexpected: tool call was allowed")
    except LexShieldBlockedError as exc:
        rule_id = exc.verdict.matched_rule_id if exc.verdict else "unknown"
        print(f"BLOCKED (expected): {exc.message} (rule={rule_id})")


if __name__ == "__main__":
    asyncio.run(_demo())
