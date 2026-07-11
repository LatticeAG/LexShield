"""FastAPI local API — SPEC §9 routes (stubbed)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from lexshield.challenges.store import ChallengeStore
from lexshield.models import ToolCallRequest, VerdictType
from lexshield.shield import Shield

_bearer = HTTPBearer(auto_error=False)


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
    app = FastAPI(title="LexShield", version="0.1.0")
    app.state.shield = shield
    app.state.challenge_store = ChallengeStore()
    app.state.policy_loaded = shield is not None

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, bool]:
        return {"ready": bool(app.state.policy_loaded)}

    @app.post(
        "/v1/shields/{shield_id}/evaluate",
        dependencies=[Depends(_require_token)],
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
        dependencies=[Depends(_require_token)],
    )
    async def execute(shield_id: str, body: ToolCallRequest) -> dict[str, Any]:
        active = _get_shield(app, shield_id)
        verdict = await active.evaluate(
            tool=body.tool.name,
            arguments=body.arguments,
            caller=body.caller,
            context=body.context,
            request_id=body.id,
        )
        if verdict.decision != VerdictType.ALLOW:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": _error_code(verdict.decision),
                    "verdict": verdict.decision.value,
                    "reason": verdict.reason,
                    "request_id": verdict.request_id,
                    "matched_rule_id": verdict.matched_rule_id,
                    "retryable": False,
                },
            )
        return {
            "verdict": verdict.model_dump(by_alias=True),
            "executed": False,
            "message": "Execute stub — upstream forwarding not implemented",
        }

    @app.get(
        "/v1/shields/{shield_id}/policy",
        dependencies=[Depends(_require_token)],
    )
    async def get_policy(shield_id: str) -> dict[str, Any]:
        active = _get_shield(app, shield_id)
        return active.policy.model_dump(by_alias=True)

    @app.post(
        "/v1/shields/{shield_id}/policy/reload",
        dependencies=[Depends(_require_token)],
    )
    async def reload_policy(shield_id: str) -> dict[str, str]:
        active = _get_shield(app, shield_id)
        try:
            from lexshield.policy.loader import load_policy

            active.policy = load_policy(active.policy_path)
            active.policy_engine.policy = active.policy
            return {"status": "reloaded"}
        except Exception as exc:
            return {"status": "failed", "message": str(exc)}

    @app.get("/v1/traces", dependencies=[Depends(_require_token)])
    async def list_traces(
        decision: str | None = None,
        tool: str | None = None,
        intent: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        active: Shield = app.state.shield
        if active is None or active.trace_sink is None:
            return {"traces": [], "total": 0}
        traces = active.trace_sink.read_all(limit=limit, offset=offset)
        filtered = []
        for trace in traces:
            verdict = trace.get("verdict", {})
            request = trace.get("request", {})
            if decision and verdict.get("decision") != decision:
                continue
            if tool and request.get("tool", {}).get("name") != tool:
                continue
            if intent:
                classifications = trace.get("classifications", [])
                if not any(c.get("intent") == intent for c in classifications):
                    continue
            filtered.append(trace)
        return {"traces": filtered, "total": len(filtered)}

    @app.get("/v1/challenges", dependencies=[Depends(_require_token)])
    async def list_challenges() -> dict[str, Any]:
        store: ChallengeStore = app.state.challenge_store
        return {"challenges": store.list_open()}

    @app.post(
        "/v1/challenges/{challenge_id}/resolve",
        dependencies=[Depends(_require_token)],
    )
    async def resolve_challenge(
        challenge_id: str,
        body: dict[str, str],
    ) -> dict[str, Any]:
        store: ChallengeStore = app.state.challenge_store
        decision = body.get("decision", "")
        actor = body.get("actor", "api")
        if decision not in ("approve", "deny"):
            raise HTTPException(status_code=400, detail="decision must be approve or deny")
        record = store.resolve(challenge_id, decision=decision, actor=actor)
        if record is None:
            raise HTTPException(status_code=404, detail="Challenge not found")
        return record

    return app


def _get_shield(app: FastAPI, shield_id: str) -> Shield:
    active: Shield | None = app.state.shield
    if active is None:
        raise HTTPException(status_code=503, detail="Shield not configured")
    if active.shield_id != shield_id:
        raise HTTPException(status_code=404, detail=f"Shield '{shield_id}' not found")
    return active


def _error_code(decision: VerdictType) -> str:
    mapping = {
        VerdictType.BLOCK: "lexshield_blocked",
        VerdictType.CHALLENGE: "lexshield_challenged",
        VerdictType.DEFER: "lexshield_deferred",
    }
    return mapping.get(decision, "lexshield_blocked")
