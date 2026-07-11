"""Tests for lexshield evaluate command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lexshield_cli.commands.init import LEXSHIELD_YAML, POLICY_TEMPLATES, RULES_YAML
from lexshield_cli.main import app

runner = CliRunner()


def _scaffold(tmp_path: Path) -> Path:
    (tmp_path / "lexshield.yaml").write_text(LEXSHIELD_YAML, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(POLICY_TEMPLATES["baseline-deny"], encoding="utf-8")
    (tmp_path / "rules.yaml").write_text(RULES_YAML, encoding="utf-8")
    return tmp_path / "lexshield.yaml"


def test_evaluate_health_allow(tmp_path: Path) -> None:
    config = _scaffold(tmp_path)
    result = runner.invoke(
        app,
        ["evaluate", "--tool", "health_check", "--args", "{}", "-c", str(config)],
    )
    assert result.exit_code == 0, result.stdout
    assert "ALLOW" in result.stdout
    assert "allow-health" in result.stdout


def test_evaluate_block_secret(tmp_path: Path) -> None:
    config = _scaffold(tmp_path)
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--tool",
            "send_email",
            "--args",
            '{"body":"AKIAIOSFODNN7EXAMPLE"}',
            "-c",
            str(config),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "BLOCK"
    assert payload["matchedRuleId"] == "block-secret-exposure"


def test_evaluate_stdin_tool_call_request(tmp_path: Path) -> None:
    config = _scaffold(tmp_path)
    request = {
        "caller": {"id": "agent-1", "type": "agent"},
        "tool": {"name": "health_check"},
        "arguments": {},
        "context": {"environment": "staging"},
    }
    result = runner.invoke(
        app,
        ["evaluate", "--stdin", "-c", str(config), "--json"],
        input=json.dumps(request),
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "ALLOW"


def test_evaluate_caller_environment_tags(tmp_path: Path) -> None:
    config = _scaffold(tmp_path)
    caller = json.dumps({"id": "svc-1", "type": "service_account", "roles": ["ops"]})
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--tool",
            "delete_resource",
            "--args",
            "{}",
            "--caller",
            caller,
            "--environment",
            "production",
            "--tags",
            '{"change_ticket":"INC-42"}',
            "-c",
            str(config),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "CHALLENGE"
    assert payload["matchedRuleId"] == "challenge-delete-prod"
