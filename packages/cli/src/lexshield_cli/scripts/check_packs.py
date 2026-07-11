"""Validate all shipped policy packs (used in CI)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PACKS = ("baseline-deny", "pii-guard", "change-window")


def _repo_root() -> Path:
    start = Path(__file__).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "packs" / "baseline-deny" / "policy.yaml").is_file():
            return candidate
    raise RuntimeError("Could not locate repository root (packs/baseline-deny/policy.yaml)")


def main() -> int:
    root = _repo_root()
    packs_root = root / "packs"

    for pack in PACKS:
        policy = packs_root / pack / "policy.yaml"
        rules = packs_root / pack / "rules.yaml"
        if not policy.is_file():
            print(f"error: missing policy for pack {pack}: {policy}", file=sys.stderr)
            return 1

        print(f"Checking pack: {pack}")
        command = [
            "lexshield",
            "check",
            "--policy",
            str(policy),
            "--rules",
            str(rules),
            "--strict",
        ]
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode != 0:
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
