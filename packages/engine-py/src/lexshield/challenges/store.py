"""Local challenge store under .lexshield/challenges."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from lexshield.models import VerdictType


class ChallengeStore:
    """File-based local challenge queue."""

    def __init__(self, base_path: str | Path = ".lexshield/challenges") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        request_id: str,
        reason: str,
        timeout_seconds: int = 3600,
        on_timeout: VerdictType = VerdictType.BLOCK,
    ) -> str:
        """Create an open challenge and return its id."""
        challenge_id = str(uuid4())
        record: dict[str, Any] = {
            "id": challenge_id,
            "requestId": request_id,
            "reason": reason,
            "status": "open",
            "timeoutSeconds": timeout_seconds,
            "onTimeout": on_timeout.value,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        path = self.base_path / f"{challenge_id}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return challenge_id

    def get(self, challenge_id: str) -> dict[str, Any] | None:
        """Return a challenge record by id."""
        path = self.base_path / f"{challenge_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_open(self) -> list[dict[str, Any]]:
        """List open challenges."""
        self.expire_open()
        open_challenges: list[dict[str, Any]] = []
        for path in sorted(self.base_path.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("status") == "open":
                open_challenges.append(record)
        return open_challenges

    def expire_open(self) -> list[dict[str, Any]]:
        """Mark open challenges past timeout as timed_out; return expired records."""
        now = datetime.now(timezone.utc)
        expired: list[dict[str, Any]] = []

        for path in sorted(self.base_path.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("status") != "open":
                continue

            created_raw = record.get("createdAt")
            if not created_raw:
                continue

            created = datetime.fromisoformat(created_raw)
            timeout_seconds = int(record.get("timeoutSeconds", 3600))
            deadline = created + timedelta(seconds=timeout_seconds)
            if now < deadline:
                continue

            record["status"] = "timed_out"
            record["resolvedAt"] = now.isoformat()
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            expired.append(record)

        return expired

    def resolve(
        self,
        challenge_id: str,
        *,
        decision: str,
        actor: str,
    ) -> dict[str, Any] | None:
        """Resolve a challenge as approve or deny."""
        path = self.base_path / f"{challenge_id}.json"
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        record["status"] = "approved" if decision == "approve" else "denied"
        record["resolvedAt"] = datetime.now(timezone.utc).isoformat()
        record["actor"] = actor
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record
