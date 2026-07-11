"""Tests for expose_rule_ids shield configuration."""

from __future__ import annotations

import pytest

from pathlib import Path

from lexshield.errors import (
    LexShieldBlockedError,
    agent_facing_error,
    redact_verdict_for_agent,
)
from lexshield.models import Verdict, VerdictType
from lexshield.shield import Shield

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"
BASELINE_POLICY = PACKS_DIR / "baseline-deny" / "policy.yaml"
BASELINE_RULES = PACKS_DIR / "baseline-deny" / "rules.yaml"


@pytest.fixture
def shield_with_exposed_ids(tmp_path: Path) -> Shield:
    return Shield(
        shield_id="test",
        name="test-shield",
        policy_path=BASELINE_POLICY,
        rules_path=BASELINE_RULES,
        expose_rule_ids=True,
    )


@pytest.fixture
def shield_without_exposed_ids(tmp_path: Path) -> Shield:
    return Shield(
        shield_id="test",
        name="test-shield",
        policy_path=BASELINE_POLICY,
        rules_path=BASELINE_RULES,
        expose_rule_ids=False,
    )


def _blocked_verdict() -> Verdict:
    return Verdict(
        requestId="01JTEST",
        decision=VerdictType.BLOCK,
        matchedRuleId="block-secret-exposure",
        reason="Possible secret exposure in tool arguments",
        durationMs=1.0,
    )


def test_agent_facing_error_includes_rule_id_by_default() -> None:
    payload = agent_facing_error(_blocked_verdict())

    assert payload["matchedRuleId"] == "block-secret-exposure"
    assert payload["error"] == "lexshield_blocked"
    assert payload["verdict"] == "BLOCK"


def test_agent_facing_error_omits_rule_id_when_disabled() -> None:
    payload = agent_facing_error(_blocked_verdict(), expose_rule_ids=False)

    assert "matchedRuleId" not in payload
    assert payload["reason"] == "Possible secret exposure in tool arguments"


def test_redact_verdict_for_agent_strips_matched_rule_id() -> None:
    redacted = redact_verdict_for_agent(_blocked_verdict(), expose_rule_ids=False)

    assert redacted.matched_rule_id is None
    assert redacted.reason == _blocked_verdict().reason


@pytest.mark.asyncio
async def test_guard_error_includes_rule_id_when_exposed(
    shield_with_exposed_ids: Shield,
) -> None:
    @shield_with_exposed_ids.guard(tool="send_email")
    async def send_email(body: str) -> None:
        return None

    with pytest.raises(LexShieldBlockedError) as exc_info:
        await send_email(body="AKIAIOSFODNN7EXAMPLE")

    assert exc_info.value.verdict is not None
    assert exc_info.value.verdict.matched_rule_id == "block-secret-exposure"


@pytest.mark.asyncio
async def test_guard_error_strips_rule_id_when_not_exposed(
    shield_without_exposed_ids: Shield,
) -> None:
    @shield_without_exposed_ids.guard(tool="send_email")
    async def send_email(body: str) -> None:
        return None

    with pytest.raises(LexShieldBlockedError) as exc_info:
        await send_email(body="AKIAIOSFODNN7EXAMPLE")

    assert exc_info.value.verdict is not None
    assert exc_info.value.verdict.matched_rule_id is None


def test_from_config_defaults_expose_rule_ids_true(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    (config_dir / "policy.yaml").write_text(BASELINE_POLICY.read_text(encoding="utf-8"))
    (config_dir / "rules.yaml").write_text(BASELINE_RULES.read_text(encoding="utf-8"))
    config_path = config_dir / "lexshield.yaml"
    config_path.write_text(
        """\
version: 1
shield:
  id: local
  name: local-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
""",
        encoding="utf-8",
    )

    shield = Shield.from_config(config_path)

    assert shield.expose_rule_ids is True


def test_from_config_parses_expose_rule_ids_false(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    (config_dir / "policy.yaml").write_text(BASELINE_POLICY.read_text(encoding="utf-8"))
    (config_dir / "rules.yaml").write_text(BASELINE_RULES.read_text(encoding="utf-8"))
    config_path = config_dir / "lexshield.yaml"
    config_path.write_text(
        """\
version: 1
shield:
  id: local
  name: local-shield
  policy: ./policy.yaml
  expose_rule_ids: false
  classifiers:
    - type: deterministic
      path: ./rules.yaml
""",
        encoding="utf-8",
    )

    shield = Shield.from_config(config_path)

    assert shield.expose_rule_ids is False
