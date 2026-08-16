"""Tests for lexshield packs apply command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from lexshield_cli.main import app

runner = CliRunner()


def test_packs_apply_copies_rules(tmp_path: Path, monkeypatch) -> None:
    # Must run from a directory with packs/ reachable (repo root or below);
    # the CLI locates packs/ by walking up from cwd.
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root)
    result = runner.invoke(
        app,
        [
            "packs",
            "apply",
            "baseline-deny",
            "-o",
            str(tmp_path / "policy.yaml"),
            "--rules-output",
            str(tmp_path / "rules.yaml"),
            "--force",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "policy.yaml").exists()
    assert (tmp_path / "rules.yaml").exists()
    rules_text = (tmp_path / "rules.yaml").read_text(encoding="utf-8")
    assert "security.secret_exposure" in rules_text
