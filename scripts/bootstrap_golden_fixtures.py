#!/usr/bin/env python3
"""Bootstrap golden fixture directories and expected.json from engine output."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "packages" / "engine-py" / "tests"))

from golden_runner import (  # noqa: E402
    GOLDEN_ROOT,
    _classifications_for_request,
    _load_policy_ref,
    load_golden_fixture,
    primary_intent,
    run_golden_fixture,
)
from lexshield.models import ToolCallRequest  # noqa: E402


def evaluate_scenario(scenario: str) -> dict:
    scenario_dir = GOLDEN_ROOT / scenario
    with (scenario_dir / "request.json").open(encoding="utf-8") as handle:
        request_data = json.load(handle)
    policy_engine, classifier = _load_policy_ref(scenario_dir)
    request = ToolCallRequest.model_validate(request_data)
    classifications = _classifications_for_request(
        request,
        classifier,
        scenario_dir=scenario_dir,
    )
    verdict = policy_engine.evaluate(request, classifications)
    expected: dict = {
        "decision": verdict.decision.value,
        "reason": verdict.reason,
        "primaryIntent": primary_intent(verdict),
    }
    if verdict.matched_rule_id is not None:
        expected["matchedRuleId"] = verdict.matched_rule_id
    return expected


def ensure_fixture(scenario: str, files: dict[str, object]) -> None:
    scenario_dir = GOLDEN_ROOT / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = scenario_dir / name
        if path.exists():
            continue
        if name.endswith(".json"):
            path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        elif name.endswith(".yaml"):
            path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")


def main() -> None:
    baseline_policy_ref = {
        "pack": "baseline-deny",
        "policy": "../../../packs/baseline-deny/policy.yaml",
        "rules": "../../../packs/baseline-deny/rules.yaml",
    }
    pii_policy_ref = {
        "pack": "pii-guard",
        "policy": "../../../packs/pii-guard/policy.yaml",
        "rules": "../../../packs/pii-guard/rules.yaml",
    }
    change_policy_ref = {
        "pack": "change-window",
        "policy": "../../../packs/change-window/policy.yaml",
        "rules": "../../../packs/change-window/rules.yaml",
    }

    fixtures: dict[str, dict[str, object]] = {
        # §9B.9 matrix rows
        "allow-ping": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTUREALLOWPING01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "ping"},
                "arguments": {},
                "context": {"environment": "staging"},
            },
        },
        "block-delete-staging-default": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTUREBLOCKDELSTG01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "delete_resource"},
                "arguments": {"resource_id": "vol-123"},
                "context": {"environment": "staging"},
            },
        },
        "block-unclassified-low-conf": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTUREBLOCKUNCLASS01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "mystery_widget"},
                "arguments": {},
                "context": {"environment": "development"},
            },
        },
        "allow-health-prod": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTUREALLOWHLTHPRD01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "health_check"},
                "arguments": {},
                "context": {"environment": "production"},
            },
        },
        "block-secret-beats-challenge": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTURESECBEATCHAL01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "delete_resource"},
                "arguments": {
                    "resource_id": "db-prod-1",
                    "note": "AKIAIOSFODNN7EXAMPLE",
                },
                "context": {"environment": "production"},
            },
        },
        "priority-secret-over-exfil": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "priority-secret-over-exfil",
                    "name": "Secret priority over exfil",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "block-exfil",
                            "name": "Block exfiltration",
                            "priority": 300,
                            "match": {"intents": ["data.exfiltrate"]},
                            "verdict": "BLOCK",
                            "reason": "Possible data exfiltration",
                        },
                        {
                            "id": "block-secret-exposure",
                            "name": "Block secret exposure",
                            "priority": 310,
                            "match": {"intents": ["security.secret_exposure"]},
                            "verdict": "BLOCK",
                            "reason": "Possible secret exposure in tool arguments",
                        },
                    ],
                },
            },
            "classifications-ref.json": [
                {
                    "intent": "security.secret_exposure",
                    "confidence": 0.98,
                    "alternatives": [
                        {"intent": "data.exfiltrate", "confidence": 0.95}
                    ],
                    "classifier": "deterministic:v1",
                }
            ],
            "request.json": {
                "id": "01JFIXTUREPRISECEXFIL01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "send_email"},
                "arguments": {
                    "body": "export customer list with secret material",
                },
                "context": {"environment": "staging"},
            },
        },
        "allow-http-allowlist": {
            "policy-ref.yaml": pii_policy_ref,
            "request.json": {
                "id": "01JFIXTUREALLOWHTTPAL01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "http_request"},
                "arguments": {"url": "https://api.mycompany.com/v1/status"},
                "context": {"environment": "production"},
            },
        },
        "block-finance-transfer": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTUREBLOCKFINXFER01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "transfer_funds"},
                "arguments": {"amount": 100, "to_account": "acct-9"},
                "context": {"environment": "production"},
            },
        },
        "tie-priority-by-rule-id": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "tie-priority-by-rule-id",
                    "name": "Tie priority by rule id",
                    "defaultVerdict": "ALLOW",
                    "rules": [
                        {
                            "id": "aaa-block",
                            "name": "AAA block",
                            "priority": 200,
                            "match": {"tools": ["tie_tool"]},
                            "verdict": "BLOCK",
                            "reason": "Lower rule id wins on tie",
                        },
                        {
                            "id": "zzz-allow",
                            "name": "ZZZ allow",
                            "priority": 200,
                            "match": {"tools": ["tie_tool"]},
                            "verdict": "ALLOW",
                            "reason": "Higher id loses on tie",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTURETIEPRIORITY01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "tie_tool"},
                "arguments": {},
                "context": {"environment": "staging"},
            },
        },
        "expression-env-prod": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "expression-env-prod",
                    "name": "Expression env production challenge",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "expr-prod-challenge",
                            "name": "Challenge in production",
                            "priority": 200,
                            "match": {
                                "intents": ["infra.mutate.resource"],
                                "expression": 'env == "production"',
                            },
                            "verdict": "CHALLENGE",
                            "reason": "Production mutations require approval",
                            "challenge": {
                                "channel": "stdout",
                                "timeoutSeconds": 3600,
                                "onTimeout": "BLOCK",
                            },
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREEXPRESSIONENV01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "update_resource"},
                "arguments": {"resource_id": "svc-1"},
                "context": {"environment": "production"},
            },
        },
        "defers-verdict": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "defers-verdict",
                    "name": "Defer verdict fixture policy",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "defer-review",
                            "name": "Defer for manual review",
                            "priority": 200,
                            "match": {
                                "tools": ["update_resource"],
                                "intents": ["infra.mutate.resource"],
                            },
                            "verdict": "DEFER",
                            "reason": "Deferred for manual policy review",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREDEFERSVERDICT01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "update_resource"},
                "arguments": {"resource_id": "svc-2"},
                "context": {"environment": "staging"},
            },
        },
        "tool-glob-send-wildcard": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "tool-glob-send-wildcard",
                    "name": "Glob tool send wildcard fixture",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-send-tools",
                            "name": "Allow send_* tools",
                            "priority": 100,
                            "match": {
                                "tools": ["send_*"],
                                "intents": ["comms.send.slack", "comms.send.email"],
                            },
                            "verdict": "ALLOW",
                            "reason": "Send tools are allowed",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREGLOBSENDWILD01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "send_slack"},
                "arguments": {"channel": "#ops", "text": "status ok"},
                "context": {"environment": "staging"},
            },
        },
        "caller-id-match": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "caller-id-match",
                    "name": "Caller id match fixture",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-ci",
                            "name": "Allow CI bot",
                            "priority": 100,
                            "match": {
                                "callers": ["ci-bot"],
                                "tools": ["health_check", "ping"],
                            },
                            "verdict": "ALLOW",
                            "reason": "CI bot health checks allowed",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTURECALLERIDMATCH01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "ci-bot", "type": "service_account"},
                "tool": {"name": "ping"},
                "arguments": {},
                "context": {"environment": "production"},
            },
        },
        "role-admin-allow": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "role-admin-allow",
                    "name": "Role admin allow fixture",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-admin",
                            "name": "Allow admin role",
                            "priority": 200,
                            "match": {
                                "roles": ["admin"],
                                "intents": ["infra.delete.resource"],
                            },
                            "verdict": "ALLOW",
                            "reason": "Admin role permitted for destructive actions",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREROLEADMINALW01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {
                    "id": "admin-user",
                    "type": "user",
                    "roles": ["admin"],
                },
                "tool": {"name": "delete_resource"},
                "arguments": {"resource_id": "vol-9"},
                "context": {"environment": "production"},
            },
        },
        "challenge-infra-prod-no-ticket": {
            "policy-ref.yaml": change_policy_ref,
            "request.json": {
                "id": "01JFIXTURECHALINFRAPRD01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "create_resource"},
                "arguments": {"type": "vm", "name": "web-1"},
                "context": {"environment": "production"},
            },
        },
        # Additional valuable scenarios
        "block-bearer-token": {
            "policy-ref.yaml": baseline_policy_ref,
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"http_request": "network.request.http"},
                "patterns": [
                    {
                        "name": "bearer_token",
                        "match": {
                            "any_arg_regex": "(?i)bearer\\s+[a-zA-Z0-9._-]{20,}"
                        },
                        "intent": "security.secret_exposure",
                        "confidence": 0.97,
                    },
                ],
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKBEARER01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "http_request"},
                "arguments": {
                    "url": "https://api.example.com/data",
                    "headers": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload",
                },
                "context": {"environment": "staging"},
            },
        },
        "block-password-in-args": {
            "policy-ref.yaml": baseline_policy_ref,
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"write_file": "code.write.repo"},
                "patterns": [
                    {
                        "name": "password_literal",
                        "match": {"any_arg_regex": "(?i)password\\s*[:=]\\s*\\S+"},
                        "intent": "security.secret_exposure",
                        "confidence": 0.96,
                    },
                ],
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKPASSWORD01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "write_file"},
                "arguments": {
                    "path": "/tmp/config.env",
                    "content": "db_password=supersecret123",
                },
                "context": {"environment": "development"},
            },
        },
        "challenge-defer-timeout": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "challenge-defer-timeout",
                    "name": "Challenge defer on timeout",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "challenge-defer-on-timeout",
                            "name": "Challenge with defer timeout",
                            "priority": 200,
                            "match": {"intents": ["infra.delete.resource"]},
                            "verdict": "CHALLENGE",
                            "reason": "Delete requires timed approval",
                            "challenge": {
                                "channel": "stdout",
                                "timeoutSeconds": 300,
                                "onTimeout": "DEFER",
                            },
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTURECHALDEFERTO01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "delete_resource"},
                "arguments": {"resource_id": "bucket-1"},
                "context": {"environment": "staging"},
            },
        },
        "allow-read-internal": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "allow-read-internal",
                    "name": "Allow internal reads",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-internal-read",
                            "name": "Allow internal data reads",
                            "priority": 100,
                            "match": {"intents": ["data.read.internal"]},
                            "verdict": "ALLOW",
                            "reason": "Internal reads are permitted",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"read_internal_report": "data.read.internal"},
            },
            "request.json": {
                "id": "01JFIXTUREALLOWREADINT01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "read_internal_report"},
                "arguments": {"report_id": "Q1-sales"},
                "context": {"environment": "production"},
            },
        },
        "block-impersonate": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "block-impersonate",
                    "name": "Block impersonation",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "block-impersonate",
                            "name": "Block impersonation",
                            "priority": 250,
                            "match": {"intents": ["identity.auth.impersonate"]},
                            "verdict": "BLOCK",
                            "reason": "Impersonation is not permitted",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"impersonate_user": "identity.auth.impersonate"},
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKIMPERSON01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "impersonate_user"},
                "arguments": {"user_id": "ceo"},
                "context": {"environment": "production"},
            },
        },
        "block-permission-grant": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "block-permission-grant",
                    "name": "Block permission grants",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "block-permission-grant",
                            "name": "Block permission grant",
                            "priority": 250,
                            "match": {"intents": ["identity.permission.grant"]},
                            "verdict": "BLOCK",
                            "reason": "Permission grants require human approval",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"grant_role": "identity.permission.grant"},
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKPERMGRNT01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "grant_role"},
                "arguments": {"role": "admin", "user_id": "contractor-1"},
                "context": {"environment": "production"},
            },
        },
        "block-transfer-funds": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "block-transfer-funds",
                    "name": "Explicit block transfer funds",
                    "defaultVerdict": "ALLOW",
                    "rules": [
                        {
                            "id": "block-transfer-funds",
                            "name": "Block fund transfers",
                            "priority": 300,
                            "match": {"intents": ["finance.transfer.create"]},
                            "verdict": "BLOCK",
                            "reason": "Fund transfers are blocked by policy",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKXFERFUND01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "transfer_funds"},
                "arguments": {"amount": 5000, "to_account": "vendor-42"},
                "context": {"environment": "production"},
            },
        },
        "allow-metrics-tool": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "allow-metrics-tool",
                    "name": "Allow metrics tools",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-metrics",
                            "name": "Allow metrics emission",
                            "priority": 100,
                            "match": {
                                "tools": ["emit_metrics", "record_metric"],
                                "intents": ["network.request.health"],
                            },
                            "verdict": "ALLOW",
                            "reason": "Metrics tools are always allowed",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {
                    "emit_metrics": "network.request.health",
                    "record_metric": "network.request.health",
                },
            },
            "request.json": {
                "id": "01JFIXTUREALLOWMETRICS01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "emit_metrics"},
                "arguments": {"name": "requests.total", "value": 1},
                "context": {"environment": "production"},
            },
        },
        "block-sql-delete": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "block-sql-delete",
                    "name": "Block SQL delete statements",
                    "defaultVerdict": "ALLOW",
                    "rules": [
                        {
                            "id": "block-sql-delete",
                            "name": "Block SQL delete",
                            "priority": 300,
                            "match": {"intents": ["data.delete.record"]},
                            "verdict": "BLOCK",
                            "reason": "SQL DELETE statements are blocked",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"execute_sql": "data.query.sql"},
                "patterns": [
                    {
                        "name": "sql_delete",
                        "match": {"arg_regex:query": "(?i)\\bDELETE\\b"},
                        "intent": "data.delete.record",
                        "confidence": 0.92,
                    },
                ],
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKSQLDEL01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "execute_sql"},
                "arguments": {"query": "DELETE FROM users WHERE inactive = true"},
                "context": {"environment": "production"},
            },
        },
        "expression-complex-and-or": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "expression-complex-and-or",
                    "name": "Complex AND/OR expression",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "block-complex-expr",
                            "name": "Block complex expression match",
                            "priority": 250,
                            "match": {
                                "intents": ["comms.send.email"],
                                "expression": '(env == "production" || env == "staging") && args.to contains "@external.com"',
                            },
                            "verdict": "BLOCK",
                            "reason": "External email blocked in prod or staging",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREEXPRCOMPLEX01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "send_email"},
                "arguments": {
                    "to": "partner@external.com",
                    "subject": "Update",
                    "body": "Hello",
                },
                "context": {"environment": "staging"},
            },
        },
        "tags-multi-key-match": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "tags-multi-key-match",
                    "name": "Multi-key tag match",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "challenge-sensitive-export",
                            "name": "Challenge sensitive export",
                            "priority": 220,
                            "match": {
                                "intents": ["data.exfiltrate"],
                                "tags": {
                                    "data_class": ["pii", "financial"],
                                    "export_scope": ["external"],
                                },
                            },
                            "verdict": "CHALLENGE",
                            "reason": "Sensitive external export requires approval",
                            "challenge": {
                                "channel": "stdout",
                                "timeoutSeconds": 3600,
                                "onTimeout": "BLOCK",
                            },
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"export_data": "data.exfiltrate"},
            },
            "request.json": {
                "id": "01JFIXTURETAGSMULTIKEY01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "export_data"},
                "arguments": {"destination": "s3://external/partner"},
                "context": {
                    "environment": "production",
                    "tags": {
                        "data_class": "pii",
                        "export_scope": "external",
                    },
                },
            },
        },
        "namespace-tool-match": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "namespace-tool-match",
                    "name": "Namespace expression match",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-billing-namespace",
                            "name": "Allow billing namespace tools",
                            "priority": 150,
                            "match": {
                                "expression": 'tool.namespace == "billing"',
                            },
                            "verdict": "ALLOW",
                            "reason": "Billing namespace tools are allowed",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"invoice_sync": "finance.charge.create"},
            },
            "request.json": {
                "id": "01JFIXTURENAMESPACETOOL01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "invoice_sync", "namespace": "billing"},
                "arguments": {"customer_id": "cust-1"},
                "context": {"environment": "production"},
            },
        },
        "alternatives-intent-match": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "alternatives-intent-match",
                    "name": "Alternative intent match",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "block-exfil-alt",
                            "name": "Block exfil via alternative intent",
                            "priority": 300,
                            "match": {"intents": ["data.exfiltrate"]},
                            "verdict": "BLOCK",
                            "reason": "Possible data exfiltration",
                        },
                    ],
                },
            },
            "classifications-ref.json": [
                {
                    "intent": "comms.send.email",
                    "confidence": 0.7,
                    "alternatives": [
                        {"intent": "data.exfiltrate", "confidence": 0.55}
                    ],
                    "classifier": "deterministic:v1",
                }
            ],
            "request.json": {
                "id": "01JFIXTUREALTERNATIVES01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "send_email"},
                "arguments": {
                    "to": "a@b.com",
                    "subject": "data",
                    "body": "export",
                },
                "context": {"environment": "staging"},
            },
        },
        "challenge-webhook-channel": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "challenge-webhook-channel",
                    "name": "Webhook challenge channel",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "challenge-webhook",
                            "name": "Webhook challenge",
                            "priority": 200,
                            "match": {"intents": ["infra.provision.resource"]},
                            "verdict": "CHALLENGE",
                            "reason": "Provisioning requires webhook approval",
                            "challenge": {
                                "channel": "webhook",
                                "timeoutSeconds": 1800,
                                "onTimeout": "BLOCK",
                            },
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTURECHALWEBHOOK01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "create_resource"},
                "arguments": {"type": "database"},
                "context": {"environment": "staging"},
            },
        },
        "block-prod-write-pii": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "block-prod-write-pii",
                    "name": "Block PII writes in production",
                    "defaultVerdict": "ALLOW",
                    "rules": [
                        {
                            "id": "block-prod-write-pii",
                            "name": "Block prod PII writes",
                            "priority": 280,
                            "match": {
                                "intents": ["data.write.record"],
                                "environments": ["production"],
                                "tags": {"data_class": ["pii"]},
                            },
                            "verdict": "BLOCK",
                            "reason": "PII writes are blocked in production",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"write_record": "data.write.record"},
            },
            "request.json": {
                "id": "01JFIXTUREBLOCKPRODPII01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "write_record"},
                "arguments": {"table": "customers", "email": "user@example.com"},
                "context": {
                    "environment": "production",
                    "tags": {"data_class": "pii"},
                },
            },
        },
        "allow-dev-mutate": {
            "policy-ref.yaml": {
                "rules": "../../../packs/baseline-deny/rules.yaml",
                "policy": {
                    "version": 1,
                    "id": "allow-dev-mutate",
                    "name": "Allow dev mutations",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-dev-mutate",
                            "name": "Allow dev environment mutations",
                            "priority": 150,
                            "match": {
                                "environments": ["development"],
                                "intents": ["infra.mutate.resource"],
                            },
                            "verdict": "ALLOW",
                            "reason": "Development mutations are allowed",
                        },
                    ],
                },
            },
            "request.json": {
                "id": "01JFIXTUREALLOWDEVMUT01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "update_resource"},
                "arguments": {"resource_id": "dev-svc-1"},
                "context": {"environment": "development"},
            },
        },
        "min-confidence-blocks-weak": {
            "policy-ref.yaml": {
                "rules": "rules-ref.yaml",
                "policy": {
                    "version": 1,
                    "id": "min-confidence-blocks-weak",
                    "name": "Min confidence blocks weak classification",
                    "defaultVerdict": "BLOCK",
                    "rules": [
                        {
                            "id": "allow-high-confidence-email",
                            "name": "Allow high-confidence email",
                            "priority": 100,
                            "match": {
                                "intents": ["comms.send.email"],
                                "minConfidence": 0.95,
                            },
                            "verdict": "ALLOW",
                            "reason": "High-confidence email allowed",
                        },
                    ],
                },
            },
            "rules-ref.yaml": {
                "version": 1,
                "tool_map": {"send_email": "comms.send.email"},
                "patterns": [
                    {
                        "name": "weak_email_signal",
                        "match": {"any_arg_regex": "(?i)maybe email"},
                        "intent": "comms.send.email",
                        "confidence": 0.7,
                    },
                ],
            },
            "request.json": {
                "id": "01JFIXTUREMINCONFWEAK01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "send_email"},
                "arguments": {"body": "maybe email this later"},
                "context": {"environment": "staging"},
            },
        },
        "block-high-severity-shell": {
            "policy-ref.yaml": baseline_policy_ref,
            "request.json": {
                "id": "01JFIXTUREBLOCKSHELLHI01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "run_shell"},
                "arguments": {"command": "rm -rf /tmp/cache"},
                "context": {"environment": "production"},
            },
        },
        "allow-pii-guard-health": {
            "policy-ref.yaml": pii_policy_ref,
            "request.json": {
                "id": "01JFIXTUREPIIGUARDHLTH01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "health_check"},
                "arguments": {},
                "context": {"environment": "production"},
            },
        },
        "block-change-window-no-ticket": {
            "policy-ref.yaml": change_policy_ref,
            "request.json": {
                "id": "01JFIXTURECHGWNDNOTKT01",
                "shieldId": "local",
                "timestamp": "2026-07-11T12:00:00.000Z",
                "caller": {"id": "agent-1", "type": "agent"},
                "tool": {"name": "update_resource"},
                "arguments": {"resource_id": "lb-1"},
                "context": {"environment": "production"},
            },
        },
    }

    for scenario, files in fixtures.items():
        ensure_fixture(scenario, files)
        expected_path = GOLDEN_ROOT / scenario / "expected.json"
        if not expected_path.exists():
            expected = evaluate_scenario(scenario)
            expected_path.write_text(
                json.dumps(expected, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"created expected for {scenario}")


if __name__ == "__main__":
    main()
