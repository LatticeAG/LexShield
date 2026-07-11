"""Built-in intent taxonomy and severity ranks (SPEC Appendix B)."""

from __future__ import annotations

# Frozen 24-intent catalog for v0.1. Severity 1–100 (higher = more severe).
INTENT_SEVERITY: dict[str, int] = {
    "network.request.health": 5,
    "data.read.public": 10,
    "data.read.internal": 25,
    "comms.read.inbox": 35,
    "data.query.sql": 40,
    "comms.send.slack": 40,
    "data.write.record": 45,
    "comms.send.email": 50,
    "unknown.unclassified": 50,
    "code.write.repo": 50,
    "network.request.http": 55,
    "data.read.pii": 60,
    "infra.provision.resource": 60,
    "infra.mutate.resource": 65,
    "comms.send.external": 70,
    "data.delete.record": 75,
    "finance.charge.create": 80,
    "infra.delete.resource": 85,
    "identity.permission.grant": 85,
    "code.execute.shell": 88,
    "finance.transfer.create": 90,
    "identity.auth.impersonate": 90,
    "data.exfiltrate": 95,
    "security.secret_exposure": 98,
}

BUILTIN_INTENTS: frozenset[str] = frozenset(INTENT_SEVERITY.keys())


def intent_severity(intent: str) -> int:
    """Return severity rank for an intent (0 for unknown custom intents)."""
    return INTENT_SEVERITY.get(intent, 0)
