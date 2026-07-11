"""Classifier pipeline: deterministic then LLM with severity merge."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from lexshield.classifiers.deterministic import DeterministicClassifier
from lexshield.classifiers.llm import LLMClassifier
from lexshield.models import Classification, ToolCallRequest
from lexshield.taxonomy import intent_severity

DETERMINISTIC_SKIP_LLM_THRESHOLD = 0.90
UNKNOWN_INTENT = "unknown.unclassified"
UNKNOWN_CONFIDENCE = 0.30
FINGERPRINT_CACHE_TTL_SECONDS = 60.0


class _FingerprintCache:
    """In-memory TTL cache for deterministic-only classification results."""

    def __init__(self, ttl_seconds: float = FINGERPRINT_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, list[Classification]]] = {}

    def get(self, key: str) -> list[Classification] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return [item.model_copy(deep=True) for item in value]

    def set(self, key: str, value: list[Classification]) -> None:
        self._entries[key] = (
            time.monotonic() + self._ttl_seconds,
            [item.model_copy(deep=True) for item in value],
        )


def _fingerprint(request: ToolCallRequest) -> str:
    payload = {
        "tool": request.tool.name,
        "arguments": request.arguments,
    }
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _cache_enabled(request: ToolCallRequest) -> bool:
    if request.context.messages:
        return False
    if request.context.prior_calls:
        return False
    return True


def _is_deterministic_only(results: list[Classification]) -> bool:
    return bool(results) and all(
        classification.classifier.startswith("deterministic") for classification in results
    )


def merge_classifications(classifications: list[Classification]) -> list[Classification]:
    """Reorder classifications so the primary (highest severity) intent is first."""
    if len(classifications) <= 1:
        return classifications

    def sort_key(classification: Classification) -> tuple[int, float, int]:
        severity = intent_severity(classification.intent)
        is_deterministic = 1 if classification.classifier.startswith("deterministic") else 0
        return (severity, classification.confidence, is_deterministic)

    return sorted(classifications, key=sort_key, reverse=True)


class ClassifierPipeline:
    """Runs deterministic classifier first, then LLM if needed."""

    def __init__(
        self,
        *,
        rules_path: str | Path | None = None,
        llm: LLMClassifier | None = None,
    ) -> None:
        self.deterministic = DeterministicClassifier(rules_path)
        self.llm = llm
        self._cache = _FingerprintCache()
        self.last_classifier_error = False

    async def classify(self, request: ToolCallRequest) -> list[Classification]:
        """Return ordered classifications from the pipeline."""
        self.last_classifier_error = False
        if _cache_enabled(request):
            cached = self._cache.get(_fingerprint(request))
            if cached is not None:
                return cached

        results: list[Classification] = []
        llm_invoked = False
        llm_failed = False

        det = self.deterministic.classify(request)
        if det is not None:
            results.append(det)
            if det.confidence >= DETERMINISTIC_SKIP_LLM_THRESHOLD:
                merged = merge_classifications(results)
                if _cache_enabled(request) and _is_deterministic_only(merged):
                    self._cache.set(_fingerprint(request), merged)
                return merged

        if self.llm is not None and self.llm.is_available():
            if self.llm.circuit_breaker.is_open():
                llm_failed = True
            else:
                llm_invoked = True
                llm_result = await self.llm.classify(request)
                if llm_result is not None:
                    results.append(llm_result)
                else:
                    llm_failed = True

        if not results:
            if det is None and (self.llm is None or not self.llm.is_available() or llm_failed):
                self.last_classifier_error = True
            results.append(
                Classification(
                    intent=UNKNOWN_INTENT,
                    confidence=UNKNOWN_CONFIDENCE,
                    alternatives=[],
                    classifier="deterministic:v1",
                    reasoning="No deterministic or LLM classification",
                )
            )

        merged = merge_classifications(results)

        if (
            _cache_enabled(request)
            and _is_deterministic_only(merged)
            and not llm_invoked
        ):
            self._cache.set(_fingerprint(request), merged)

        return merged
