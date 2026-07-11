"""NDJSON, stdout, HTTP, and OTLP trace sinks."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

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


_DEFAULT_HTTP_TIMEOUT_MS = 2000


def _fire_and_forget_post(
    url: str,
    *,
    body: bytes,
    content_type: str,
    timeout_ms: int = _DEFAULT_HTTP_TIMEOUT_MS,
) -> None:
    """POST payload in a background thread; errors are swallowed."""
    try:
        with httpx.Client(timeout=timeout_ms / 1000) as client:
            client.post(
                url,
                content=body,
                headers={"Content-Type": content_type},
            )
    except httpx.HTTPError:
        pass


class HttpTraceSink:
    """POST NDJSON trace events to a remote HTTP endpoint (fire-and-forget)."""

    def __init__(self, url: str, *, timeout_ms: int = _DEFAULT_HTTP_TIMEOUT_MS) -> None:
        self.url = url
        self.timeout_ms = timeout_ms

    def write(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        threading.Thread(
            target=_fire_and_forget_post,
            args=(self.url,),
            kwargs={
                "body": line.encode("utf-8"),
                "content_type": "application/x-ndjson",
                "timeout_ms": self.timeout_ms,
            },
            daemon=True,
        ).start()

    def update_outcome(self, request_id: str, outcome: str) -> None:
        _ = (request_id, outcome)


def _otlp_ids(request_id: str) -> tuple[str, str]:
    trace_id = hashlib.sha256(request_id.encode()).hexdigest()[:32]
    span_id = hashlib.sha256(f"{request_id}:span".encode()).hexdigest()[:16]
    return trace_id, span_id


def _iso_to_unix_nano(iso_ts: str) -> int:
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except ValueError:
        return int(time.time() * 1_000_000_000)


def _otlp_string_attr(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "value": {"stringValue": value}}


def _otlp_number_attr(key: str, value: int | float) -> dict[str, Any]:
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    return {"key": key, "value": {"doubleValue": float(value)}}


def build_otlp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Build minimal OTLP/HTTP JSON export for span ``lexshield.evaluate``."""
    request = payload.get("request", {})
    verdict = payload.get("verdict", {})
    classifications = payload.get("classifications", [])

    request_id = payload.get("id") or request.get("id") or "unknown"
    trace_id, span_id = _otlp_ids(str(request_id))
    start_nano = _iso_to_unix_nano(str(payload.get("ts", "")))
    duration_ms = verdict.get("durationMs", 0)
    end_nano = start_nano + int(float(duration_ms) * 1_000_000)

    tool = request.get("tool", {}).get("name", "")
    intent = classifications[0].get("intent", "") if classifications else ""
    decision = verdict.get("decision", "")
    rule_id = verdict.get("matchedRuleId", "")

    attributes: list[dict[str, Any]] = [
        _otlp_string_attr("tool", tool),
        _otlp_string_attr("intent", intent),
        _otlp_string_attr("verdict", decision),
        _otlp_number_attr("duration_ms", duration_ms),
    ]
    if rule_id:
        attributes.append(_otlp_string_attr("rule_id", rule_id))

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _otlp_string_attr("service.name", "lexshield"),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "lexshield"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": "lexshield.evaluate",
                                "kind": 1,
                                "startTimeUnixNano": str(start_nano),
                                "endTimeUnixNano": str(end_nano),
                                "attributes": attributes,
                            }
                        ],
                    }
                ],
            }
        ]
    }


class OtlpTraceSink:
    """Export ``lexshield.evaluate`` spans via OTLP/HTTP JSON."""

    def __init__(self, url: str, *, timeout_ms: int = _DEFAULT_HTTP_TIMEOUT_MS) -> None:
        self.url = url
        self.timeout_ms = timeout_ms

    def write(self, payload: dict[str, Any]) -> None:
        otlp_payload = build_otlp_payload(payload)
        body = json.dumps(otlp_payload, separators=(",", ":")).encode("utf-8")
        threading.Thread(
            target=_fire_and_forget_post,
            args=(self.url,),
            kwargs={
                "body": body,
                "content_type": "application/json",
                "timeout_ms": self.timeout_ms,
            },
            daemon=True,
        ).start()

    def update_outcome(self, request_id: str, outcome: str) -> None:
        _ = (request_id, outcome)


class CompositeTraceSink:
    """Delegate trace writes to multiple sinks."""

    def __init__(self, sinks: list[TraceSink]) -> None:
        self.sinks = sinks

    def write(self, payload: dict[str, Any]) -> None:
        for sink in self.sinks:
            sink.write(payload)

    def update_outcome(self, request_id: str, outcome: str) -> None:
        for sink in self.sinks:
            sink.update_outcome(request_id, outcome)
