"""LexShield SDK — Shield entry point (stub)."""

from __future__ import annotations

import contextvars
import functools
import inspect
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

import ulid
import yaml

from lexshield.challenges.store import ChallengeStore
from lexshield.classifiers.pipeline import ClassifierPipeline
from lexshield.errors import (
    LexShieldBlockedError,
    LexShieldChallengeError,
    LexShieldConfigError,
)
from lexshield.models import (
    Caller,
    CallContext,
    ToolCallRequest,
    ToolRef,
    Trace,
    Verdict,
    VerdictType,
)
from lexshield.policy.engine import PolicyEngine
from lexshield.policy.loader import load_policy
from lexshield.traces.sink import NDJSONTraceSink

F = TypeVar("F", bound=Callable[..., Any])

_session_conversation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "conversation_id", default=None
)
_session_environment: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "environment", default=None
)
_session_tags: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "tags", default=None
)


class ShieldSession:
    """Context manager for session-scoped contextvars."""

    def __init__(
        self,
        *,
        conversation_id: str | None = None,
        environment: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.environment = environment
        self.tags = tags
        self._tokens: list[contextvars.Token[Any]] = []

    def __enter__(self) -> ShieldSession:
        if self.conversation_id is not None:
            self._tokens.append(
                _session_conversation_id.set(self.conversation_id)
            )
        if self.environment is not None:
            self._tokens.append(_session_environment.set(self.environment))
        if self.tags is not None:
            self._tokens.append(_session_tags.set(self.tags))
        return self

    def __exit__(self, *_: object) -> None:
        for token in reversed(self._tokens):
            token.var.reset(token)


class Shield:
    """Bound LexShield instance: policy + classifiers + sinks."""

    def __init__(
        self,
        *,
        shield_id: str,
        name: str,
        policy_path: Path,
        rules_path: Path | None = None,
        trace_sink_path: Path | None = None,
    ) -> None:
        self.shield_id = shield_id
        self.name = name
        self.policy_path = policy_path
        self.compiled_policy = load_policy(policy_path)
        self.policy = self.compiled_policy.policy
        self.policy_engine = PolicyEngine(self.compiled_policy)
        self.classifier_pipeline = ClassifierPipeline(rules_path=rules_path)
        self.challenge_store = ChallengeStore()
        self.trace_sink = (
            NDJSONTraceSink(trace_sink_path) if trace_sink_path else None
        )

    @classmethod
    def from_config(cls, path: str | Path) -> Shield:
        """Load shield from lexshield.yaml."""
        config_path = Path(path)
        if not config_path.exists():
            raise LexShieldConfigError(f"Config file not found: {config_path}")

        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)

        if not isinstance(raw, dict) or "shield" not in raw:
            raise LexShieldConfigError("Config must contain a 'shield' section")

        shield_cfg = raw["shield"]
        base_dir = config_path.parent
        policy_path = base_dir / shield_cfg.get("policy", "./policy.yaml")
        rules_path = None
        for classifier in shield_cfg.get("classifiers", []):
            if classifier.get("type") == "deterministic":
                rules_path = base_dir / classifier.get("path", "./rules.yaml")
                break

        trace_sink_path = None
        for sink in shield_cfg.get("sinks", []):
            if sink.get("type") == "file":
                trace_sink_path = base_dir / sink.get("path", "./traces.ndjson")
                break

        return cls(
            shield_id=shield_cfg.get("id", "local"),
            name=shield_cfg.get("name", "local-shield"),
            policy_path=policy_path,
            rules_path=rules_path,
            trace_sink_path=trace_sink_path,
        )

    def session(
        self,
        *,
        conversation_id: str | None = None,
        environment: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> ShieldSession:
        """Return a context manager for nested session context."""
        return ShieldSession(
            conversation_id=conversation_id,
            environment=environment,
            tags=tags,
        )

    async def evaluate(
        self,
        *,
        tool: str,
        arguments: dict[str, Any] | None = None,
        caller: dict[str, Any] | Caller | None = None,
        context: dict[str, Any] | CallContext | None = None,
        request_id: str | None = None,
    ) -> Verdict:
        """Evaluate a tool call and return a verdict (does not execute the tool)."""
        start = time.perf_counter()
        rid = request_id or str(ulid.new())

        caller_model = (
            caller
            if isinstance(caller, Caller)
            else Caller.model_validate(caller or {"id": "anonymous", "type": "agent"})
        )

        ctx = context if isinstance(context, CallContext) else CallContext.model_validate(
            context or {}
        )
        if _session_conversation_id.get() and not ctx.conversation_id:
            ctx = ctx.model_copy(update={"conversationId": _session_conversation_id.get()})
        if _session_environment.get() and not ctx.environment:
            ctx = ctx.model_copy(update={"environment": _session_environment.get()})
        if _session_tags.get() and not ctx.tags:
            ctx = ctx.model_copy(update={"tags": _session_tags.get()})

        request = ToolCallRequest(
            id=rid,
            shieldId=self.shield_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            caller=caller_model,
            tool=ToolRef(name=tool),
            arguments=arguments or {},
            context=ctx,
        )

        classifications = await self.classifier_pipeline.classify(request)
        verdict = self.policy_engine.evaluate(request, classifications)
        verdict = verdict.model_copy(
            update={
                "requestId": rid,
                "durationMs": (time.perf_counter() - start) * 1000,
            }
        )
        if self.trace_sink is not None:
            self.trace_sink.write(
                Trace(
                    id=rid,
                    request=request,
                    verdict=verdict,
                )
            )
        return verdict

    def reload_policy(self) -> None:
        """Reload policy from disk and refresh the policy engine."""
        self.compiled_policy = load_policy(self.policy_path)
        self.policy = self.compiled_policy.policy
        self.policy_engine = PolicyEngine(self.compiled_policy)

    async def record_outcome(self, request_id: str, outcome: str) -> None:
        """Record execution outcome for a prior request (stub)."""
        _ = (request_id, outcome)

    def guard(
        self,
        tool: str | None = None,
        *,
        await_challenge: bool = False,
    ) -> Callable[[F], F]:
        """Decorator that evaluates policy before invoking the wrapped function."""

        def decorator(fn: F) -> F:
            tool_name = tool or fn.__name__

            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    verdict = await self.evaluate(
                        tool=tool_name,
                        arguments=kwargs or {},
                    )
                    self._raise_for_verdict(verdict, await_challenge=await_challenge)
                    return await fn(*args, **kwargs)

                return async_wrapper  # type: ignore[return-value]

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                raise LexShieldConfigError(
                    "Use shield.guard_sync for synchronous functions"
                )

            return sync_wrapper  # type: ignore[return-value]

        return decorator

    def guard_sync(
        self,
        tool: str | None = None,
        *,
        await_challenge: bool = False,
    ) -> Callable[[F], F]:
        """Synchronous guard decorator (stub raises for async-only evaluate)."""
        _ = (tool, await_challenge)

        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                raise LexShieldConfigError(
                    "guard_sync requires a running event loop; use async guard"
                )

            return wrapper  # type: ignore[return-value]

        return decorator

    def _raise_for_verdict(
        self,
        verdict: Verdict,
        *,
        await_challenge: bool = False,
    ) -> None:
        if verdict.decision == VerdictType.BLOCK:
            raise LexShieldBlockedError(
                verdict.reason,
                verdict=verdict,
                request_id=verdict.request_id,
            )
        if verdict.decision == VerdictType.CHALLENGE:
            if await_challenge:
                return
            raise LexShieldChallengeError(
                verdict.reason,
                verdict=verdict,
                request_id=verdict.request_id,
            )
