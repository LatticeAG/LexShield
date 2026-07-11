"""LLM classifier tests (mocked HTTP, no live API calls)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lexshield.classifiers.llm import LLMClassifier
from lexshield.models import Caller, CallerType, ToolCallRequest, ToolRef
from lexshield.taxonomy import BUILTIN_INTENTS


def _request(**kwargs: object) -> ToolCallRequest:
    return ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name="send_email"),
        arguments=kwargs.get("arguments", {"body": "hello"}),
    )


def _mock_response(status_code: int = 200, *, json_payload: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    return httpx.Response(status_code, json=json_payload, request=request)


def _chat_response(content: dict) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(content),
                }
            }
        ]
    }


@pytest.fixture
def llm_classifier(monkeypatch: pytest.MonkeyPatch) -> LLMClassifier:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    return LLMClassifier(model="gpt-4o-mini", timeout_ms=2000, optional=True)


@pytest.mark.asyncio
async def test_returns_none_without_api_key_when_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    classifier = LLMClassifier(optional=True)
    result = await classifier.classify(_request())
    assert result is None


@pytest.mark.asyncio
async def test_raises_without_api_key_when_not_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    classifier = LLMClassifier(optional=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await classifier.classify(_request())


@pytest.mark.asyncio
async def test_classify_success(llm_classifier: LLMClassifier) -> None:
    mock_response = _mock_response(json_payload=_chat_response(
        {
            "intent": "comms.send.email",
            "confidence": 0.82,
            "alternatives": [{"intent": "comms.send.external", "confidence": 0.2}],
            "reasoning": "Email tool with recipient arguments",
        }
    ))
    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient.post", mock_post):
        result = await llm_classifier.classify(_request())

    assert result is not None
    assert result.intent == "comms.send.email"
    assert result.confidence == 0.82
    assert result.classifier == "llm:openai:gpt-4o-mini"
    assert result.alternatives[0].intent == "comms.send.external"
    assert result.reasoning == "Email tool with recipient arguments"

    mock_post.assert_awaited_once()
    call_kwargs = mock_post.await_args.kwargs
    assert call_kwargs["json"]["model"] == "gpt-4o-mini"
    assert call_kwargs["json"]["response_format"] == {"type": "json_object"}

    system_prompt = call_kwargs["json"]["messages"][0]["content"]
    for intent in BUILTIN_INTENTS:
        assert intent in system_prompt

    user_prompt = call_kwargs["json"]["messages"][1]["content"]
    assert "AKIAIOSFODNN7EXAMPLE" not in user_prompt


@pytest.mark.asyncio
async def test_redacts_secrets_in_prompt(llm_classifier: LLMClassifier) -> None:
    request = _request(
        arguments={"body": "key=AKIAIOSFODNN7EXAMPLE", "to": "user@example.com"}
    )
    mock_response = _mock_response(
        json_payload=_chat_response(
            {
                "intent": "security.secret_exposure",
                "confidence": 0.95,
                "alternatives": [],
                "reasoning": "AWS key detected",
            }
        ),
    )
    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient.post", mock_post):
        await llm_classifier.classify(request)

    user_prompt = mock_post.await_args.kwargs["json"]["messages"][1]["content"]
    assert "AKIAIOSFODNN7EXAMPLE" not in user_prompt
    assert "[REDACTED_AWS_KEY]" in user_prompt
    assert "user@example.com" not in user_prompt
    assert "[REDACTED_EMAIL]" in user_prompt


@pytest.mark.asyncio
async def test_returns_none_on_http_error(llm_classifier: LLMClassifier) -> None:
    mock_post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "error",
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
            response=httpx.Response(500),
        )
    )

    with patch("httpx.AsyncClient.post", mock_post):
        result = await llm_classifier.classify(_request())

    assert result is None


@pytest.mark.asyncio
async def test_returns_none_on_timeout(llm_classifier: LLMClassifier) -> None:
    mock_post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient.post", mock_post):
        result = await llm_classifier.classify(_request())

    assert result is None


@pytest.mark.asyncio
async def test_returns_none_on_invalid_json_content(
    llm_classifier: LLMClassifier,
) -> None:
    mock_response = _mock_response(
        json_payload={"choices": [{"message": {"content": "not-json"}}]},
    )
    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient.post", mock_post):
        result = await llm_classifier.classify(_request())

    assert result is None


@pytest.mark.asyncio
async def test_posts_to_configured_base_url(llm_classifier: LLMClassifier) -> None:
    mock_response = _mock_response(
        json_payload=_chat_response(
            {
                "intent": "unknown.unclassified",
                "confidence": 0.4,
                "alternatives": [],
                "reasoning": "unclear",
            }
        ),
    )
    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient.post", mock_post):
        await llm_classifier.classify(_request())

    url = str(mock_post.await_args.args[0])
    assert url == "https://api.example.com/v1/chat/completions"


def test_normalizes_provider_prefixed_model() -> None:
    classifier = LLMClassifier(model="openai:gpt-4o-mini")
    assert classifier.model == "gpt-4o-mini"
