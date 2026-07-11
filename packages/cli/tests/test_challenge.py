"""Tests for lexshield challenge command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from lexshield.challenges.store import ChallengeStore
from lexshield_cli.main import app

runner = CliRunner()


def test_challenge_list_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["challenge", "list", "--dir", str(tmp_path / "challenges")])
    assert result.exit_code == 0, result.stdout
    assert "No open challenges" in result.stdout


def test_challenge_list_approve_deny(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store_dir = tmp_path / ".lexshield" / "challenges"
    store = ChallengeStore(store_dir)
    challenge_id = store.create(request_id="req-1", reason="Production delete")

    list_result = runner.invoke(app, ["challenge", "list", "--dir", str(store_dir)])
    assert list_result.exit_code == 0, list_result.stdout
    assert "open" in list_result.stdout
    assert "Production delete" in list_result.stdout

    approve_result = runner.invoke(
        app,
        ["challenge", "approve", challenge_id, "--dir", str(store_dir)],
    )
    assert approve_result.exit_code == 0, approve_result.stdout
    assert challenge_id in approve_result.stdout
    assert "approved" in approve_result.stdout

    challenge_id_2 = store.create(request_id="req-2", reason="Another change")
    deny_result = runner.invoke(
        app,
        ["challenge", "deny", challenge_id_2, "--dir", str(store_dir)],
    )
    assert deny_result.exit_code == 0, deny_result.stdout
    assert "denied" in deny_result.stdout
