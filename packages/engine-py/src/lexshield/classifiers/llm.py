"""OpenAI-compatible LLM classifier."""

from __future__ import annotations

import json
import os
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
            return None

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

        if not isinstance(content, str):
            return None

        return self._parse_response(content)


def _normalize_model(model: str) -> str:
    """Strip provider prefix from config values like openai:gpt-4o-mini."""
    if ":" in model:
        return model.split(":", 1)[1]
    return model
