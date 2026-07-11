"""Challenge delete demo — delete_resource in production → CHALLENGE."""

from __future__ import annotations

import asyncio

from lexshield import Shield
from lexshield.errors import LexShieldChallengeError


shield = Shield.from_config("lexshield.yaml")


@shield.guard(tool="delete_resource")
async def delete_resource(resource_id: str, reason: str) -> dict:
    return {"status": "deleted", "resource_id": resource_id}


async def main() -> None:
    with shield.session(environment="production"):
        try:
            await delete_resource(
                resource_id="db-primary-replica",
                reason="cleanup old replica",
            )
        except LexShieldChallengeError as exc:
            print(f"CHALLENGE: {exc.reason}")
            print(f"  challenge_id={exc.challenge_id}")
            print("Approve with: lexshield challenge approve", exc.challenge_id)
            return

    print("Unexpected: tool call was allowed")


if __name__ == "__main__":
    asyncio.run(main())
