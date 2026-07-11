"""LLM classifier stub (optional API key)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from lexshield.models import Classification, IntentAlternative, ToolCallRequest
from lexshield.redaction import redact_arguments


class LLMClassifier:
    """OpenAI-compatible LLM classifier (stub)."""

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key_env: str = "OPENAI_API_KEY",
        base_url_env: str = "OPENAI_BASE_URL",
        timeout_ms: int = 2000,
        optional: bool = True,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.timeout_ms = timeout_ms
        self.optional = optional

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)

    @property
    def base_url(self) -> str:
        return os.environ.get(self.base_url_env, "https://api.openai.com/v1")

    def is_available(self) -> bool:
        """Return True when the classifier can run."""
        return bool(self.api_key)

    async def classify(self, request: ToolCallRequest) -> Classification | None:
        """Classify via LLM (stub: returns None when unavailable)."""
        if not self.is_available():
            if self.optional:
                return None
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        redacted_args, _ = redact_arguments(request.arguments, redact_emails="redact")
        _ = redacted_args

        # Stub: no live LLM call in scaffold
        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as _client:
            return Classification(
                intent="unknown.unclassified",
                confidence=0.5,
                alternatives=[IntentAlternative(intent="unknown.unclassified", confidence=0.5)],
                classifier=f"llm:openai:{self.model}",
                reasoning="LLM classifier stub",
            )
