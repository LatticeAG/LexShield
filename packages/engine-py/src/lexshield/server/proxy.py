"""Upstream HTTP forward for /execute when ALLOW."""

from __future__ import annotations

from typing import Any

import httpx

from lexshield.models import ToolCallRequest, UpstreamConfig


class UpstreamForwardError(Exception):
    """Raised when upstream forwarding fails after ALLOW."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def forward_upstream(
    request: ToolCallRequest,
    upstream: UpstreamConfig,
) -> dict[str, Any]:
    """POST tool call payload to configured upstream and return JSON body."""
    headers = dict(upstream.headers or {})
    headers["X-LexShield-Request-Id"] = request.id or ""
    headers["X-LexShield-Verdict"] = "ALLOW"

    timeout_s = (upstream.timeout_ms or 5000) / 1000
    payload = {
        "tool": request.tool.model_dump(by_alias=True),
        "arguments": request.arguments,
        "caller": request.caller.model_dump(by_alias=True),
        "context": request.context.model_dump(by_alias=True),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(upstream.url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamForwardError(
            f"Upstream returned HTTP {exc.response.status_code}",
            status_code=exc.response.status_code,
        ) from exc
    except httpx.HTTPError as exc:
        raise UpstreamForwardError(str(exc)) from exc

    try:
        body = response.json()
    except ValueError:
        return {"status": response.status_code, "body": response.text}
    if isinstance(body, dict):
        return body
    return {"result": body}
