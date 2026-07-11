"""Smoke tests for core CLI flows."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lexshield_cli.main import app

runner = CliRunner()


def test_smoke_init_evaluate_and_challenge_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    init_result = runner.invoke(app, ["init", "--pack", "baseline-deny"])
    assert init_result.exit_code == 0, init_result.stdout
    assert (tmp_path / "lexshield.yaml").exists()
    assert (tmp_path / "policy.yaml").exists()
    assert (tmp_path / "rules.yaml").exists()
    policy_text = (tmp_path / "policy.yaml").read_text(encoding="utf-8")
    assert "challenge-delete-prod" in policy_text

    health_result = runner.invoke(
        app,
        ["evaluate", "--tool", "health_check", "--args", "{}", "-c", "lexshield.yaml"],
    )
    assert health_result.exit_code == 0, health_result.stdout
    assert "ALLOW" in health_result.stdout

    secret_result = runner.invoke(
        app,
        [
            "evaluate",
            "--tool",
            "send_email",
            "--args",
            '{"body":"AKIAIOSFODNN7EXAMPLE"}',
            "-c",
            "lexshield.yaml",
            "--json",
        ],
    )
    assert secret_result.exit_code == 0, secret_result.stdout
    assert json.loads(secret_result.stdout)["decision"] == "BLOCK"

    challenge_result = runner.invoke(app, ["challenge", "list", "-c", "lexshield.yaml"])
    assert challenge_result.exit_code == 0, challenge_result.stdout
    assert "No open challenges" in challenge_result.stdout
