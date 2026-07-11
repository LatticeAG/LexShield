"""Challenge notification channels (stdout, webhook)."""

from __future__ import annotations

import json
import sys
import threading
from typing import Any

import httpx

from lexshield.models import ChallengeChannel

_WEBHOOK_TIMEOUT_SECONDS = 2.0


def _format_summary(record: dict[str, Any]) -> str:
    return (
        f"[LexShield Challenge] id={record.get('id')} "
        f"request={record.get('requestId')} "
        f"reason={record.get('reason')} "
        f"timeout={record.get('timeoutSeconds')}s"
    )


def _post_webhook(url: str, payload: dict[str, Any]) -> None:
    try:
        with httpx.Client(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
            client.post(url, json=payload)
    except httpx.HTTPError:
        pass


def notify_challenge_created(
    record: dict[str, Any],
    *,
    channel: ChallengeChannel,
    webhook_url: str | None = None,
) -> None:
    """Notify reviewers when a challenge is created."""
    if channel == ChallengeChannel.STDOUT:
        print(_format_summary(record), file=sys.stdout, flush=True)
        return

    if channel == ChallengeChannel.WEBHOOK:
        url = webhook_url or record.get("webhookUrl")
        if not url:
            return
        threading.Thread(
            target=_post_webhook,
            args=(url, record),
            daemon=True,
        ).start()
