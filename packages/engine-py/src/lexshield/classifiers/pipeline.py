"""Classifier pipeline: deterministic then LLM."""

from __future__ import annotations

from pathlib import Path

from lexshield.classifiers.deterministic import DeterministicClassifier
from lexshield.classifiers.llm import LLMClassifier
from lexshield.models import Classification, ToolCallRequest

DETERMINISTIC_SKIP_LLM_THRESHOLD = 0.90
UNKNOWN_INTENT = "unknown.unclassified"


class ClassifierPipeline:
    """Runs deterministic classifier first, then LLM if needed."""

    def __init__(
        self,
        *,
        rules_path: str | Path | None = None,
        llm: LLMClassifier | None = None,
    ) -> None:
        self.deterministic = DeterministicClassifier(rules_path)
        self.llm = llm or LLMClassifier()

    async def classify(self, request: ToolCallRequest) -> list[Classification]:
        """Return ordered classifications from the pipeline."""
        results: list[Classification] = []

        det = self.deterministic.classify(request)
        if det is not None:
            results.append(det)
            if det.confidence >= DETERMINISTIC_SKIP_LLM_THRESHOLD:
                return results

        if self.llm.is_available():
            llm_result = await self.llm.classify(request)
            if llm_result is not None:
                results.append(llm_result)

        if not results:
            results.append(
                Classification(
                    intent=UNKNOWN_INTENT,
                    confidence=0.3,
                    alternatives=[],
                    classifier="deterministic:v1",
                    reasoning="No deterministic or LLM classification",
                )
            )

        return results
