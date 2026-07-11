"""Challenge expiry tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lexshield.challenges.store import ChallengeStore
from lexshield.models import VerdictType


def _write_open_challenge(
    store: ChallengeStore,
    *,
    challenge_id: str,
    timeout_seconds: int,
    created_at: datetime,
) -> None:
    record = {
        "id": challenge_id,
        "requestId": "req-1",
        "reason": "needs approval",
        "status": "open",
        "timeoutSeconds": timeout_seconds,
        "onTimeout": VerdictType.BLOCK.value,
        "createdAt": created_at.isoformat(),
    }
    path = store.base_path / f"{challenge_id}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def test_expire_open_marks_past_deadline_as_timed_out(tmp_path: Path) -> None:
    store = ChallengeStore(tmp_path / "challenges")
    created = datetime.now(timezone.utc) - timedelta(seconds=120)
    _write_open_challenge(
        store,
        challenge_id="expired-1",
        timeout_seconds=60,
        created_at=created,
    )
    _write_open_challenge(
        store,
        challenge_id="still-open",
        timeout_seconds=3600,
        created_at=datetime.now(timezone.utc),
    )

    expired = store.expire_open()

    assert len(expired) == 1
    assert expired[0]["id"] == "expired-1"
    assert expired[0]["status"] == "timed_out"
    assert expired[0]["onTimeout"] == VerdictType.BLOCK.value
    assert "resolvedAt" in expired[0]

    record = store.get("expired-1")
    assert record is not None
    assert record["status"] == "timed_out"

    still_open = store.get("still-open")
    assert still_open is not None
    assert still_open["status"] == "open"


def test_list_open_excludes_expired_challenges(tmp_path: Path) -> None:
    store = ChallengeStore(tmp_path / "challenges")
    created = datetime.now(timezone.utc) - timedelta(seconds=10)
    _write_open_challenge(
        store,
        challenge_id="expired-2",
        timeout_seconds=5,
        created_at=created,
    )

    open_challenges = store.list_open()

    assert open_challenges == []


def test_expire_open_returns_empty_when_none_expired(tmp_path: Path) -> None:
    store = ChallengeStore(tmp_path / "challenges")
    store.create(
        request_id="req-1",
        reason="pending",
        timeout_seconds=3600,
        on_timeout=VerdictType.BLOCK,
    )

    assert store.expire_open() == []
