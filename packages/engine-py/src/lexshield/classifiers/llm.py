"""OpenAI-compatible LLM classifier."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from lexshield.models import Classification, IntentAlternative, ToolCallRequest
from lexshield.redaction import redact_arguments
from lexshield.taxonomy import BUILTIN_INTENTS

_SYSTEM_PROMPT_TEMPLATE = """You classify agent tool calls into intents for a policy firewall.

Allowed intents (use exactly one as primary):
{intents}

Safety rules:
- Prefer unknown.unclassified over guessing a dangerous intent as benign.
- Base classification on tool name, arguments, and caller context.
- Return JSON only with keys: intent, confidence, alternatives, reasoning.
- confidence must be between 0 and 1.
- alternatives is a list of {{intent, confidence}} objects."""


class CircuitBreaker:
    """Skip calls after repeated failures within a sliding window."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        open_seconds: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.open_seconds = open_seconds
        self._failure_times: list[float] = []
        self._open_until: float = 0.0
        self.circuit_open_count: int = 0

    def is_open(self) -> bool:
        return time.monotonic() < self._open_until

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failure_times = [
            ts for ts in self._failure_times if now - ts <= self.window_seconds
        ]
        self._failure_times.append(now)
        if len(self._failure_times) >= self.failure_threshold:
            self._open_until = now + self.open_seconds
            self.circuit_open_count += 1
            self._failure_times.clear()

    def record_success(self) -> None:
        self._failure_times.clear()
        self._open_until = 0.0


class LLMClassifier:
    """OpenAI-compatible LLM classifier."""

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key_env: str = "OPENAI_API_KEY",
        base_url_env: str = "OPENAI_BASE_URL",
        timeout_ms: int = 2000,
        optional: bool = True,
        redact: bool = True,
    ) -> None:
        self.model = _normalize_model(model)
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.timeout_ms = timeout_ms
        self.optional = optional
        self.redact = redact
        self.circuit_breaker = CircuitBreaker()

    @property
    def circuit_open_count(self) -> int:
        return self.circuit_breaker.circuit_open_count

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)

    @property
    def base_url(self) -> str:
        return os.environ.get(self.base_url_env, "https://api.openai.com/v1").rstrip("/")

    def is_available(self) -> bool:
        """Return True when the classifier can run."""
        return bool(self.api_key)

    def _system_prompt(self) -> str:
        intents = "\n".join(f"- {intent}" for intent in sorted(BUILTIN_INTENTS))
        return _SYSTEM_PROMPT_TEMPLATE.format(intents=intents)

    def _build_user_prompt(self, request: ToolCallRequest) -> str:
        arguments = request.arguments
        if self.redact:
            arguments, _ = redact_arguments(request.arguments, redact_emails="redact")

        payload: dict[str, Any] = {
            "tool": request.tool.name,
            "arguments": arguments,
            "caller": {
                "id": request.caller.id,
                "type": request.caller.type.value,
            },
        }
        if request.caller.roles:
            payload["caller"]["roles"] = request.caller.roles
        if request.context.environment:
            payload["environment"] = request.context.environment
        if request.context.tags:
            payload["tags"] = request.context.tags

        return json.dumps(payload, sort_keys=True)

    def _parse_response(self, content: str) -> Classification | None:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None

        intent = data.get("intent")
        confidence = data.get("confidence")
        if not isinstance(intent, str) or not isinstance(confidence, (int, float)):
            return None

        alternatives: list[IntentAlternative] = []
        for item in data.get("alternatives") or []:
            if not isinstance(item, dict):
                continue
            alt_intent = item.get("intent")
            alt_confidence = item.get("confidence")
            if isinstance(alt_intent, str) and isinstance(alt_confidence, (int, float)):
                alternatives.append(
                    IntentAlternative(intent=alt_intent, confidence=float(alt_confidence))
                )

        reasoning = data.get("reasoning")
        return Classification(
            intent=intent,
            confidence=float(confidence),
            alternatives=alternatives,
            classifier=f"llm:openai:{self.model}",
            reasoning=reasoning if isinstance(reasoning, str) else None,
        )

    async def classify(self, request: ToolCallRequest) -> Classification | None:
        """Classify via OpenAI-compatible chat completions API."""
        if not self.is_available():
            if self.optional:
                return None
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        if self.circuit_breaker.is_open():
            return None

        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._build_user_prompt(request)},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError):
            self.circuit_breaker.record_failure()
            return None

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            self.circuit_breaker.record_failure()
            return None

        if not isinstance(content, str):
            self.circuit_breaker.record_failure()
            return None

        parsed = self._parse_response(content)
        if parsed is None:
            self.circuit_breaker.record_failure()
            return None

        self.circuit_breaker.record_success()
        return parsed


def _normalize_model(model: str) -> str:
    """Strip provider prefix from config values like openai:gpt-4o-mini."""
    if ":" in model:
        return model.split(":", 1)[1]
    return model
