# Intent Catalog

Built-in intent taxonomy for LexShield v0.1. See [SPEC §10](../SPEC.md#10-intent-taxonomy) and [Appendix B](../SPEC.md#appendix-b--built-in-intent-catalog-v01).

## Overview

## Classification output contract

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

## Custom intents (`custom.*`)

## Deterministic tool map

## Extending with `taxonomy.yaml`
