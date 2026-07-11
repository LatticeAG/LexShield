"""Tests for EmbeddingClassifier post-MVP interface stub."""

from __future__ import annotations

import pytest

from lexshield.classifiers.embedding import EmbeddingClassifier
from lexshield.models import Caller, CallerType, ToolCallRequest, ToolRef


def _request() -> ToolCallRequest:
    return ToolCallRequest(
        id="01JTEST",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name="send_email"),
        arguments={"to": "a@b.com"},
    )


def test_embedding_classifier_not_available() -> None:
    classifier = EmbeddingClassifier()
    assert classifier.is_available() is False


def test_embedding_classifier_raises_not_implemented() -> None:
    classifier = EmbeddingClassifier()
    with pytest.raises(NotImplementedError, match="not implemented in v0.1"):
        classifier.classify(_request())
