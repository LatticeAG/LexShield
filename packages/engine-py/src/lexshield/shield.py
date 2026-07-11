"""LexShield SDK — Shield entry point."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

import ulid
import yaml

from lexshield.challenges.notifier import notify_challenge_created
from lexshield.challenges.store import ChallengeStore
from lexshield.classifiers.llm import LLMClassifier
from lexshield.classifiers.pipeline import ClassifierPipeline
from lexshield.errors import (
    LexShieldBlockedError,
    LexShieldChallengeError,
    LexShieldConfigError,
    redact_verdict_for_agent,
)
from lexshield.models import (
    Caller,
    CallContext,
    OutcomeType,
    ToolCallRequest,
    ToolRef,
    UpstreamConfig,
    Verdict,
    VerdictType,
)
from lexshield.policy.engine import PolicyEngine
from lexshield.policy.loader import load_policy
from lexshield.redaction import redact_arguments
from lexshield.server.proxy import forward_upstream
from lexshield.traces.sink import (
    HttpTraceSink,
    NDJSONTraceSink,
    OtlpTraceSink,
    StdoutTraceSink,
    TraceSink,
    build_trace_payload,
)

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

_CHALLENGE_POLL_INTERVAL_SECONDS = 0.05


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
        llm: LLMClassifier | None = None,
        trace_sink_path: Path | None = None,
        trace_sinks: list[TraceSink] | None = None,
        challenge_store_path: Path | None = None,
        challenge_webhook_url: str | None = None,
        proxy_upstreams: dict[str, UpstreamConfig] | None = None,
        fail_on_classifier_error: VerdictType = VerdictType.BLOCK,
        redact_emails: str = "hash",
        expose_rule_ids: bool = True,
    ) -> None:
        self.shield_id = shield_id
        self.name = name
        self.policy_path = policy_path
        self.compiled_policy = load_policy(policy_path)
        self.policy = self.compiled_policy.policy
        self.policy_engine = PolicyEngine(self.compiled_policy)
        self.classifier_pipeline = ClassifierPipeline(
            rules_path=rules_path,
            llm=llm,
        )
        self.challenge_store = ChallengeStore(
            challenge_store_path or ".lexshield/challenges"
        )
        self.challenge_webhook_url = challenge_webhook_url
        self.fail_on_classifier_error = fail_on_classifier_error
        self.redact_emails = redact_emails
        self.expose_rule_ids = expose_rule_ids
        self.proxy_upstreams = proxy_upstreams or {}

        if trace_sinks is not None:
            self.trace_sinks: list[TraceSink] = trace_sinks
        elif trace_sink_path is not None:
            self.trace_sinks = [NDJSONTraceSink(trace_sink_path)]
        else:
            self.trace_sinks = []

        self.trace_sink = next(
            (sink for sink in self.trace_sinks if isinstance(sink, NDJSONTraceSink)),
            self.trace_sinks[0] if self.trace_sinks else None,
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
        llm_classifier: LLMClassifier | None = None
        for classifier in shield_cfg.get("classifiers", []):
            classifier_type = classifier.get("type")
            if classifier_type == "deterministic":
                rules_path = base_dir / classifier.get("path", "./rules.yaml")
            elif classifier_type == "llm":
                llm_classifier = LLMClassifier(
                    model=classifier.get("model", "openai:gpt-4o-mini"),
                    api_key_env=classifier.get("api_key_env", "OPENAI_API_KEY"),
                    base_url_env=classifier.get("base_url_env", "OPENAI_BASE_URL"),
                    timeout_ms=classifier.get("timeout_ms", 2000),
                    optional=classifier.get("optional", True),
                    redact=classifier.get("redact", True),
                )

        trace_sinks: list[TraceSink] = []
        for sink in shield_cfg.get("sinks", []):
            sink_type = sink.get("type")
            if sink_type == "file":
                trace_sinks.append(
                    NDJSONTraceSink(base_dir / sink.get("path", "./traces.ndjson"))
                )
            elif sink_type == "stdout":
                trace_sinks.append(StdoutTraceSink())
            elif sink_type == "http":
                url = sink.get("url")
                if url:
                    trace_sinks.append(
                        HttpTraceSink(
                            url,
                            timeout_ms=sink.get("timeout_ms", 2000),
                        )
                    )
            elif sink_type == "otlp":
                url = sink.get("url")
                if url:
                    trace_sinks.append(
                        OtlpTraceSink(
                            url,
                            timeout_ms=sink.get("timeout_ms", 2000),
                        )
                    )

        trace_sink_path = None
        for sink in shield_cfg.get("sinks", []):
            if sink.get("type") == "file":
                trace_sink_path = base_dir / sink.get("path", "./traces.ndjson")
                break

        challenges_cfg = shield_cfg.get("challenges", {})
        challenge_store_path = base_dir / challenges_cfg.get(
            "path", ".lexshield/challenges"
        )
        challenge_webhook_url = challenges_cfg.get("webhook") or challenges_cfg.get(
            "webhook_url"
        )

        proxy_upstreams: dict[str, UpstreamConfig] = {}
        proxy_cfg = shield_cfg.get("proxy", {})
        if proxy_cfg.get("enabled"):
            for tool, upstream in proxy_cfg.get("upstreams", {}).items():
                proxy_upstreams[tool] = UpstreamConfig.model_validate(upstream)

        fail_raw = shield_cfg.get("fail_on_classifier_error", "BLOCK")
        fail_on_classifier_error = VerdictType(fail_raw)
        redact_emails = shield_cfg.get("redact", {}).get("emails", "hash")
        expose_rule_ids = shield_cfg.get("expose_rule_ids", True)

        return cls(
            shield_id=shield_cfg.get("id", "local"),
            name=shield_cfg.get("name", "local-shield"),
            policy_path=policy_path,
            rules_path=rules_path,
            llm=llm_classifier,
            trace_sink_path=trace_sink_path,
            trace_sinks=trace_sinks or None,
            challenge_store_path=challenge_store_path,
            challenge_webhook_url=challenge_webhook_url,
            proxy_upstreams=proxy_upstreams,
            fail_on_classifier_error=fail_on_classifier_error,
            redact_emails=redact_emails,
            expose_rule_ids=expose_rule_ids,
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
        timestamp = datetime.now(timezone.utc).isoformat()

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
            timestamp=timestamp,
            caller=caller_model,
            tool=ToolRef(name=tool),
            arguments=arguments or {},
            context=ctx,
        )

        classifications = await self.classifier_pipeline.classify(request)
        if self.classifier_pipeline.last_classifier_error:
            duration_ms = (time.perf_counter() - start) * 1000
            verdict = Verdict(
                requestId=rid,
                decision=self.fail_on_classifier_error,
                reason="Classifier pipeline failed; applied fail_on_classifier_error",
                classifications=classifications,
                durationMs=duration_ms,
                policyVersion=self.policy.version,
            )
        else:
            verdict = self.policy_engine.evaluate(request, classifications)
            verdict = verdict.model_copy(
                update={
                    "requestId": rid,
                    "durationMs": (time.perf_counter() - start) * 1000,
                }
            )
        verdict = self._attach_challenge(verdict, request_id=rid)

        if self.trace_sinks:
            trace_payload = build_trace_payload(
                trace_id=rid,
                shield_id=self.shield_id,
                timestamp=timestamp,
                request=request,
                classifications=classifications,
                verdict=verdict,
                redact_emails=self.redact_emails,
            )
            for sink in self.trace_sinks:
                sink.write(trace_payload)

        return verdict

    def reload_policy(self) -> None:
        """Reload policy from disk and refresh the policy engine."""
        new_compiled = load_policy(self.policy_path)
        new_engine = PolicyEngine(new_compiled)
        self.compiled_policy = new_compiled
        self.policy = new_compiled.policy
        self.policy_engine = new_engine

    async def record_outcome(self, request_id: str, outcome: str) -> None:
        """Record execution outcome for a prior request."""
        for sink in self.trace_sinks:
            sink.update_outcome(request_id, outcome)

    async def execute_upstream(
        self,
        *,
        tool: str,
        arguments: dict[str, Any] | None = None,
        caller: dict[str, Any] | Caller | None = None,
        context: dict[str, Any] | CallContext | None = None,
        request_id: str | None = None,
    ) -> tuple[Verdict, dict[str, Any] | None]:
        """Evaluate and forward the request to a configured upstream when ALLOW."""
        verdict = await self.evaluate(
            tool=tool,
            arguments=arguments,
            caller=caller,
            context=context,
            request_id=request_id,
        )
        if verdict.decision != VerdictType.ALLOW:
            return verdict, None

        upstream = self.proxy_upstreams.get(tool)
        if upstream is None:
            return verdict, None

        caller_model = (
            caller
            if isinstance(caller, Caller)
            else Caller.model_validate(caller or {"id": "anonymous", "type": "agent"})
        )
        ctx = context if isinstance(context, CallContext) else CallContext.model_validate(
            context or {}
        )
        request = ToolCallRequest(
            id=verdict.request_id,
            shieldId=self.shield_id,
            caller=caller_model,
            tool=ToolRef(name=tool),
            arguments=arguments or {},
            context=ctx,
        )
        result = await forward_upstream(request, upstream)
        await self.record_outcome(verdict.request_id, OutcomeType.EXECUTED.value)
        return verdict, result

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
                    await self._raise_for_verdict(
                        verdict,
                        await_challenge=await_challenge,
                    )
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
        """Synchronous guard decorator using asyncio.run for evaluation."""

        def decorator(fn: F) -> F:
            tool_name = tool or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                async def _run() -> Any:
                    verdict = await self.evaluate(
                        tool=tool_name,
                        arguments=kwargs or {},
                    )
                    await self._raise_for_verdict(
                        verdict,
                        await_challenge=await_challenge,
                    )
                    return fn(*args, **kwargs)

                return asyncio.run(_run())

            return wrapper  # type: ignore[return-value]

        return decorator

    def _attach_challenge(self, verdict: Verdict, *, request_id: str) -> Verdict:
        if verdict.decision not in (VerdictType.CHALLENGE, VerdictType.DEFER):
            return verdict
        if not verdict.matched_rule_id:
            return verdict

        rule = next(
            (item for item in self.policy.rules if item.id == verdict.matched_rule_id),
            None,
        )
        if rule is None or rule.challenge is None:
            return verdict

        challenge_id = self.challenge_store.create(
            request_id=request_id,
            reason=verdict.reason,
            timeout_seconds=rule.challenge.timeout_seconds,
            on_timeout=rule.challenge.on_timeout,
        )
        record = self.challenge_store.get(challenge_id)
        if record is not None:
            notify_challenge_created(
                record,
                channel=rule.challenge.channel,
                webhook_url=rule.challenge.url or self.challenge_webhook_url,
            )
        return verdict.model_copy(update={"challenge_id": challenge_id})

    async def _raise_for_verdict(
        self,
        verdict: Verdict,
        *,
        await_challenge: bool = False,
    ) -> None:
        agent_verdict = redact_verdict_for_agent(
            verdict,
            expose_rule_ids=self.expose_rule_ids,
        )
        if verdict.decision == VerdictType.BLOCK:
            raise LexShieldBlockedError(
                verdict.reason,
                verdict=agent_verdict,
                request_id=verdict.request_id,
            )
        if verdict.decision == VerdictType.CHALLENGE:
            if await_challenge:
                await self._await_challenge(verdict)
                return
            raise LexShieldChallengeError(
                verdict.reason,
                verdict=agent_verdict,
                request_id=verdict.request_id,
            )

    async def _await_challenge(self, verdict: Verdict) -> None:
        challenge_id = verdict.challenge_id
        if not challenge_id:
            raise LexShieldChallengeError(
                "Challenge required but no challenge id was created",
                verdict=verdict,
                request_id=verdict.request_id,
            )

        while True:
            self.challenge_store.expire_open()
            record = self.challenge_store.get(challenge_id)
            if record is None:
                raise LexShieldChallengeError(
                    f"Challenge {challenge_id} not found",
                    verdict=verdict,
                    request_id=verdict.request_id,
                )

            status = record.get("status")
            if status == "approved":
                return
            if status == "denied":
                raise LexShieldBlockedError(
                    "Challenge denied",
                    verdict=verdict,
                    request_id=verdict.request_id,
                )
            if status == "timed_out":
                on_timeout = VerdictType(record.get("onTimeout", VerdictType.BLOCK.value))
                if on_timeout == VerdictType.ALLOW:
                    return
                raise LexShieldBlockedError(
                    "Challenge timed out",
                    verdict=verdict,
                    request_id=verdict.request_id,
                )

            if self._challenge_timed_out(record):
                on_timeout = VerdictType(record.get("onTimeout", VerdictType.BLOCK.value))
                if on_timeout == VerdictType.ALLOW:
                    return
                raise LexShieldBlockedError(
                    "Challenge timed out",
                    verdict=verdict,
                    request_id=verdict.request_id,
                )

            await asyncio.sleep(_CHALLENGE_POLL_INTERVAL_SECONDS)

    @staticmethod
    def _challenge_timed_out(record: dict[str, Any]) -> bool:
        created_raw = record.get("createdAt")
        if not created_raw:
            return False
        created = datetime.fromisoformat(created_raw)
        timeout_seconds = int(record.get("timeoutSeconds", 3600))
        deadline = created + timedelta(seconds=timeout_seconds)
        return datetime.now(timezone.utc) >= deadline
