"""Policy evaluation engine (stub)."""

from __future__ import annotations

import time

from lexshield.models import (
    Classification,
    Policy,
    ToolCallRequest,
    Verdict,
    VerdictType,
)


class PolicyEngine:
    """Evaluates policy rules against classified tool call requests."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    def evaluate(
        self,
        request: ToolCallRequest,
        classifications: list[Classification],
    ) -> Verdict:
        """Evaluate policy for a request.

        Stub: returns BLOCK for unknown/unclassified intents; otherwise defaultVerdict.
        """
        start = time.perf_counter()
        request_id = request.id or "unknown"

        primary = classifications[0] if classifications else None
        if primary is None or primary.intent == "unknown.unclassified":
            duration_ms = (time.perf_counter() - start) * 1000
            return Verdict(
                requestId=request_id,
                decision=VerdictType.BLOCK,
                reason="No matching policy rule; default deny for unclassified intent",
                classifications=classifications,
                durationMs=duration_ms,
                policyVersion=self.policy.version,
            )

        duration_ms = (time.perf_counter() - start) * 1000
        return Verdict(
            requestId=request_id,
            decision=self.policy.default_verdict,
            reason=f"No rule matched; default verdict {self.policy.default_verdict.value}",
            classifications=classifications,
            durationMs=duration_ms,
            policyVersion=self.policy.version,
        )
