"""Deterministic classifier reading rules.yaml shape (stub)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from lexshield.models import Classification, IntentAlternative, ToolCallRequest


class DeterministicClassifier:
    """Pattern and tool-map based classifier."""

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = Path(rules_path) if rules_path else None
        self.tool_map: dict[str, str] = {}
        self.patterns: list[dict[str, Any]] = []
        if self.rules_path and self.rules_path.exists():
            self._load_rules(self.rules_path)

    def _load_rules(self, path: Path) -> None:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        self.tool_map = data.get("tool_map", {})
        self.patterns = data.get("patterns", [])

    def classify(self, request: ToolCallRequest) -> Classification | None:
        """Classify a tool call using deterministic rules."""
        args_blob = " ".join(str(v) for v in request.arguments.values())

        for pattern in self.patterns:
            match_spec = pattern.get("match", {})
            regex = match_spec.get("any_arg_regex")
            if regex and re.search(regex, args_blob):
                return Classification(
                    intent=pattern["intent"],
                    confidence=float(pattern.get("confidence", 0.9)),
                    alternatives=[],
                    classifier="deterministic:v1",
                )
            for key, value in request.arguments.items():
                arg_regex = match_spec.get(f"arg_regex:{key}")
                if arg_regex and re.search(arg_regex, str(value)):
                    return Classification(
                        intent=pattern["intent"],
                        confidence=float(pattern.get("confidence", 0.9)),
                        alternatives=[],
                        classifier="deterministic:v1",
                    )

        tool_name = request.tool.name
        if tool_name in self.tool_map:
            return Classification(
                intent=self.tool_map[tool_name],
                confidence=0.7,
                alternatives=[],
                classifier="deterministic:v1",
            )

        return None
