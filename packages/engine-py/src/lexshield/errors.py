"""LexShield SDK and API errors."""

from __future__ import annotations

from typing import Any

from lexshield.models import Verdict, VerdictType


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


_ERROR_CODES: dict[VerdictType, str] = {
    VerdictType.BLOCK: "lexshield_blocked",
    VerdictType.CHALLENGE: "lexshield_challenged",
    VerdictType.DEFER: "lexshield_deferred",
}


def redact_verdict_for_agent(verdict: Verdict, *, expose_rule_ids: bool) -> Verdict:
    """Return a verdict copy safe for agent-facing surfaces."""
    if expose_rule_ids or verdict.matched_rule_id is None:
        return verdict
    return verdict.model_copy(update={"matched_rule_id": None})


def agent_facing_error(
    verdict: Verdict,
    *,
    expose_rule_ids: bool = True,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build structured agent-facing error payload per SPEC §13.3."""
    code = error_code or _ERROR_CODES.get(verdict.decision, "lexshield_blocked")
    payload: dict[str, Any] = {
        "error": code,
        "verdict": verdict.decision.value,
        "reason": verdict.reason,
        "requestId": verdict.request_id,
        "retryable": False,
    }
    if expose_rule_ids and verdict.matched_rule_id:
        payload["matchedRuleId"] = verdict.matched_rule_id
    if verdict.challenge_id and verdict.decision == VerdictType.CHALLENGE:
        payload["challengeId"] = verdict.challenge_id
    return payload
