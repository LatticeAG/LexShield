"""YAML policy loader (stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lexshield.errors import LexShieldConfigError
from lexshield.models import Policy


def _validate_policy_structure(data: dict[str, Any]) -> None:
    """Validate minimal policy structure before Pydantic parse."""
    required = ("version", "id", "name", "defaultVerdict", "rules")
    missing = [field for field in required if field not in data]
    if missing:
        raise LexShieldConfigError(
            f"Policy missing required fields: {', '.join(missing)}"
        )
    if not isinstance(data.get("rules"), list):
        raise LexShieldConfigError("Policy 'rules' must be a list")


def load_policy(path: str | Path, *, strict: bool = False) -> Policy:
    """Load and validate a YAML policy file.

    Args:
        path: Path to policy.yaml.
        strict: When True, reject unknown top-level fields (stub: not enforced yet).

    Returns:
        Parsed Policy model.
    """
    policy_path = Path(path)
    if not policy_path.exists():
        raise LexShieldConfigError(f"Policy file not found: {policy_path}")

    with policy_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise LexShieldConfigError("Policy root must be a mapping")

    if strict:
        allowed = {
            "version",
            "id",
            "name",
            "description",
            "defaultVerdict",
            "rules",
            "taxonomyRef",
            "severity_threshold",
        }
        unknown = set(raw.keys()) - allowed
        if unknown:
            raise LexShieldConfigError(
                f"Unknown policy fields in strict mode: {', '.join(sorted(unknown))}"
            )

    _validate_policy_structure(raw)

    try:
        return Policy.model_validate(raw)
    except Exception as exc:
        raise LexShieldConfigError(f"Invalid policy: {exc}") from exc
