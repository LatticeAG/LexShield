"""Embedding classifier interface (post-MVP; SPEC §11.1 step 2)."""

from __future__ import annotations

from pathlib import Path

from lexshield.models import Classification, ToolCallRequest


class EmbeddingClassifier:
    """Local embedding/heuristic classifier — interface only in v0.1."""

    def __init__(
        self,
        *,
        model: str | None = None,
        model_path: str | Path | None = None,
        threshold: float = 0.85,
    ) -> None:
        self.model = model
        self.model_path = Path(model_path) if model_path is not None else None
        self.threshold = threshold

    def is_available(self) -> bool:
        """Return False until a local embedding model is configured."""
        return False

    def classify(self, request: ToolCallRequest) -> Classification | None:
        """Not implemented in v0.1 — reserved for post-MVP embedding path."""
        raise NotImplementedError(
            "EmbeddingClassifier is not implemented in v0.1; "
            "use DeterministicClassifier and optional LLMClassifier instead."
        )
