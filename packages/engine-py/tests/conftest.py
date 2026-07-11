"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_arguments_with_aws_key() -> dict[str, str]:
    return {
        "to": "user@example.com",
        "subject": "test",
        "body": "key=AKIAIOSFODNN7EXAMPLE",
    }


@pytest.fixture
def sample_arguments_with_bearer() -> dict[str, str]:
    return {"headers": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test"}
