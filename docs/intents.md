# Intent Catalog

Built-in intent taxonomy for LexShield v0.1. See [SPEC §10](../SPEC.md#10-intent-taxonomy) and [Appendix B](../SPEC.md#appendix-b--built-in-intent-catalog-v01).

## Overview

An **intent** describes *why* a tool is being called — not just its name. LexShield classifies each `ToolCallRequest` into one or more intents, then policy rules match on those intents.

v0.1 ships a fixed catalog. Custom intents use the `custom.*` namespace and optional `taxonomy.yaml` extensions.

## Classification output contract

Each classification includes:

| Field | Description |
|-------|-------------|
| `intent` | Catalog intent id (e.g. `comms.send.email`) |
| `confidence` | 0.0–1.0 |
| `classifier` | Source (`deterministic:v1`, `llm:...`) |
| `alternatives` | Other candidate intents |

The **primary** intent (highest severity, then confidence) drives default policy matching. All classifications are preserved on the verdict for audit.

## Built-in intents (v0.1)

| Intent | Severity | Description |
|--------|----------|-------------|
| `network.request.health` | 5 | Health/ping |
| `data.read.public` | 10 | Read non-sensitive |
| `data.read.internal` | 25 | Read internal business data |
| `data.read.pii` | 60 | Read PII |
| `data.query.sql` | 40 | SQL read/query |
| `data.write.record` | 45 | Create/update records |
| `data.delete.record` | 75 | Delete data |
| `data.exfiltrate` | 95 | Suspected exfiltration |
| `comms.read.inbox` | 35 | Read messages/inbox |
| `comms.send.email` | 50 | Send email |
| `comms.send.slack` | 40 | Send Slack/chat |
| `comms.send.external` | 70 | Message external party |
| `network.request.http` | 55 | Arbitrary HTTP |
| `infra.provision.resource` | 60 | Create infra |
| `infra.mutate.resource` | 65 | Change infra |
| `infra.delete.resource` | 85 | Destroy infra |
| `finance.charge.create` | 80 | Create charge/payment |
| `finance.transfer.create` | 90 | Move money |
| `identity.permission.grant` | 85 | Grant access |
| `identity.auth.impersonate` | 90 | Impersonation |
| `code.execute.shell` | 88 | Shell/code exec |
| `code.write.repo` | 50 | Write code/files |
| `security.secret_exposure` | 98 | Secrets in args/egress |
| `unknown.unclassified` | 50 | Fallback |

## Severity and conflict resolution

When multiple classifications exist (e.g. deterministic + LLM), LexShield picks the primary intent by:

1. Highest **severity** (table above)
2. Higher **confidence** on tie
3. Deterministic classifier wins over LLM on further tie

Policy authors can still match on any intent in `classifications[]` via `match.intents`.

## Custom intents (`custom.*`)

Reserve `custom.<your_domain>.<action>` for org-specific intents not in the built-in catalog. Reference them in policy rules the same way as built-in intents.

LLM classifiers may propose custom intents when enabled; deterministic v0.1 uses the catalog and `rules.yaml` only.

## Deterministic tool map

`rules.yaml` maps tool names to intents without an LLM:

```yaml
tool_map:
  health_check: network.request.health
  send_email: comms.send.email
  delete_resource: infra.delete.resource
```

Tool-map hits use confidence **0.70**. Regex patterns in the same file can override with higher confidence (e.g. **0.98** for AWS keys → `security.secret_exposure`).

## Extending with `taxonomy.yaml`

Optional `taxonomy.yaml` can declare additional intents and severity overrides for your deployment. `lexshield check` validates references from policy rules.

For v0.1 OSS, most teams start with the built-in catalog plus `rules.yaml` `tool_map` and `patterns` — no taxonomy file required.

## Related

- [Policy authoring](./policy.md) — matching on intents
- [Python SDK](./sdk-python.md) — `shield.evaluate` returns classifications
- [Golden fixtures](../fixtures/golden/) — intent + verdict regression tests
