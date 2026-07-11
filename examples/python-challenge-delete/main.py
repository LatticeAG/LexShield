"""Challenge delete demo — delete_resource in production → CHALLENGE → approve → execute."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from lexshield import Shield
from lexshield.errors import LexShieldChallengeError

EXAMPLE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EXAMPLE_DIR / "lexshield.yaml"

shield = Shield.from_config(CONFIG_PATH)


@shield.guard(tool="delete_resource")
async def delete_resource(resource_id: str, reason: str) -> dict:
    return {"status": "deleted", "resource_id": resource_id}


@shield.guard(tool="delete_resource", await_challenge=True)
async def delete_resource_await(resource_id: str, reason: str) -> dict:
    return {"status": "deleted", "resource_id": resource_id}


async def trigger_challenge() -> str | None:
    """Raise CHALLENGE without blocking and return the challenge id."""
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
            return challenge_id

    print("Unexpected: tool call was allowed without challenge")
    return None


def approve_via_cli(challenge_id: str) -> None:
    """Approve using the lexshield CLI (documented human-in-the-loop step)."""
    command = [
        "lexshield",
        "challenge",
        "approve",
        challenge_id,
        "-c",
        str(EXAMPLE_DIR),
    ]
    print()
    print("Approving via CLI:")
    print(f"  {' '.join(command)}")
    print()
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        raise SystemExit(result.returncode)


async def wait_for_open_challenge(
    *,
    ignore_ids: set[str] | None = None,
    timeout_seconds: float = 2.0,
) -> str:
    """Poll the local store until a new open challenge appears."""
    import time

    ignored = ignore_ids or set()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        open_challenges = [
            record
            for record in shield.challenge_store.list_open()
            if record["id"] not in ignored
        ]
        if open_challenges:
            return open_challenges[-1]["id"]
        await asyncio.sleep(0.05)
    raise SystemExit("Timed out waiting for CHALLENGE record")


async def execute_with_cli_approve(
    *,
    resource_id: str,
    reason: str,
) -> dict:
    """Block on await_challenge while approving the new challenge via CLI."""

    async def run_guard() -> dict:
        with shield.session(environment="production"):
            return await delete_resource_await(resource_id=resource_id, reason=reason)

    existing_ids = {record["id"] for record in shield.challenge_store.list_open()}
    task = asyncio.create_task(run_guard())
    challenge_id = await wait_for_open_challenge(ignore_ids=existing_ids)
    print(f"CHALLENGE while awaiting approval: challenge_id={challenge_id}")
    approve_via_cli(challenge_id)
    return await task


async def run_full_demo() -> None:
    """End-to-end: CLI approve during await_challenge, then execute."""
    print("=== CHALLENGE → CLI approve → execute ===")
    result = await execute_with_cli_approve(
        resource_id="db-primary-replica",
        reason="cleanup old replica",
    )
    print()
    print("ALLOW after approval:")
    print(f"  {result}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--challenge-only",
        action="store_true",
        help="Only trigger CHALLENGE and print the lexshield challenge approve command.",
    )
    args = parser.parse_args()

    if args.challenge_only:
        challenge_id = await trigger_challenge()
        if not challenge_id:
            raise SystemExit(1)
        print()
        print("Approve manually, then run the full demo:")
        print(f"  lexshield challenge approve {challenge_id} -c {EXAMPLE_DIR}")
        print("  uv run --project ../.. python main.py")
        return

    await run_full_demo()


if __name__ == "__main__":
    asyncio.run(main())
