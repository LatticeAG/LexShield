"""Shield SDK integration tests."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from lexshield.challenges.store import ChallengeStore
from lexshield.errors import LexShieldBlockedError, LexShieldChallengeError
from lexshield.models import VerdictType
from lexshield.shield import Shield
from lexshield.traces.sink import NDJSONTraceSink, StdoutTraceSink

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"
BASELINE_POLICY = PACKS_DIR / "baseline-deny" / "policy.yaml"
BASELINE_RULES = PACKS_DIR / "baseline-deny" / "rules.yaml"


@pytest.fixture
def shield(tmp_path: Path) -> Shield:
    trace_path = tmp_path / "traces.ndjson"
    challenge_path = tmp_path / "challenges"
    return Shield(
        shield_id="test",
        name="test-shield",
        policy_path=BASELINE_POLICY,
        rules_path=BASELINE_RULES,
        trace_sink_path=trace_path,
        challenge_store_path=challenge_path,
    )


@pytest.fixture
def lexshield_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    (config_dir / "policy.yaml").write_text(BASELINE_POLICY.read_text(encoding="utf-8"))
    (config_dir / "rules.yaml").write_text(BASELINE_RULES.read_text(encoding="utf-8"))
    config_path = config_dir / "lexshield.yaml"
    config_path.write_text(
        f"""\
version: 1
shield:
  id: local
  name: local-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
  fail_on_classifier_error: BLOCK
  redact:
    emails: hash
  sinks:
    - type: stdout
    - type: file
      path: ./traces.ndjson
  challenges:
    path: ./challenges
  proxy:
    enabled: true
    upstreams:
      health_check:
        url: http://127.0.0.1:9999/health
        timeoutMs: 1000
""",
        encoding="utf-8",
    )
    return config_path


@pytest.mark.asyncio
async def test_evaluate_allow_health_check(shield: Shield) -> None:
    verdict = await shield.evaluate(tool="health_check", arguments={})
    assert verdict.decision == VerdictType.ALLOW
    assert verdict.matched_rule_id == "allow-health"


@pytest.mark.asyncio
async def test_evaluate_block_secret_exposure(shield: Shield) -> None:
    verdict = await shield.evaluate(
        tool="send_email",
        arguments={"body": "AKIAIOSFODNN7EXAMPLE"},
    )
    assert verdict.decision == VerdictType.BLOCK
    assert verdict.matched_rule_id == "block-secret-exposure"


@pytest.mark.asyncio
async def test_challenge_creation_on_evaluate(shield: Shield) -> None:
    verdict = await shield.evaluate(
        tool="delete_resource",
        context={"environment": "production"},
    )
    assert verdict.decision == VerdictType.CHALLENGE
    assert verdict.matched_rule_id == "challenge-delete-prod"
    assert verdict.challenge_id is not None

    record = shield.challenge_store.get(verdict.challenge_id)
    assert record is not None
    assert record["requestId"] == verdict.request_id
    assert record["status"] == "open"
    assert record["timeoutSeconds"] == 3600
    assert record["onTimeout"] == VerdictType.BLOCK.value


@pytest.mark.asyncio
async def test_trace_format_redacts_emails_and_includes_classifications(
    shield: Shield,
) -> None:
    await shield.evaluate(
        tool="send_email",
        arguments={
            "to": "user@example.com",
            "body": "AKIAIOSFODNN7EXAMPLE",
        },
    )

    sink = shield.trace_sink
    assert isinstance(sink, NDJSONTraceSink)
    traces = sink.read_all()
    assert len(traces) == 1

    trace = traces[0]
    assert trace["shieldId"] == "test"
    assert "classifications" in trace
    assert trace["classifications"]
    assert trace["classifications"][0]["intent"] == "security.secret_exposure"

    redacted_args = trace["request"]["arguments_redacted"]
    assert "user@example.com" not in json.dumps(redacted_args)
    assert "[EMAIL_HASH:" in json.dumps(redacted_args)
    assert "[REDACTED_AWS_KEY]" in redacted_args["body"]


@pytest.mark.asyncio
async def test_record_outcome_updates_trace(shield: Shield) -> None:
    verdict = await shield.evaluate(tool="health_check", arguments={})
    await shield.record_outcome(verdict.request_id, "EXECUTED")

    sink = shield.trace_sink
    assert isinstance(sink, NDJSONTraceSink)
    traces = sink.read_all()
    assert traces[0]["outcome"] == "EXECUTED"
    assert "outcomeAt" in traces[0]


@pytest.mark.asyncio
async def test_guard_blocks_async(shield: Shield) -> None:
    @shield.guard(tool="send_email")
    async def send_email(body: str) -> dict[str, str]:
        return {"status": "sent", "body": body}

    with pytest.raises(LexShieldBlockedError) as exc_info:
        await send_email(body="AKIAIOSFODNN7EXAMPLE")

    assert exc_info.value.verdict is not None
    assert exc_info.value.verdict.decision == VerdictType.BLOCK


@pytest.mark.asyncio
async def test_guard_allows_async(shield: Shield) -> None:
    @shield.guard(tool="health_check")
    async def health_check() -> str:
        return "ok"

    assert await health_check() == "ok"


def test_guard_sync_blocks(shield: Shield) -> None:
    @shield.guard_sync(tool="send_email")
    def send_email(body: str) -> dict[str, str]:
        return {"status": "sent", "body": body}

    with pytest.raises(LexShieldBlockedError):
        send_email(body="AKIAIOSFODNN7EXAMPLE")


def test_guard_sync_allows(shield: Shield) -> None:
    @shield.guard_sync(tool="health_check")
    def health_check() -> str:
        return "ok"

    assert health_check() == "ok"


def test_guard_sync_await_challenge_approved(shield: Shield) -> None:
    @shield.guard_sync(tool="delete_resource", await_challenge=True)
    def delete_resource(resource_id: str) -> dict[str, str]:
        return {"deleted": resource_id}

    def approve_after_delay() -> None:
        time.sleep(0.15)
        open_challenges = shield.challenge_store.list_open()
        assert len(open_challenges) == 1
        challenge_id = open_challenges[0]["id"]
        shield.challenge_store.resolve(challenge_id, decision="approve", actor="test")

    with shield.session(environment="production"):
        approver = threading.Thread(target=approve_after_delay)
        approver.start()
        result = delete_resource(resource_id="db-1")
        approver.join()

    assert result == {"deleted": "db-1"}


def test_guard_sync_raises_challenge_without_await(shield: Shield) -> None:
    @shield.guard_sync(tool="delete_resource")
    def delete_resource(resource_id: str) -> dict[str, str]:
        return {"deleted": resource_id}

    with shield.session(environment="production"):
        with pytest.raises(LexShieldChallengeError) as exc_info:
            delete_resource(resource_id="db-1")

    assert exc_info.value.verdict is not None
    assert exc_info.value.verdict.challenge_id is not None


def test_from_config_loads_sinks_and_proxy(lexshield_config: Path) -> None:
    shield = Shield.from_config(lexshield_config)
    assert shield.fail_on_classifier_error == VerdictType.BLOCK
    assert shield.redact_emails == "hash"
    assert len(shield.trace_sinks) == 2
    assert any(isinstance(sink, StdoutTraceSink) for sink in shield.trace_sinks)
    assert any(isinstance(sink, NDJSONTraceSink) for sink in shield.trace_sinks)
    assert "health_check" in shield.proxy_upstreams
    assert isinstance(shield.challenge_store, ChallengeStore)
