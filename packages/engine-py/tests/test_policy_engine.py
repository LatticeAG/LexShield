"""Policy engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexshield.models import (
    Caller,
    CallerType,
    Classification,
    Policy,
    PolicyRule,
    RuleMatch,
    ToolCallRequest,
    ToolRef,
    VerdictType,
)
from lexshield.policy.engine import PolicyEngine
from lexshield.policy.expressions import Expression, ExpressionError
from lexshield.policy.loader import CompiledPolicy, load_policy
from lexshield.policy.match import build_expression_bindings, rule_matches

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"
BASELINE_POLICY_PATH = PACKS_DIR / "baseline-deny" / "policy.yaml"


def _classification(
    intent: str,
    confidence: float = 0.9,
    *,
    alternatives: list[tuple[str, float]] | None = None,
) -> Classification:
    return Classification(
        intent=intent,
        confidence=confidence,
        classifier="test",
        alternatives=[
            {"intent": alt_intent, "confidence": alt_confidence}
            for alt_intent, alt_confidence in (alternatives or [])
        ],
    )


def _request(
    *,
    tool: str = "health_check",
    arguments: dict | None = None,
    environment: str | None = None,
    tags: dict[str, str] | None = None,
    caller_id: str = "agent-1",
    caller_roles: list[str] | None = None,
) -> ToolCallRequest:
    return ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(
            id=caller_id,
            type=CallerType.AGENT,
            roles=caller_roles,
        ),
        tool=ToolRef(name=tool),
        arguments=arguments or {},
        context={
            "environment": environment,
            "tags": tags,
        },
    )


def _engine_for_policy(policy: Policy) -> PolicyEngine:
    return PolicyEngine(CompiledPolicy.from_policy(policy))


@pytest.fixture
def baseline_engine() -> PolicyEngine:
    compiled = load_policy(BASELINE_POLICY_PATH)
    return PolicyEngine(compiled)


def test_allow_health(baseline_engine: PolicyEngine) -> None:
    request = _request(tool="health_check")
    classifications = [_classification("network.request.health")]

    verdict = baseline_engine.evaluate(request, classifications)

    assert verdict.decision == VerdictType.ALLOW
    assert verdict.matched_rule_id == "allow-health"
    assert verdict.reason == "Health checks are always allowed"


def test_block_secret_exposure(baseline_engine: PolicyEngine) -> None:
    request = _request(tool="send_email", arguments={"body": "AKIAIOSFODNN7EXAMPLE"})
    classifications = [_classification("security.secret_exposure", 0.98)]

    verdict = baseline_engine.evaluate(request, classifications)

    assert verdict.decision == VerdictType.BLOCK
    assert verdict.matched_rule_id == "block-secret-exposure"
    assert verdict.reason == "Possible secret exposure in tool arguments"


def test_challenge_delete_prod(baseline_engine: PolicyEngine) -> None:
    request = _request(
        tool="delete_resource",
        environment="production",
    )
    classifications = [_classification("infra.delete.resource", 0.95)]

    verdict = baseline_engine.evaluate(request, classifications)

    assert verdict.decision == VerdictType.CHALLENGE
    assert verdict.matched_rule_id == "challenge-delete-prod"
    assert verdict.reason == "Destructive action in production requires approval"
    assert verdict.challenge_id == "challenge-01JTEST"


def test_priority_tie_break_by_rule_id() -> None:
    policy = Policy(
        id="tie-break",
        name="Tie break",
        version="1",
        defaultVerdict=VerdictType.BLOCK,
        rules=[
            PolicyRule(
                id="rule-b",
                name="Rule B",
                priority=300,
                match=RuleMatch(intents=["security.secret_exposure"]),
                verdict=VerdictType.BLOCK,
                reason="Blocked by rule-b",
            ),
            PolicyRule(
                id="rule-a",
                name="Rule A",
                priority=300,
                match=RuleMatch(intents=["security.secret_exposure"]),
                verdict=VerdictType.ALLOW,
                reason="Allowed by rule-a",
            ),
        ],
    )
    engine = _engine_for_policy(policy)
    request = _request(tool="send_email")
    classifications = [_classification("security.secret_exposure")]

    verdict = engine.evaluate(request, classifications)

    assert verdict.decision == VerdictType.ALLOW
    assert verdict.matched_rule_id == "rule-a"


def test_default_deny_when_no_rule_matches(baseline_engine: PolicyEngine) -> None:
    request = _request(tool="unknown_tool")
    classifications = [_classification("unknown.unclassified", 0.2)]

    verdict = baseline_engine.evaluate(request, classifications)

    assert verdict.decision == VerdictType.BLOCK
    assert verdict.matched_rule_id is None
    assert "default deny for unclassified intent" in verdict.reason


def test_glob_tools_match() -> None:
    policy = Policy(
        id="glob-tools",
        name="Glob tools",
        version="1",
        defaultVerdict=VerdictType.BLOCK,
        rules=[
            PolicyRule(
                id="allow-send",
                name="Allow send tools",
                priority=100,
                match=RuleMatch(
                    tools=["send_*"],
                    intents=["comms.send.email"],
                ),
                verdict=VerdictType.ALLOW,
                reason="Send tools allowed",
            ),
        ],
    )
    engine = _engine_for_policy(policy)
    request = _request(tool="send_email")
    classifications = [_classification("comms.send.email")]

    verdict = engine.evaluate(request, classifications)

    assert verdict.decision == VerdictType.ALLOW
    assert verdict.matched_rule_id == "allow-send"


def test_tags_match_requires_all_keys() -> None:
    policy = Policy(
        id="tag-policy",
        name="Tag policy",
        version="1",
        defaultVerdict=VerdictType.BLOCK,
        rules=[
            PolicyRule(
                id="challenge-pii",
                name="Challenge PII",
                priority=200,
                match=RuleMatch(
                    intents=["comms.send.email"],
                    tags={"data_class": ["pii"], "region": ["us"]},
                ),
                verdict=VerdictType.CHALLENGE,
                reason="PII egress requires approval",
            ),
        ],
    )
    engine = _engine_for_policy(policy)
    request = _request(
        tool="send_email",
        tags={"data_class": "pii"},
    )
    classifications = [_classification("comms.send.email")]

    blocked = engine.evaluate(request, classifications)
    assert blocked.decision == VerdictType.BLOCK
    assert blocked.matched_rule_id is None

    request_with_tags = _request(
        tool="send_email",
        tags={"data_class": "pii", "region": "us"},
    )
    challenged = engine.evaluate(request_with_tags, classifications)
    assert challenged.decision == VerdictType.CHALLENGE
    assert challenged.matched_rule_id == "challenge-pii"


def test_expression_evaluation() -> None:
    policy = Policy(
        id="expr-policy",
        name="Expression policy",
        version="1",
        defaultVerdict=VerdictType.BLOCK,
        rules=[
            PolicyRule(
                id="block-gmail",
                name="Block gmail recipients",
                priority=250,
                match=RuleMatch(
                    intents=["comms.send.email"],
                    expression='env == "production" && args.to contains "@gmail.com"',
                ),
                verdict=VerdictType.BLOCK,
                reason="Gmail not allowed in production",
            ),
            PolicyRule(
                id="allow-allowlisted-url",
                name="Allow allowlisted URL",
                priority=200,
                match=RuleMatch(
                    intents=["network.request.http"],
                    expression='args.url startsWith "https://api.mycompany.com/"',
                ),
                verdict=VerdictType.ALLOW,
                reason="Allowlisted host",
            ),
        ],
    )
    engine = _engine_for_policy(policy)

    blocked_request = _request(
        tool="send_email",
        arguments={"to": "user@gmail.com"},
        environment="production",
    )
    blocked = engine.evaluate(
        blocked_request,
        [_classification("comms.send.email")],
    )
    assert blocked.decision == VerdictType.BLOCK
    assert blocked.matched_rule_id == "block-gmail"

    allowed_request = _request(
        tool="http_request",
        arguments={"url": "https://api.mycompany.com/v1/data"},
    )
    allowed = engine.evaluate(
        allowed_request,
        [_classification("network.request.http")],
    )
    assert allowed.decision == VerdictType.ALLOW
    assert allowed.matched_rule_id == "allow-allowlisted-url"


def test_expression_parser_rejects_empty_expression() -> None:
    with pytest.raises(ExpressionError):
        Expression.parse("   ")


def test_expression_supports_in_operator() -> None:
    expr = Expression.parse('intent in ["comms.send.email", "comms.send.slack"]')
    bindings = {
        "intent": "comms.send.email",
        "confidence": 0.9,
        "tool.name": "send_email",
        "caller.id": "agent-1",
        "caller.type": "agent",
        "env": "staging",
    }
    assert expr.evaluate(bindings) is True


def test_expression_numeric_comparison() -> None:
    expr = Expression.parse("confidence >= 0.7")
    bindings = build_expression_bindings(
        _request(),
        [_classification("network.request.health", 0.75)],
    )
    assert expr.evaluate(bindings) is True


def test_rule_matches_alternative_intent() -> None:
    compiled = CompiledPolicy.from_policy(
        Policy(
            id="alt-intent",
            name="Alt intent",
            version="1",
            defaultVerdict=VerdictType.BLOCK,
            rules=[
                PolicyRule(
                    id="allow-alt",
                    name="Allow alt",
                    priority=100,
                    match=RuleMatch(intents=["data.exfiltrate"]),
                    verdict=VerdictType.BLOCK,
                    reason="Blocked exfil",
                ),
            ],
        )
    )
    request = _request(tool="http_request")
    classifications = [
        _classification(
            "network.request.http",
            0.6,
            alternatives=[("data.exfiltrate", 0.4)],
        )
    ]

    assert rule_matches(compiled.rules[0], request, classifications) is True


def test_disabled_rules_are_skipped() -> None:
    policy = Policy(
        id="disabled",
        name="Disabled",
        version="1",
        defaultVerdict=VerdictType.ALLOW,
        rules=[
            PolicyRule(
                id="disabled-block",
                name="Disabled block",
                priority=500,
                enabled=False,
                match=RuleMatch(tools=["health_check"]),
                verdict=VerdictType.BLOCK,
                reason="Would block",
            ),
        ],
    )
    engine = _engine_for_policy(policy)
    verdict = engine.evaluate(
        _request(tool="health_check"),
        [_classification("network.request.health")],
    )
    assert verdict.decision == VerdictType.ALLOW
    assert verdict.matched_rule_id is None
