"""NDJSON and stdout trace sinks."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from lexshield.models import Classification, OutcomeType, ToolCallRequest, Trace, Verdict, VerdictType
from lexshield.redaction import redact_arguments


def _outcome_for_verdict(decision: VerdictType) -> OutcomeType:
    mapping = {
        VerdictType.ALLOW: OutcomeType.EXECUTED,
        VerdictType.BLOCK: OutcomeType.BLOCKED,
        VerdictType.CHALLENGE: OutcomeType.CHALLENGED,
        VerdictType.DEFER: OutcomeType.DEFERRED,
    }
    return mapping[decision]


def build_trace_payload(
    *,
    trace_id: str,
    shield_id: str,
    timestamp: str,
    request: ToolCallRequest,
    classifications: list[Classification],
    verdict: Verdict,
    outcome: OutcomeType | None = None,
    redact_emails: str = "hash",
) -> dict[str, Any]:
    """Build NDJSON trace event per SPEC Appendix C."""
    redacted_args, redactions = redact_arguments(
        request.arguments,
        redact_emails=redact_emails,
    )
    resolved_outcome = outcome or _outcome_for_verdict(verdict.decision)

    verdict_payload: dict[str, Any] = {
        "decision": verdict.decision.value,
        "reason": verdict.reason,
        "durationMs": verdict.duration_ms,
    }
    if verdict.matched_rule_id is not None:
        verdict_payload["matchedRuleId"] = verdict.matched_rule_id
    if verdict.policy_version is not None:
        verdict_payload["policyVersion"] = verdict.policy_version
    if verdict.challenge_id is not None:
        verdict_payload["challengeId"] = verdict.challenge_id

    payload: dict[str, Any] = {
        "id": trace_id,
        "ts": timestamp,
        "shieldId": shield_id,
        "request": {
            "id": request.id,
            "caller": request.caller.model_dump(by_alias=True, exclude_none=True),
            "tool": request.tool.model_dump(by_alias=True, exclude_none=True),
            "arguments_redacted": redacted_args,
            "context": request.context.model_dump(by_alias=True, exclude_none=True),
        },
        "classifications": [
            c.model_dump(by_alias=True, exclude_none=True) for c in classifications
        ],
        "verdict": verdict_payload,
        "outcome": resolved_outcome.value,
    }
    if redactions:
        payload["redactions"] = sorted(set(redactions))
    return payload


class TraceSink(Protocol):
    """Protocol for trace output sinks."""

    def write(self, payload: dict[str, Any]) -> None: ...

    def update_outcome(self, request_id: str, outcome: str) -> None: ...


class NDJSONTraceSink:
    """Append-only NDJSON trace sink."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict[str, Any]) -> None:
        """Append one trace event as NDJSON."""
        line = json.dumps(payload, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def write_trace(self, trace: Trace) -> None:
        """Append a Trace model (legacy compatibility)."""
        self.write(trace.model_dump(by_alias=True, exclude_none=True))

    def update_outcome(self, request_id: str, outcome: str) -> None:
        """Patch outcome field for the matching request id."""
        if not self.path.exists():
            return

        lines = self.path.read_text(encoding="utf-8").splitlines()
        outcome_at = datetime.now(timezone.utc).isoformat()
        updated_lines: list[str] = []
        changed = False

        for line in lines:
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = record.get("id") or record.get("request", {}).get("id")
            if record_id == request_id:
                record["outcome"] = outcome
                record["outcomeAt"] = outcome_at
                changed = True
            updated_lines.append(json.dumps(record, separators=(",", ":")))

        if changed:
            content = "\n".join(updated_lines)
            if content:
                content += "\n"
            self.path.write_text(content, encoding="utf-8")

    def read_all(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        """Read trace events from the NDJSON file."""
        traces, _ = self.read_filtered(limit=limit, offset=offset)
        return traces

    def read_all(self) -> list[dict[str, Any]]:
        """Read all trace events from the NDJSON file."""
        if not self.path.exists():
            return []
        traces: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                traces.append(json.loads(line))
        return traces

    def read_filtered(
        self,
        *,
        decision: str | None = None,
        tool: str | None = None,
        intent: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Read traces with optional filters, then apply limit/offset."""
        if not self.path.exists():
            return [], 0
        filtered: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            trace = json.loads(line)
            verdict = trace.get("verdict", {})
            request = trace.get("request", {})
            if decision and verdict.get("decision") != decision:
                continue
            if tool and request.get("tool", {}).get("name") != tool:
                continue
            if intent:
                classifications = trace.get("classifications", [])
                if not classifications:
                    classifications = verdict.get("classifications", [])
                if not any(c.get("intent") == intent for c in classifications):
                    continue
            filtered.append(trace)
        total = len(filtered)
        return filtered[offset : offset + limit], total

    def read_all(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        """Read trace events from the NDJSON file."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        selected = lines[offset : offset + limit]
        return [json.loads(line) for line in selected if line.strip()]


class StdoutTraceSink:
    """Print one-line trace summaries to stdout."""

    def write(self, payload: dict[str, Any]) -> None:
        verdict = payload.get("verdict", {})
        request = payload.get("request", {})
        tool = request.get("tool", {}).get("name", "?")
        decision = verdict.get("decision", "?")
        rule_id = verdict.get("matchedRuleId", "-")
        intent = ""
        classifications = payload.get("classifications", [])
        if classifications:
            intent = classifications[0].get("intent", "")
        summary = f"[LexShield] {decision} {tool}"
        if intent:
            summary += f" {intent}"
        summary += f" rule={rule_id}"
        print(summary, file=sys.stdout, flush=True)

    def update_outcome(self, request_id: str, outcome: str) -> None:
        _ = (request_id, outcome)
