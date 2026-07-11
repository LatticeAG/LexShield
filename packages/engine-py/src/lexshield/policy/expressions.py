"""Safe expression parser (stub)."""

from __future__ import annotations

from typing import Any


class ExpressionError(ValueError):
    """Raised when an expression cannot be parsed or evaluated."""


class Expression:
    """Compiled policy expression (stub)."""

    def __init__(self, source: str) -> None:
        self.source = source

    @classmethod
    def parse(cls, source: str) -> Expression:
        """Parse an expression string into a compiled form."""
        if not source or not source.strip():
            raise ExpressionError("Expression must not be empty")
        return cls(source.strip())

    def evaluate(self, bindings: dict[str, Any]) -> bool:
        """Evaluate expression against bound variables (stub: always False)."""
        _ = bindings
        return False
