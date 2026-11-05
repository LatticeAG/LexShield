"""The challenge demo exposes its result separately from operator messages."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("arguments, decision", [([], "ALLOW"), (["--challenge-only"], "CHALLENGE")])
def test_challenge_demo_streams(arguments: list[str], decision: str) -> None:
    root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [sys.executable, str(root / "examples/python-challenge-delete/main.py"), *arguments],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["decision"] == decision
    assert "CHALLENGE" in result.stderr
    if decision == "ALLOW":
        assert payload["result"]["status"] == "deleted"
        assert "Approving via CLI" in result.stderr
    else:
        assert payload["challenge_id"]
        assert "Approve manually" in result.stderr
