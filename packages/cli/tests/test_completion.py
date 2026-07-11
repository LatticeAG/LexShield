"""Tests for lexshield completion command."""

from __future__ import annotations

from typer.testing import CliRunner

from lexshield_cli.main import app

runner = CliRunner()


def test_completion_bash_emits_script() -> None:
    result = runner.invoke(app, ["completion", "bash"])
    assert result.exit_code == 0, result.stdout
    assert "_lexshield_completion" in result.stdout
    assert "complete" in result.stdout


def test_completion_rejects_unknown_shell() -> None:
    result = runner.invoke(app, ["completion", "powershell"])
    assert result.exit_code == 1
