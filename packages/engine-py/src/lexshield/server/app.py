"""FastAPI local API — SPEC §9 routes."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from lexshield.models import ToolCallRequest, VerdictType
from lexshield.server.middleware import RequestIdMiddleware
from lexshield.server.proxy import UpstreamForwardError
from lexshield.shield import Shield

_bearer = HTTPBearer(auto_error=False)

_CONFIG_DOC = (
    "Start the server with `lexshield run -c <path>` (or `--config`) pointing at "
    "`lexshield.yaml` or a directory containing it."
)

_OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "shields", "description": "Evaluate and execute tool calls through a shield."},
    {"name": "policy", "description": "Inspect and hot-reload shield policy."},
    {"name": "traces", "description": "Query NDJSON audit traces written by the shield."},
    {"name": "challenges", "description": "Human-in-the-loop challenge queue."},
]


def _require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    token = os.environ.get("LEXSHIELD_LOCAL_TOKEN")
    if not token:
        return
    if credentials is None or credentials.credentials != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def create_app(shield: Shield | None = None) -> FastAPI:
    """Create the LexShield FastAPI application."""
    app = FastAPI(
        title="LexShield",
        version="0.1.0",
        description=(
            "Local policy firewall API for agent tool calls. "
            f"{_CONFIG_DOC}"
        ),
        openapi_tags=_OPENAPI_TAGS,
    )
    app.add_middleware(RequestIdMiddleware)
    app.state.shield = shield
    app.state.policy_loaded = shield is not None

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        """Liveness probe — process is running."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz() -> dict[str, bool]:
        """Readiness probe — shield and policy are loaded."""
        return {"ready": bool(app.state.policy_loaded)}

    @app.post(
        "/v1/shields/{shield_id}/evaluate",
        tags=["shields"],
        dependencies=[Depends(_require_token)],
        summary="Evaluate a tool call",
        description=(
            "Return a policy verdict without executing the tool. "
            f"{_CONFIG_DOC}"
        ),
    )
    async def evaluate(shield_id: str, body: ToolCallRequest) -> dict[str, Any]:
        active = _get_shield(app, shield_id)
        body = body.model_copy(update={"shieldId": shield_id})
        verdict = await active.evaluate(
            tool=body.tool.name,
            arguments=body.arguments,
            caller=body.caller,
            context=body.context,
            request_id=body.id,
        )
        return verdict.model_dump(by_alias=True)

    @app.post(
        "/v1/shields/{shield_id}/execute",
        tags=["shields"],
        dependencies=[Depends(_require_token)],
        summary="Evaluate and forward to upstream",
        description=(
            "Evaluate the tool call; when the verdict is ALLOW and an upstream is "
            "configured under `shield.proxy.upstreams`, forward the request and "
            "return the upstream JSON body. Records outcome EXECUTED on success. "
            f"{_CONFIG_DOC}"
        ),
    )
    async def execute(shield_id: str, body: ToolCallRequest) -> dict[str, Any]:
        active = _get_shield(app, shield_id)
        try:
            verdict, result = await active.execute_upstream(
                tool=body.tool.name,
                arguments=body.arguments,
                caller=body.caller,
                context=body.context,
                request_id=body.id,
            )
        except UpstreamForwardError as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "lexshield_upstream_error", "message": exc.message},
            ) from exc

        if verdict.decision != VerdictType.ALLOW:
            raise HTTPException(
                status_code=403,
                detail=_denied_detail(verdict),
            )
        return {
            "verdict": verdict.model_dump(by_alias=True),
            "result": result,
        }

    @app.get(
        "/v1/shields/{shield_id}/policy",
        tags=["policy"],
        dependencies=[Depends(_require_token)],
        summary="Get compiled policy",
        description=f"Return the active compiled policy JSON. {_CONFIG_DOC}",
    )
    async def get_policy(shield_id: str) -> dict[str, Any]:
        active = _get_shield(app, shield_id)
        return active.policy.model_dump(by_alias=True)

    @app.post(
        "/v1/shields/{shield_id}/policy/reload",
        tags=["policy"],
        dependencies=[Depends(_require_token)],
        summary="Hot-reload policy from disk",
        description=(
            "Reload policy from the path configured at server start. On failure the "
            "previous policy remains active. "
            f"{_CONFIG_DOC}"
        ),
    )
    async def reload_policy(shield_id: str) -> dict[str, str]:
        active = _get_shield(app, shield_id)
        try:
            active.reload_policy()
        except Exception as exc:
            return {"status": "failed", "message": str(exc)}
        return {"status": "reloaded"}

    @app.get(
        "/v1/traces",
        tags=["traces"],
        dependencies=[Depends(_require_token)],
        summary="List audit traces",
        description=(
            "Filter NDJSON traces by decision, tool, or intent. "
            f"{_CONFIG_DOC}"
        ),
    )
    async def list_traces(
        decision: str | None = None,
        tool: str | None = None,
        intent: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        active: Shield | None = app.state.shield
        if active is None or active.trace_sink is None:
            return {"traces": [], "total": 0}
        traces, total = active.trace_sink.read_filtered(
            decision=decision,
            tool=tool,
            intent=intent,
            limit=limit,
            offset=offset,
        )
        return {"traces": traces, "total": total}

    @app.get(
        "/v1/challenges",
        tags=["challenges"],
        dependencies=[Depends(_require_token)],
        summary="List open challenges",
        description=f"Return pending human-in-the-loop challenges. {_CONFIG_DOC}",
    )
    async def list_challenges() -> dict[str, Any]:
        active = _get_shield_or_none(app)
        if active is None:
            return {"challenges": []}
        return {"challenges": active.challenge_store.list_open()}

    @app.post(
        "/v1/challenges/{challenge_id}/resolve",
        tags=["challenges"],
        dependencies=[Depends(_require_token)],
        summary="Resolve a challenge",
        description=(
            "Approve or deny a pending challenge. Body: "
            '`{"decision": "approve"|"deny", "actor": "..."}`. '
            f"{_CONFIG_DOC}"
        ),
    )
    async def resolve_challenge(
        challenge_id: str,
        body: dict[str, str],
    ) -> dict[str, Any]:
        active = _get_shield_for_challenges(app)
        decision = body.get("decision", "")
        actor = body.get("actor", "api")
        if decision not in ("approve", "deny"):
            raise HTTPException(status_code=400, detail="decision must be approve or deny")
        record = active.challenge_store.resolve(
            challenge_id, decision=decision, actor=actor
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Challenge not found")
        return record

    return app


def configure_app(shield: Shield) -> FastAPI:
    """Wire a Shield into the module-level app instance."""
    app.state.shield = shield
    app.state.policy_loaded = True
    return app


def _get_shield_or_none(app: FastAPI) -> Shield | None:
    shield: Shield | None = app.state.shield
    return shield


def _get_shield_for_challenges(app: FastAPI) -> Shield:
    active: Shield | None = app.state.shield
    if active is None:
        raise HTTPException(status_code=503, detail="Shield not configured")
    return active


def _get_shield(app: FastAPI, shield_id: str) -> Shield:
    active: Shield | None = app.state.shield
    if active is None:
        raise HTTPException(status_code=503, detail="Shield not configured")
    if active.shield_id != shield_id:
        raise HTTPException(status_code=404, detail=f"Shield '{shield_id}' not found")
    return active


def _denied_detail(verdict: Any) -> dict[str, Any]:
    return {
        "error": _error_code(verdict.decision),
        "verdict": verdict.decision.value,
        "reason": verdict.reason,
        "request_id": verdict.request_id,
        "matched_rule_id": verdict.matched_rule_id,
        "retryable": False,
    }


def _error_code(decision: VerdictType) -> str:
    mapping = {
        VerdictType.BLOCK: "lexshield_blocked",
        VerdictType.CHALLENGE: "lexshield_challenged",
        VerdictType.DEFER: "lexshield_deferred",
    }
    return mapping.get(decision, "lexshield_blocked")


app = create_app(None)
