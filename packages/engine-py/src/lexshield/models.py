"""Pydantic v2 models matching SPEC §19 data model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VerdictType(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    CHALLENGE = "CHALLENGE"
    DEFER = "DEFER"


class CallerType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SERVICE_ACCOUNT = "service_account"


class OutcomeType(str, Enum):
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    CHALLENGED = "CHALLENGED"
    DEFERRED = "DEFERRED"
    ERROR = "ERROR"
    APPROVED_EXECUTED = "APPROVED_EXECUTED"
    DENIED = "DENIED"


class ChallengeChannel(str, Enum):
    STDOUT = "stdout"
    WEBHOOK = "webhook"
    SLACK = "slack"
    DASHBOARD = "dashboard"


class SinkType(str, Enum):
    STDOUT = "stdout"
    FILE = "file"
    HTTP = "http"
    OTLP = "otlp"


class RuleMatch(BaseModel):
    intents: list[str] | None = None
    tools: list[str] | None = None
    callers: list[str] | None = None
    roles: list[str] | None = None
    environments: list[str] | None = None
    tags: dict[str, list[str]] | None = None
    min_confidence: float | None = Field(default=None, alias="minConfidence")
    expression: str | None = None

    model_config = {"populate_by_name": True}


class ChallengeConfig(BaseModel):
    channel: ChallengeChannel
    timeout_seconds: int = Field(alias="timeoutSeconds")
    on_timeout: VerdictType = Field(alias="onTimeout")
    reviewers: list[str] | None = None

    model_config = {"populate_by_name": True}


class PolicyRule(BaseModel):
    id: str
    name: str
    priority: int
    enabled: bool = True
    match: RuleMatch
    verdict: VerdictType
    reason: str
    challenge: ChallengeConfig | None = None


class Policy(BaseModel):
    id: str
    name: str
    version: str
    description: str | None = None
    default_verdict: VerdictType = Field(alias="defaultVerdict")
    rules: list[PolicyRule]
    taxonomy_ref: str | None = Field(default=None, alias="taxonomyRef")
    severity_threshold: dict[str, Any] | None = Field(
        default=None, alias="severity_threshold"
    )

    model_config = {"populate_by_name": True}


class Caller(BaseModel):
    id: str
    type: CallerType
    roles: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ToolRef(BaseModel):
    name: str
    namespace: str | None = None
    version: str | None = None


class Message(BaseModel):
    role: str
    content: str


class PriorCall(BaseModel):
    timestamp: str
    tool: ToolRef
    intent: str
    verdict: VerdictType


class CallContext(BaseModel):
    conversation_id: str | None = Field(default=None, alias="conversationId")
    messages: list[Message] | None = None
    prior_calls: list[PriorCall] | None = Field(default=None, alias="priorCalls")
    environment: str | None = None
    tags: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class ToolCallRequest(BaseModel):
    id: str | None = None
    shield_id: str = Field(alias="shieldId")
    timestamp: str | None = None
    caller: Caller
    tool: ToolRef
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: CallContext = Field(default_factory=CallContext)

    model_config = {"populate_by_name": True}


class IntentAlternative(BaseModel):
    intent: str
    confidence: float


class Classification(BaseModel):
    intent: str
    confidence: float
    alternatives: list[IntentAlternative] = Field(default_factory=list)
    classifier: str
    reasoning: str | None = None
    signals_used: list[str] | None = Field(default=None, alias="signalsUsed")

    model_config = {"populate_by_name": True}


class Verdict(BaseModel):
    request_id: str = Field(alias="requestId")
    decision: VerdictType
    matched_rule_id: str | None = Field(default=None, alias="matchedRuleId")
    reason: str
    classifications: list[Classification] = Field(default_factory=list)
    duration_ms: float = Field(alias="durationMs")
    challenge_id: str | None = Field(default=None, alias="challengeId")
    policy_version: str | None = Field(default=None, alias="policyVersion")

    model_config = {"populate_by_name": True}


class Trace(BaseModel):
    id: str
    request: ToolCallRequest
    verdict: Verdict
    outcome: OutcomeType | None = None
    outcome_at: str | None = Field(default=None, alias="outcomeAt")
    redactions: list[str] | None = None
    metadata: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class PolicyRef(BaseModel):
    policy_id: str = Field(alias="policyId")
    version: str | None = None

    model_config = {"populate_by_name": True}


class SinkConfig(BaseModel):
    type: SinkType
    options: dict[str, Any] = Field(default_factory=dict)


class UpstreamConfig(BaseModel):
    url: str
    headers: dict[str, str] | None = None
    timeout_ms: int | None = Field(default=None, alias="timeoutMs")

    model_config = {"populate_by_name": True}


class ShieldConfig(BaseModel):
    id: str
    name: str
    policy_ref: PolicyRef = Field(alias="policyRef")
    classifier_ids: list[str] = Field(alias="classifierIds")
    sinks: list[SinkConfig] = Field(default_factory=list)
    tool_upstreams: dict[str, UpstreamConfig] | None = Field(
        default=None, alias="toolUpstreams"
    )
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}
