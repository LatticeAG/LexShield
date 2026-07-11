"""LexShield SDK and API errors."""

from __future__ import annotations

from lexshield.models import Verdict


class LexShieldError(Exception):
    """Base LexShield error."""

    def __init__(
        self,
        message: str,
        *,
        verdict: Verdict | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.verdict = verdict
        self.request_id = request_id or (verdict.request_id if verdict else None)


class LexShieldBlockedError(LexShieldError):
    """Raised when a tool call is blocked by policy."""


class LexShieldChallengeError(LexShieldError):
    """Raised when a tool call requires human approval."""


class LexShieldConfigError(LexShieldError):
    """Raised when configuration or policy is invalid."""
