# Policy Authoring

Guide to writing LexShield YAML policies.

## Overview

A LexShield **policy** is a versioned YAML file that maps classified tool-call intents (plus tool name, caller, environment, tags, and expressions) to verdicts: `ALLOW`, `BLOCK`, `CHALLENGE`, or `DEFER`.

Policies are **local-first**: they live in your repository, validate in CI with `lexshield check`, and load at runtime from `lexshield.yaml`.

## Policy file shape

```yaml
version: 1
id: my-policy
name: Production default deny
description: Optional human-readable summary
defaultVerdict: BLOCK
rules:
  - id: allow-health
    name: Allow health checks
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"
```

| Field | Required | Description |
|-------|----------|-------------|
| `version` | yes | Policy schema version (`1` in v0.1) |
| `id` | yes | Stable identifier for traces and tooling |
| `name` | yes | Display name |
| `defaultVerdict` | yes | Verdict when no rule matches (`BLOCK` recommended) |
| `rules` | yes | Ordered rule list (priority resolves ties) |

## Default verdict

`defaultVerdict` applies when:

1. A rule matches on intent/tool/context but you rely on the default for unlisted cases, or
2. No rule matches and the primary intent is **not** `unknown.unclassified`.

If the classifier returns `unknown.unclassified` and no rule matches, the engine **always blocks** regardless of `defaultVerdict` (fail-closed for unclassified calls).

`lexshield check --strict` warns when `defaultVerdict: ALLOW` is set.

## Rules

Each rule has:

| Field | Description |
|-------|-------------|
| `id` | Unique stable id (referenced in traces and errors) |
| `priority` | Higher number wins when multiple rules match |
| `enabled` | Optional; default `true` |
| `match` | Dimensions to match (see below) |
| `verdict` | `ALLOW`, `BLOCK`, `CHALLENGE`, or `DEFER` |
| `reason` | Human-readable explanation in verdicts and errors |
| `challenge` | Required for `CHALLENGE`/`DEFER` with timeout config |

### Priority and tie-breaking

Rules are sorted by **descending** `priority`. When priorities tie, rule `id` is compared lexicographically (lower id wins for BLOCK-type outcomes in tests).

Example: `block-secret-exposure` at priority 300 beats `challenge-delete-prod` at 200 when both match.

## Match dimensions

```yaml
match:
  intents: ["infra.delete.resource"]
  tools: ["delete_resource", "send_*"]
  environments: ["production"]
  callers: ["ci-bot"]
  roles: ["admin"]
  tags:
    data_class: ["pii"]
  minConfidence: 0.9
  expression: 'tags.change_ticket != ""'
```

| Dimension | Behavior |
|-----------|----------|
| `intents` | Match if primary or alternative classification intent is listed |
| `tools` | Glob on tool name (`*` only; `fnmatch` semantics) |
| `environments` | Match `context.environment` |
| `callers` | Match `caller.id` |
| `roles` | Match any role on `caller.roles` |
| `tags` | All tag keys must match one of the listed values |
| `minConfidence` | Primary classification confidence must be ≥ threshold |
| `expression` | Boolean expression over bindings (see below) |

All specified dimensions must match (logical AND).

## Expressions

Expressions are safe, non-Turing-complete boolean formulas evaluated at match time.

**Bindings:** `intent`, `confidence`, `tool.name`, `caller.id`, `caller.type`, `env`, `tags.<key>`, `args.<key>`.

**Operators:** `==`, `!=`, `&&`, `||`, `!`, comparisons, `in`, and calls `startsWith()`, `contains()`, `matches()`.

Examples:

```yaml
# Require change ticket tag in production
expression: 'tags.change_ticket != ""'

# Block HTTP to non-allowlisted hosts
expression: '!(args.url startsWith "https://api.mycompany.com/")'
```

## Challenge configuration

For `CHALLENGE` or `DEFER` verdicts:

```yaml
challenge:
  channel: stdout
  timeoutSeconds: 3600
  onTimeout: BLOCK
```

| Field | Description |
|-------|-------------|
| `channel` | Notification channel (`stdout` in v0.1; `webhook`/`slack` reserved) |
| `timeoutSeconds` | How long to wait for human approval |
| `onTimeout` | `BLOCK` (recommended) or `ALLOW` if approval never arrives |

When a challenge rule wins, LexShield creates a record under `.lexshield/challenges/` and returns `challengeId` on the verdict.

## Policy versioning

- Local policies use the `version` field and git history as source of truth.
- `lexshield check` validates structure before merge.
- Verdicts include `policyVersion` from the loaded file.

## Validation with `lexshield check`

```bash
# Validate project config + policy + rules
lexshield check

# Validate a pack directly (CI)
lexshield check \
  --policy packs/baseline-deny/policy.yaml \
  --rules packs/baseline-deny/rules.yaml \
  --strict
```

`--strict` fails on warnings (e.g. missing rules file, `defaultVerdict: ALLOW`).

## Policy packs

Shipped packs under `packs/`:

| Pack | Purpose |
|------|---------|
| `baseline-deny` | Default deny; allow health; challenge prod deletes; block secrets |
| `pii-guard` | Challenge PII egress; block non-allowlisted HTTP |
| `change-window` | Require `change_ticket` tag for prod infra changes |

```bash
lexshield packs list
lexshield packs apply baseline-deny
lexshield init --pack pii-guard
```

## Examples

**Allow health only (baseline):**

```yaml
- id: allow-health
  priority: 100
  match:
    tools: ["health_check"]
    intents: ["network.request.health"]
  verdict: ALLOW
  reason: "Health checks are always allowed"
```

**Challenge destructive prod actions:**

```yaml
- id: challenge-delete-prod
  priority: 200
  match:
    environments: ["production"]
    intents: ["infra.delete.resource"]
  verdict: CHALLENGE
  reason: "Destructive action in production requires approval"
  challenge:
    channel: stdout
    timeoutSeconds: 3600
    onTimeout: BLOCK
```

**Block secret patterns (pairs with `rules.yaml` patterns):**

```yaml
- id: block-secret-exposure
  priority: 300
  match:
    intents: ["security.secret_exposure"]
  verdict: BLOCK
  reason: "Possible secret exposure in tool arguments"
```

See [packs/baseline-deny/policy.yaml](../packs/baseline-deny/policy.yaml) and [fixtures/golden/](../fixtures/golden/) for regression scenarios.
