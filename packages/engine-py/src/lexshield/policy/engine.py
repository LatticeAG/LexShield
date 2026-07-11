"""Policy evaluation engine."""

from __future__ import annotations

import time

from lexshield.models import Classification, Policy, ToolCallRequest, Verdict, VerdictType
from lexshield.policy.loader import CompiledPolicy
from lexshield.policy.match import rule_matches, sort_rules

UNKNOWN_INTENT = "unknown.unclassified"


class PolicyEngine:
    """Evaluates policy rules against classified tool call requests."""

    def __init__(self, policy: CompiledPolicy | Policy) -> None:
        if isinstance(policy, Policy):
            self._compiled = CompiledPolicy.from_policy(policy)
        else:
            self._compiled = policy
        self._sorted_rules = sort_rules(self._compiled.rules)

    @property
    def policy(self) -> Policy:
        return self._compiled.policy

    def evaluate(
        self,
        request: ToolCallRequest,
        classifications: list[Classification],
    ) -> Verdict:
        """Evaluate policy for a request and return the winning verdict."""
        start = time.perf_counter()
        request_id = request.id or "unknown"

        primary = classifications[0] if classifications else None

        matched_rule = next(
            (
                compiled
                for compiled in self._sorted_rules
                if rule_matches(compiled, request, classifications)
            ),
            None,
        )

        duration_ms = (time.perf_counter() - start) * 1000

        if matched_rule is not None:
            rule = matched_rule.rule
            challenge_id = None
            if rule.verdict == VerdictType.CHALLENGE:
                challenge_id = f"challenge-{request_id}"
            return Verdict(
                requestId=request_id,
                decision=rule.verdict,
                matchedRuleId=rule.id,
                reason=rule.reason,
                classifications=classifications,
                durationMs=duration_ms,
                challengeId=challenge_id,
                policyVersion=self.policy.version,
            )

        if primary is None or primary.intent == UNKNOWN_INTENT:
            return Verdict(
                requestId=request_id,
                decision=VerdictType.BLOCK,
                reason="No matching policy rule; default deny for unclassified intent",
                classifications=classifications,
                durationMs=duration_ms,
                policyVersion=self.policy.version,
            )

        default = self.policy.default_verdict
        return Verdict(
            requestId=request_id,
            decision=default,
            reason=f"No matching rule; applied default verdict {default.value}",
            classifications=classifications,
            durationMs=duration_ms,
            policyVersion=self.policy.version,
        )
