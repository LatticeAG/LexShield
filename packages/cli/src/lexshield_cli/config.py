"""Shared lexshield.yaml path resolution for CLI commands."""

from __future__ import annotations

from pathlib import Path

import yaml

from lexshield.errors import LexShieldConfigError

DEFAULT_TRACE_PATH = Path("traces.ndjson")
DEFAULT_CHALLENGES_DIR = Path(".lexshield/challenges")


def resolve_config_path(config: Path) -> Path:
    """Accept a lexshield.yaml path or directory containing it."""
    if config.is_dir():
        candidate = config / "lexshield.yaml"
        if candidate.is_file():
            return candidate
        raise LexShieldConfigError(f"No lexshield.yaml found in directory: {config}")
    return config


def _load_config_raw(config: Path) -> dict:
    with config.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise LexShieldConfigError("Config root must be a mapping")
    return raw


def resolve_policy_and_rules(
    config: Path,
) -> tuple[Path, Path | None]:
    """Return policy and optional rules paths relative to config directory."""
    raw = _load_config_raw(config)
    shield_cfg = raw.get("shield")
    if not isinstance(shield_cfg, dict):
        raise LexShieldConfigError("Config must contain a 'shield' section")

    base_dir = config.parent
    policy_path = base_dir / shield_cfg.get("policy", "./policy.yaml")
    rules_path: Path | None = None
    for classifier in shield_cfg.get("classifiers", []):
        if isinstance(classifier, dict) and classifier.get("type") == "deterministic":
            rules_path = base_dir / classifier.get("path", "./rules.yaml")
            break
    return policy_path, rules_path


def resolve_trace_path(
    config: Path,
    *,
    trace_file: Path | None = None,
) -> Path:
    """Resolve NDJSON trace file from --trace-file or config file sink."""
    if trace_file is not None:
        return trace_file

    if not config.exists():
        return config.parent / DEFAULT_TRACE_PATH

    config_path = resolve_config_path(config)
    raw = _load_config_raw(config_path)
    shield_cfg = raw.get("shield", {})
    if not isinstance(shield_cfg, dict):
        return config_path.parent / DEFAULT_TRACE_PATH

    base_dir = config_path.parent
    for sink in shield_cfg.get("sinks", []):
        if isinstance(sink, dict) and sink.get("type") == "file":
            return base_dir / sink.get("path", "./traces.ndjson")
    return base_dir / DEFAULT_TRACE_PATH


def resolve_challenges_path(
    config: Path,
    *,
    challenges_dir: Path | None = None,
) -> Path:
    """Resolve challenge store directory from --dir or config directory."""
    if challenges_dir is not None:
        return challenges_dir

    if config.exists():
        config_path = resolve_config_path(config)
        raw = _load_config_raw(config_path)
        shield_cfg = raw.get("shield", {})
        if isinstance(shield_cfg, dict):
            configured = shield_cfg.get("challenges")
            if isinstance(configured, dict) and configured.get("path"):
                return config_path.parent / configured["path"]
        return config_path.parent / DEFAULT_CHALLENGES_DIR

    return Path.cwd() / DEFAULT_CHALLENGES_DIR
