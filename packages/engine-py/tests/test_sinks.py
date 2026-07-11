"""Trace sink tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from lexshield.traces.sink import (
    CompositeTraceSink,
    HttpTraceSink,
    NDJSONTraceSink,
    OtlpTraceSink,
    StdoutTraceSink,
    build_otlp_payload,
    build_trace_payload,
)
from lexshield.models import Caller, CallerType, ToolCallRequest, ToolRef, Verdict, VerdictType
from lexshield.shield import Shield


def _sample_payload() -> dict:
    request = ToolCallRequest(
        id="req-1",
        shieldId="local",
        caller=Caller(id="agent-1", type=CallerType.AGENT),
        tool=ToolRef(name="send_email"),
        arguments={"body": "hello"},
    )
    verdict = Verdict(
        requestId="req-1",
        decision=VerdictType.BLOCK,
        matchedRuleId="block-exfil",
        reason="blocked",
        durationMs=12.5,
    )
    return build_trace_payload(
        trace_id="req-1",
        shield_id="local",
        timestamp="2026-07-11T12:00:00+00:00",
        request=request,
        classifications=[],
        verdict=verdict,
    )


class _CaptureHandler(BaseHTTPRequestHandler):
    received: list[bytes] = []
    content_type: str | None = None

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append(body)
        type(self).content_type = self.headers.get("Content-Type")
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)


def _run_http_server() -> tuple[HTTPServer, threading.Thread, str]:
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}/traces"


def test_build_otlp_payload_includes_span_attributes() -> None:
    payload = _sample_payload()
    otlp = build_otlp_payload(payload)

    spans = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert spans[0]["name"] == "lexshield.evaluate"

    attrs = {item["key"]: item["value"] for item in spans[0]["attributes"]}
    assert attrs["tool"]["stringValue"] == "send_email"
    assert attrs["verdict"]["stringValue"] == "BLOCK"
    assert attrs["rule_id"]["stringValue"] == "block-exfil"
    assert attrs["duration_ms"]["doubleValue"] == 12.5


def test_http_trace_sink_posts_ndjson() -> None:
    _CaptureHandler.received = []
    server, thread, url = _run_http_server()
    try:
        sink = HttpTraceSink(url, timeout_ms=2000)
        payload = _sample_payload()
        sink.write(payload)

        deadline = 2.0
        while not _CaptureHandler.received and deadline > 0:
            thread.join(timeout=0.05)
            deadline -= 0.05

        assert len(_CaptureHandler.received) == 1
        assert _CaptureHandler.content_type == "application/x-ndjson"
        posted = json.loads(_CaptureHandler.received[0].decode().strip())
        assert posted["id"] == "req-1"
        assert posted["verdict"]["decision"] == "BLOCK"
    finally:
        server.shutdown()
        thread.join(timeout=1)


def test_otlp_trace_sink_posts_json() -> None:
    _CaptureHandler.received = []
    server, thread, url = _run_http_server()
    try:
        sink = OtlpTraceSink(url, timeout_ms=2000)
        sink.write(_sample_payload())

        deadline = 2.0
        while not _CaptureHandler.received and deadline > 0:
            thread.join(timeout=0.05)
            deadline -= 0.05

        assert len(_CaptureHandler.received) == 1
        assert _CaptureHandler.content_type == "application/json"
        body = json.loads(_CaptureHandler.received[0].decode())
        span = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["name"] == "lexshield.evaluate"
    finally:
        server.shutdown()
        thread.join(timeout=1)


def test_composite_trace_sink_delegates(tmp_path: Path) -> None:
    file_sink = NDJSONTraceSink(tmp_path / "traces.ndjson")
    stdout_sink = StdoutTraceSink()
    composite = CompositeTraceSink([file_sink, stdout_sink])
    payload = _sample_payload()

    with patch("builtins.print") as print_mock:
        composite.write(payload)

    print_mock.assert_called_once()
    traces = file_sink.read_all()
    assert len(traces) == 1
    assert traces[0]["id"] == "req-1"


def test_shield_from_config_loads_http_and_otlp_sinks(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.dump(
            {
                "id": "test-policy",
                "name": "Test",
                "version": "1",
                "defaultVerdict": "BLOCK",
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.dump({"tool_map": {}, "patterns": []}), encoding="utf-8")

    config_path = tmp_path / "lexshield.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "shield": {
                    "id": "local",
                    "name": "local-shield",
                    "policy": "./policy.yaml",
                    "classifiers": [
                        {"type": "deterministic", "path": "./rules.yaml"},
                    ],
                    "sinks": [
                        {"type": "http", "url": "http://127.0.0.1:9998/traces"},
                        {"type": "otlp", "url": "http://127.0.0.1:4318/v1/traces"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    shield = Shield.from_config(config_path)
    sink_types = {type(sink) for sink in shield.trace_sinks}
    assert HttpTraceSink in sink_types
    assert OtlpTraceSink in sink_types
