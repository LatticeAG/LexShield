"""Classifier pipeline tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from lexshield.classifiers.llm import LLMClassifier
from lexshield.classifiers.pipeline import (
    UNKNOWN_CONFIDENCE,
    UNKNOWN_INTENT,
    ClassifierPipeline,
    merge_classifications,
)
from lexshield.models import (
    Caller,
    CallerType,
    Classification,
    Message,
    PriorCall,
    ToolCallRequest,
    ToolRef,
    VerdictType,
)
from lexshield.shield import Shield


def _request(
    *,
    tool: str = "send_email",
    arguments: dict | None = None,
    messages: list[Message] | None = None,
    prior_calls: list[PriorCall] | None = None,
) -> ToolCallRequest:
    return ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name=tool),
        arguments=arguments or {},
        context={
            "messages": messages,
            "priorCalls": prior_calls,
        },
    )


def _classification(
    intent: str,
    confidence: float,
    *,
    classifier: str = "deterministic:v1",
) -> Classification:
    return Classification(
        intent=intent,
        confidence=confidence,
        alternatives=[],
        classifier=classifier,
    )


@pytest.fixture
def rules_path(tmp_path: Path) -> Path:
    rules = {
        "tool_map": {
            "send_email": "comms.send.email",
            "delete_resource": "infra.delete.resource",
        },
        "patterns": [
            {
                "name": "aws_key",
                "match": {"any_arg_regex": "AKIA[0-9A-Z]{16}"},
                "intent": "security.secret_exposure",
                "confidence": 0.98,
            }
        ],
    }
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.dump(rules), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_skips_llm_when_deterministic_confidence_high(
    rules_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = LLMClassifier()
    llm_mock = AsyncMock()
    llm.classify = llm_mock

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=llm)
    request = _request(
        arguments={"body": "credentials AKIAIOSFODNN7EXAMPLE"},
    )

    results = await pipeline.classify(request)

    assert len(results) == 1
    assert results[0].intent == "security.secret_exposure"
    assert results[0].confidence == 0.98
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_runs_llm_when_deterministic_confidence_low(
    rules_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = LLMClassifier()
    llm_result = _classification(
        "data.exfiltrate",
        0.88,
        classifier="llm:openai:gpt-4o-mini",
    )
    llm.classify = AsyncMock(return_value=llm_result)

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=llm)
    request = _request(tool="send_email", arguments={"to": "a@b.com"})

    results = await pipeline.classify(request)

    assert len(results) == 2
    assert results[0].intent == "data.exfiltrate"
    assert results[1].intent == "comms.send.email"
    llm.classify.assert_awaited_once()


@pytest.mark.asyncio
async def test_merge_prefers_higher_severity_on_disagreement(
    rules_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = LLMClassifier()
    llm.classify = AsyncMock(
        return_value=_classification(
            "security.secret_exposure",
            0.91,
            classifier="llm:openai:gpt-4o-mini",
        )
    )

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=llm)
    request = _request(tool="send_email", arguments={"subject": "hello"})

    results = await pipeline.classify(request)

    assert [item.intent for item in results] == [
        "security.secret_exposure",
        "comms.send.email",
    ]


@pytest.mark.asyncio
async def test_unknown_fallback_when_no_classifiers_hit(
    rules_path: Path,
) -> None:
    pipeline = ClassifierPipeline(rules_path=rules_path, llm=None)
    request = _request(tool="unknown_tool")

    results = await pipeline.classify(request)

    assert len(results) == 1
    assert results[0].intent == UNKNOWN_INTENT
    assert results[0].confidence == UNKNOWN_CONFIDENCE


@pytest.mark.asyncio
async def test_fingerprint_cache_hits_for_deterministic_only(
    rules_path: Path,
) -> None:
    pipeline = ClassifierPipeline(rules_path=rules_path, llm=None)
    request = _request(
        arguments={"body": "credentials AKIAIOSFODNN7EXAMPLE"},
    )

    with patch.object(
        pipeline.deterministic,
        "classify",
        wraps=pipeline.deterministic.classify,
    ) as classify_mock:
        first = await pipeline.classify(request)
        second = await pipeline.classify(request)

    assert first == second
    assert classify_mock.call_count == 1


@pytest.mark.asyncio
async def test_fingerprint_cache_disabled_with_messages(
    rules_path: Path,
) -> None:
    pipeline = ClassifierPipeline(rules_path=rules_path, llm=None)
    request = _request(
        arguments={"body": "credentials AKIAIOSFODNN7EXAMPLE"},
        messages=[Message(role="user", content="send this")],
    )

    with patch.object(
        pipeline.deterministic,
        "classify",
        wraps=pipeline.deterministic.classify,
    ) as classify_mock:
        await pipeline.classify(request)
        await pipeline.classify(request)

    assert classify_mock.call_count == 2


@pytest.mark.asyncio
async def test_fingerprint_cache_disabled_with_prior_calls(
    rules_path: Path,
) -> None:
    pipeline = ClassifierPipeline(rules_path=rules_path, llm=None)
    request = _request(
        arguments={"body": "credentials AKIAIOSFODNN7EXAMPLE"},
        prior_calls=[
            PriorCall(
                timestamp="2026-07-11T12:00:00Z",
                tool=ToolRef(name="send_email"),
                intent="comms.send.email",
                verdict=VerdictType.ALLOW,
            )
        ],
    )

    with patch.object(
        pipeline.deterministic,
        "classify",
        wraps=pipeline.deterministic.classify,
    ) as classify_mock:
        await pipeline.classify(request)
        await pipeline.classify(request)

    assert classify_mock.call_count == 2


@pytest.mark.asyncio
async def test_fingerprint_cache_not_used_when_llm_runs(
    rules_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = LLMClassifier()
    llm.classify = AsyncMock(
        return_value=_classification(
            "comms.send.external",
            0.75,
            classifier="llm:openai:gpt-4o-mini",
        )
    )

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=llm)
    request = _request(tool="send_email", arguments={"to": "a@b.com"})

    with patch.object(
        pipeline.deterministic,
        "classify",
        wraps=pipeline.deterministic.classify,
    ) as classify_mock:
        await pipeline.classify(request)
        await pipeline.classify(request)

    assert classify_mock.call_count == 2
    assert llm.classify.await_count == 2


def test_merge_classifications_tie_breaks_to_higher_confidence() -> None:
    det = _classification("comms.send.email", 0.7)
    llm = _classification("comms.send.email", 0.85, classifier="llm:openai:gpt-4o-mini")

    merged = merge_classifications([det, llm])

    assert merged[0].classifier.startswith("llm")
    assert merged[1].classifier.startswith("deterministic")


def test_merge_classifications_tie_breaks_to_deterministic_on_equal_confidence() -> None:
    det = _classification("comms.send.email", 0.8)
    llm = _classification("comms.send.email", 0.8, classifier="llm:openai:gpt-4o-mini")

    merged = merge_classifications([det, llm])

    assert merged[0].classifier.startswith("deterministic")


def test_shield_from_config_parses_llm_classifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.dump(
            {
                "id": "test-policy",
                "name": "Test",
                "version": "1",
                "defaultVerdict": "BLOCK",
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.dump({"tool_map": {}, "patterns": []}), encoding="utf-8")

    config_path = tmp_path / "lexshield.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "shield": {
                    "id": "local",
                    "name": "local-shield",
                    "policy": "./policy.yaml",
                    "classifiers": [
                        {"type": "deterministic", "path": "./rules.yaml"},
                        {
                            "type": "llm",
                            "model": "openai:gpt-4o-mini",
                            "api_key_env": "TEST_OPENAI_KEY",
                            "base_url_env": "TEST_OPENAI_BASE",
                            "timeout_ms": 1500,
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    shield = Shield.from_config(config_path)
    llm = shield.classifier_pipeline.llm

    assert llm is not None
    assert llm.model == "gpt-4o-mini"
    assert llm.api_key_env == "TEST_OPENAI_KEY"
    assert llm.base_url_env == "TEST_OPENAI_BASE"
    assert llm.timeout_ms == 1500


@pytest.mark.asyncio
async def test_fingerprint_cache_expires_after_ttl(rules_path: Path) -> None:
    from lexshield.classifiers.pipeline import _fingerprint

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=None)
    request = _request(
        arguments={"body": "credentials AKIAIOSFODNN7EXAMPLE"},
    )

    await pipeline.classify(request)
    cache_key = _fingerprint(request)
    cached_value = pipeline._cache._entries[cache_key][1]
    pipeline._cache._entries[cache_key] = (time.monotonic() - 1, cached_value)

    with patch.object(
        pipeline.deterministic,
        "classify",
        wraps=pipeline.deterministic.classify,
    ) as classify_mock:
        await pipeline.classify(request)

    assert classify_mock.call_count == 1
