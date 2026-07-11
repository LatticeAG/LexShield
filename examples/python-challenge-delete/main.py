"""Challenge delete demo — delete_resource in production → CHALLENGE."""

from __future__ import annotations

import asyncio
from pathlib import Path

from lexshield import Shield
from lexshield.errors import LexShieldChallengeError

EXAMPLE_DIR = Path(__file__).resolve().parent

shield = Shield.from_config(EXAMPLE_DIR / "lexshield.yaml")


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
            challenge_id = exc.verdict.challenge_id if exc.verdict else None
            print(f"CHALLENGE: {exc.message}")
            if challenge_id:
                print(f"  challenge_id={challenge_id}")
                print()
                print("Approve from this directory:")
                print(f"  lexshield challenge approve {challenge_id}")
                print()
                print("Then re-run with await_challenge=True on the guard decorator")
                print("to block until approval (see docs/sdk-python.md).")
            return

    print("Unexpected: tool call was allowed")


if __name__ == "__main__":
    asyncio.run(main())
