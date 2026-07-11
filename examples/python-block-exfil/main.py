"""Block exfil demo — send_email with AWS key in body → BLOCK."""

from __future__ import annotations

import asyncio

from lexshield import Shield
from lexshield.errors import LexShieldBlockedError


shield = Shield.from_config("lexshield.yaml")


@shield.guard(tool="send_email")
async def send_email(to: str, subject: str, body: str) -> dict:
    # In a real app this would call your mail provider.
    return {"status": "sent", "to": to}


async def main() -> None:
    try:
        await send_email(
            to="recipient@example.com",
            subject="Status update",
            body="Here is the key: AKIAIOSFODNN7EXAMPLE",
        )
    except LexShieldBlockedError as exc:
        print(f"BLOCKED: {exc.reason} (rule={exc.matched_rule_id})")
        return

    print("Unexpected: tool call was allowed")


if __name__ == "__main__":
    asyncio.run(main())
