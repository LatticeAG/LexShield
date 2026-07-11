"""Tests for lexshield check command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from lexshield_cli.commands.init import LEXSHIELD_YAML, POLICY_TEMPLATES, RULES_YAML
from lexshield_cli.main import app

runner = CliRunner()


def test_check_valid_init_scaffold(tmp_path: Path) -> None:
    (tmp_path / "lexshield.yaml").write_text(LEXSHIELD_YAML, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(POLICY_TEMPLATES["baseline-deny"], encoding="utf-8")
    (tmp_path / "rules.yaml").write_text(RULES_YAML, encoding="utf-8")

    result = runner.invoke(app, ["check", "-c", str(tmp_path / "lexshield.yaml")])

    assert result.exit_code == 0, result.stdout
    assert "OK" in result.stdout
    assert "policy rule" in result.stdout


def test_check_fails_when_rules_missing(tmp_path: Path) -> None:
    (tmp_path / "lexshield.yaml").write_text(LEXSHIELD_YAML, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(POLICY_TEMPLATES["baseline-deny"], encoding="utf-8")

    result = runner.invoke(app, ["check", "-c", str(tmp_path / "lexshield.yaml")])

    assert result.exit_code == 1
    assert "Rules file not found" in result.stdout
