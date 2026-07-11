# LexShield Policy Packs

Shipped policy packs for v0.1. Each pack is a directory with:

| File | Purpose |
|------|---------|
| `policy.yaml` | Allow/block/challenge rules (SPEC Appendix A) |
| `rules.yaml` | Deterministic classifier: `tool_map` + `patterns` (Appendix A.4) |

Apply a pack with:

```bash
lexshield packs apply baseline-deny
# or
lexshield init --pack pii-guard
```

## Available packs

### `baseline-deny`

Default-deny posture. Allows health/ping only; challenges destructive actions in production; blocks secret exposure and exfiltration.

**Use when:** Starting from scratch; you want a safe baseline before customizing rules.

### `pii-guard`

Extends baseline with PII egress controls. Challenges email/external comms when `data_class: pii` is tagged; blocks HTTP to hosts outside `https://api.mycompany.com/`.

**Use when:** Agents send email, Slack, or HTTP and you need PII egress guardrails.

### `change-window`

Infra change-window policy. Allows production infra mutate/provision when `change_ticket` tag is present; otherwise challenges prod infra changes.

**Use when:** Production infrastructure changes must be tied to an approved change ticket.

## Deterministic classifier

`pii-guard` and `change-window` symlink `rules.yaml` to `baseline-deny/rules.yaml` (shared tool map and secret patterns). Customize per pack by replacing the symlink with a copy.

## Normative source

Full YAML is defined in [SPEC.md Appendix A](../SPEC.md#appendix-a--example-policy-packs).
