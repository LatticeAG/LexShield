"""Helpers for loading and running golden policy fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from lexshield.classifiers.deterministic import DeterministicClassifier
from lexshield.models import Classification, ToolCallRequest, Verdict
from lexshield.policy.engine import PolicyEngine
from lexshield.policy.loader import load_policy, load_policy_data

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_ROOT = WORKSPACE_ROOT / "fixtures" / "golden"
UNKNOWN_INTENT = "unknown.unclassified"


@dataclass(frozen=True)
class GoldenFixture:
    """Loaded golden scenario inputs and expectations."""

    name: str
    directory: Path
    request: ToolCallRequest
    expected: dict[str, Any]
    policy_engine: PolicyEngine
    classifier: DeterministicClassifier
    strict: bool = False


def discover_golden_scenarios(root: Path | None = None) -> list[str]:
    """Return sorted scenario directory names under fixtures/golden."""
    base = root or GOLDEN_ROOT
    if not base.exists():
        return []
    return sorted(
        entry.name
        for entry in base.iterdir()
        if entry.is_dir() and (entry / "request.json").exists()
    )


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _load_policy_ref(scenario_dir: Path) -> tuple[PolicyEngine, DeterministicClassifier]:
    policy_ref_path = scenario_dir / "policy-ref.yaml"
    if not policy_ref_path.exists():
        raise FileNotFoundError(f"Missing policy-ref.yaml in {scenario_dir}")

    with policy_ref_path.open(encoding="utf-8") as handle:
        policy_ref = yaml.safe_load(handle) or {}

    policy_data = policy_ref.get("policy")
    if isinstance(policy_data, dict):
        compiled_policy = load_policy_data(policy_data)
    elif isinstance(policy_data, str):
        compiled_policy = load_policy(_resolve_path(scenario_dir, policy_data))
    else:
        pack_policy = policy_ref.get("pack")
        if pack_policy:
            default_policy = WORKSPACE_ROOT / "packs" / pack_policy / "policy.yaml"
            compiled_policy = load_policy(default_policy)
        else:
            raise ValueError(f"policy-ref.yaml in {scenario_dir} must define policy or pack")

    rules_ref = policy_ref.get("rules")
    if isinstance(rules_ref, str):
        rules_path = _resolve_path(scenario_dir, rules_ref)
    elif (scenario_dir / "rules-ref.yaml").exists():
        rules_path = scenario_dir / "rules-ref.yaml"
    elif policy_ref.get("pack"):
        rules_path = WORKSPACE_ROOT / "packs" / policy_ref["pack"] / "rules.yaml"
    else:
        rules_path = None

    classifier = DeterministicClassifier(rules_path)
    return PolicyEngine(compiled_policy), classifier


def load_golden_fixture(scenario: str, *, root: Path | None = None) -> GoldenFixture:
    """Load a golden scenario by directory name."""
    base = root or GOLDEN_ROOT
    scenario_dir = base / scenario
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"Golden scenario not found: {scenario_dir}")

    with (scenario_dir / "request.json").open(encoding="utf-8") as handle:
        request_data = json.load(handle)

    with (scenario_dir / "expected.json").open(encoding="utf-8") as handle:
        expected = json.load(handle)

    policy_engine, classifier = _load_policy_ref(scenario_dir)
    request = ToolCallRequest.model_validate(request_data)
    strict = bool(expected.pop("strict", False))

    return GoldenFixture(
        name=scenario,
        directory=scenario_dir,
        request=request,
        expected=expected,
        policy_engine=policy_engine,
        classifier=classifier,
        strict=strict,
    )


def _classifications_for_request(
    request: ToolCallRequest,
    classifier: DeterministicClassifier,
    *,
    scenario_dir: Path | None = None,
) -> list[Classification]:
    """Run deterministic classifier only, matching CI golden semantics."""
    if scenario_dir is not None:
        classifications_ref = scenario_dir / "classifications-ref.json"
        if classifications_ref.exists():
            with classifications_ref.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return [Classification.model_validate(item) for item in data]

    result = classifier.classify(request)
    if result is not None:
        return [result]
    return [
        Classification(
            intent=UNKNOWN_INTENT,
            confidence=0.3,
            alternatives=[],
            classifier="deterministic:v1",
            reasoning="No deterministic classification",
        )
    ]


def run_golden_fixture(fixture: GoldenFixture) -> Verdict:
    """Evaluate a loaded golden fixture and return the verdict."""
    classifications = _classifications_for_request(
        fixture.request,
        fixture.classifier,
        scenario_dir=fixture.directory,
    )
    return fixture.policy_engine.evaluate(fixture.request, classifications)


def primary_intent(verdict: Verdict) -> str | None:
    """Return the primary classification intent from a verdict."""
    if not verdict.classifications:
        return None
    return verdict.classifications[0].intent
