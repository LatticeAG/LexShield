"""Golden fixture regression tests for the policy engine."""

from __future__ import annotations

import pytest

from golden_runner import (
    discover_golden_scenarios,
    load_golden_fixture,
    primary_intent,
    run_golden_fixture,
)

GOLDEN_SCENARIOS = discover_golden_scenarios()


@pytest.mark.golden
@pytest.mark.parametrize("scenario", GOLDEN_SCENARIOS)
def test_golden_fixture(scenario: str) -> None:
    """Each fixtures/golden/<scenario> must match expected verdict fields."""
    fixture = load_golden_fixture(scenario)
    verdict = run_golden_fixture(fixture)
    expected = fixture.expected

    assert verdict.decision.value == expected["decision"], (
        f"{scenario}: decision expected {expected['decision']!r}, got {verdict.decision.value!r}"
    )

    if "matchedRuleId" in expected:
        assert verdict.matched_rule_id == expected["matchedRuleId"], (
            f"{scenario}: matchedRuleId expected {expected['matchedRuleId']!r}, "
            f"got {verdict.matched_rule_id!r}"
        )
    elif expected.get("matchedRuleId") is None:
        assert verdict.matched_rule_id is None

    assert verdict.reason == expected["reason"], (
        f"{scenario}: reason expected {expected['reason']!r}, got {verdict.reason!r}"
    )

    if "primaryIntent" in expected:
        assert primary_intent(verdict) == expected["primaryIntent"], (
            f"{scenario}: primaryIntent expected {expected['primaryIntent']!r}, "
            f"got {primary_intent(verdict)!r}"
        )

    if fixture.strict:
        if "durationMs" in expected:
            assert verdict.duration_ms == expected["durationMs"]
        if "challengeId" in expected:
            assert verdict.challenge_id == expected["challengeId"]
