"""Basic model validation tests."""

from lexshield.models import (
    Caller,
    CallerType,
    Classification,
    Policy,
    PolicyRule,
    RuleMatch,
    ToolCallRequest,
    ToolRef,
    Verdict,
    VerdictType,
)


def test_verdict_type_values() -> None:
    assert VerdictType.ALLOW.value == "ALLOW"
    assert VerdictType.BLOCK.value == "BLOCK"
    assert VerdictType.CHALLENGE.value == "CHALLENGE"
    assert VerdictType.DEFER.value == "DEFER"


def test_tool_call_request_roundtrip() -> None:
    request = ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name="send_email"),
        arguments={"to": "a@b.com"},
    )
    data = request.model_dump(by_alias=True)
    restored = ToolCallRequest.model_validate(data)
    assert restored.tool.name == "send_email"
    assert restored.caller.id == "agent-1"


def test_policy_model_accepts_spec_shape() -> None:
    policy = Policy(
        id="baseline-deny",
        name="Baseline",
        version="1",
        defaultVerdict=VerdictType.BLOCK,
        rules=[
            PolicyRule(
                id="allow-health",
                name="Allow health",
                priority=100,
                match=RuleMatch(
                    tools=["health_check"],
                    intents=["network.request.health"],
                ),
                verdict=VerdictType.ALLOW,
                reason="Health checks allowed",
            )
        ],
    )
    assert policy.default_verdict == VerdictType.BLOCK
    assert policy.rules[0].id == "allow-health"


def test_verdict_serialization() -> None:
    verdict = Verdict(
        requestId="01JTEST",
        decision=VerdictType.BLOCK,
        reason="blocked",
        classifications=[
            Classification(
                intent="security.secret_exposure",
                confidence=0.98,
                classifier="deterministic:v1",
            )
        ],
        durationMs=1.5,
    )
    dumped = verdict.model_dump(by_alias=True)
    assert dumped["requestId"] == "01JTEST"
    assert dumped["decision"] == "BLOCK"
