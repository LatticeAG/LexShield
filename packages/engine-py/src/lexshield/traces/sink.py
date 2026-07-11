"""NDJSON trace file sink (stub)."""

from __future__ import annotations

import json
from pathlib import Path

from lexshield.models import Trace


class NDJSONTraceSink:
    """Append-only NDJSON trace sink."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, trace: Trace) -> None:
        """Append one trace event as NDJSON (non-blocking stub)."""
        line = trace.model_dump_json(by_alias=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read_all(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        """Read trace events from the NDJSON file."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        selected = lines[offset : offset + limit]
        return [json.loads(line) for line in selected if line.strip()]
