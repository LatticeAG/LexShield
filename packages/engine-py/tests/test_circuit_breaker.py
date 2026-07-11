"""LLM circuit breaker and fail_on_classifier_error tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml

from lexshield.classifiers.llm import CircuitBreaker, LLMClassifier
from lexshield.classifiers.pipeline import ClassifierPipeline
from lexshield.models import Caller, CallerType, ToolCallRequest, ToolRef, VerdictType
from lexshield.shield import Shield


def _request(tool: str = "unknown_tool") -> ToolCallRequest:
    return ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name=tool),
        arguments={},
    )


def test_circuit_breaker_opens_after_five_failures_in_window() -> None:
    breaker = CircuitBreaker(failure_threshold=5, window_seconds=60, open_seconds=30)

    for _ in range(4):
        breaker.record_failure()
        assert not breaker.is_open()

    breaker.record_failure()
    assert breaker.is_open()
    assert breaker.circuit_open_count == 1


def test_circuit_breaker_closes_after_open_duration() -> None:
    breaker = CircuitBreaker(
        failure_threshold=1,
        window_seconds=60,
        open_seconds=0.1,
    )
    breaker.record_failure()
    assert breaker.is_open()

    time.sleep(0.15)
    assert not breaker.is_open()


def test_circuit_breaker_resets_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=5, window_seconds=60, open_seconds=30)
    for _ in range(4):
        breaker.record_failure()

    breaker.record_success()
    for _ in range(4):
        breaker.record_failure()

    assert not breaker.is_open()


@pytest.mark.asyncio
async def test_llm_skips_calls_when_circuit_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    classifier = LLMClassifier()
    classifier.circuit_breaker._open_until = time.monotonic() + 30

    mock_post = AsyncMock()
    with patch("httpx.AsyncClient.post", mock_post):
        result = await classifier.classify(_request())

    assert result is None
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_llm_opens_circuit_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    classifier = LLMClassifier()
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient.post", mock_post):
        for _ in range(5):
            await classifier.classify(_request())

    assert classifier.circuit_breaker.is_open()
    assert classifier.circuit_open_count == 1


@pytest.mark.asyncio
async def test_pipeline_sets_classifier_error_when_all_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.dump({"tool_map": {}, "patterns": []}), encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = LLMClassifier()
    llm.classify = AsyncMock(return_value=None)

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=llm)
    await pipeline.classify(_request())

    assert pipeline.last_classifier_error is True


@pytest.mark.asyncio
async def test_pipeline_no_classifier_error_when_deterministic_hits(
    tmp_path: Path,
) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        yaml.dump({"tool_map": {"send_email": "comms.send.email"}, "patterns": []}),
        encoding="utf-8",
    )

    pipeline = ClassifierPipeline(rules_path=rules_path, llm=None)
    await pipeline.classify(_request(tool="send_email"))

    assert pipeline.last_classifier_error is False


@pytest.mark.asyncio
async def test_shield_applies_fail_on_classifier_error(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.dump(
            {
                "id": "test-policy",
                "name": "Test",
                "version": "1",
                "defaultVerdict": "ALLOW",
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.dump({"tool_map": {}, "patterns": []}), encoding="utf-8")

    shield = Shield(
        shield_id="test",
        name="test",
        policy_path=policy_path,
        rules_path=rules_path,
        fail_on_classifier_error=VerdictType.CHALLENGE,
    )

    verdict = await shield.evaluate(tool="totally_unknown_tool")

    assert verdict.decision == VerdictType.CHALLENGE
    assert "fail_on_classifier_error" in verdict.reason
