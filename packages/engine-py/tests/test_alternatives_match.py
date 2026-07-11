"""Tests for intent matching via classification alternatives."""

from __future__ import annotations

from lexshield.models import (
    Caller,
    CallerType,
    Classification,
    IntentAlternative,
    Policy,
    PolicyRule,
    RuleMatch,
    ToolCallRequest,
    ToolRef,
    VerdictType,
)
from lexshield.policy.engine import PolicyEngine
from lexshield.policy.loader import CompiledPolicy
from lexshield.policy.match import rule_matches


def _classification(
    intent: str,
    confidence: float,
    *,
    alternatives: list[tuple[str, float]] | None = None,
) -> Classification:
    return Classification(
        intent=intent,
        confidence=confidence,
        classifier="test",
        alternatives=[
            IntentAlternative(intent=alt_intent, confidence=alt_confidence)
            for alt_intent, alt_confidence in (alternatives or [])
        ],
    )


def _request(tool: str = "http_request") -> ToolCallRequest:
    return ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name=tool),
        arguments={},
        context={},
    )


def _compiled_rule(intent: str) -> object:
    compiled = CompiledPolicy.from_policy(
        Policy(
            id="alt-policy",
            name="Alt policy",
            version="1",
            defaultVerdict=VerdictType.BLOCK,
            rules=[
                PolicyRule(
                    id="block-exfil",
                    name="Block exfil",
                    priority=100,
                    match=RuleMatch(intents=[intent]),
                    verdict=VerdictType.BLOCK,
                    reason="Blocked exfil",
                ),
            ],
        )
    )
    return compiled.rules[0]


def test_alternative_intent_matches_at_default_threshold() -> None:
    compiled_rule = _compiled_rule("data.exfiltrate")
    classifications = [
        _classification(
            "network.request.http",
            0.6,
            alternatives=[("data.exfiltrate", 0.4)],
        )
    ]

    assert rule_matches(compiled_rule, _request(), classifications) is True


def test_alternative_intent_matches_above_custom_threshold() -> None:
    policy = Policy(
        id="custom-threshold",
        name="Custom threshold",
        version="1",
        defaultVerdict=VerdictType.BLOCK,
        severity_threshold={"alternatives_min_confidence": 0.5},
        rules=[
            PolicyRule(
                id="block-exfil",
                name="Block exfil",
                priority=100,
                match=RuleMatch(intents=["data.exfiltrate"]),
                verdict=VerdictType.BLOCK,
                reason="Blocked exfil",
            ),
        ],
    )
    engine = PolicyEngine(CompiledPolicy.from_policy(policy))
    classifications = [
        _classification(
            "network.request.http",
            0.6,
            alternatives=[("data.exfiltrate", 0.55)],
        )
    ]

    verdict = engine.evaluate(_request(), classifications)

    assert verdict.decision == VerdictType.BLOCK
    assert verdict.matched_rule_id == "block-exfil"


def test_alternative_intent_below_threshold_does_not_match() -> None:
    compiled_rule = _compiled_rule("data.exfiltrate")
    classifications = [
        _classification(
            "network.request.http",
            0.6,
            alternatives=[("data.exfiltrate", 0.39)],
        )
    ]

    assert rule_matches(compiled_rule, _request(), classifications) is False


def test_primary_intent_matches_without_alternative_threshold() -> None:
    compiled_rule = _compiled_rule("security.secret_exposure")
    classifications = [_classification("security.secret_exposure", 0.2)]

    assert rule_matches(compiled_rule, _request(tool="send_email"), classifications) is True
