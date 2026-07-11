# Security Model

Threat model, trust boundaries, and honest limits. See [SPEC §23](../SPEC.md#23-security--threat-model).

## Trust boundaries

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Agent / LLM │────▶│ LexShield engine │────▶│ Tool upstreams  │
│  (untrusted)│     │ (policy + classify)│   │ (your services) │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │
                    ┌──────┴──────┐
                    │ Policy YAML │  ← trusted (git, code review)
                    │ rules.yaml  │
                    └─────────────┘
```

| Component | Trust level |
|-----------|-------------|
| Policy + rules in git | **Trusted** — reviewed like application code |
| LexShield engine (OSS) | **Trusted** — MIT source; verify checksums/releases |
| Agent prompts & tool args | **Untrusted** — may be adversarial or injected |
| LLM classifier (optional) | **Semi-trusted** — probabilistic; not required for v0.1 deterministic path |
| Tool upstreams | **Trusted** — LexShield does not replace network/auth controls |

LexShield does **not** store tool credentials or execute tools unless you wire execution/proxy yourself.

## Threats and mitigations

| Threat | Mitigation |
|--------|------------|
| Prompt injection causing dangerous tool use | Classify intent + default-deny policy; block/challenge before execution |
| Secret exfil via email/HTTP/file tools | Deterministic patterns (`AKIA…`, `sk-…`) → `security.secret_exposure` |
| Destructive prod actions | Environment + intent rules; `CHALLENGE` with human approval |
| Policy bypass by renaming tools | Match on **intent**, not only tool name; unclassified → block |
| Leaking policy internals to agents | Configurable exposure of `matchedRuleId` in errors (dev vs prod) |
| Local API abuse | Bind `127.0.0.1`; optional `LEXSHIELD_LOCAL_TOKEN` |

## Security guarantees (honest)

LexShield **reduces** risk from misclassified or malicious agent tool calls. It does **not**:

- Eliminate prompt injection or adversarial ML
- Replace IAM, network segmentation, or secrets management
- Guarantee correct LLM classification when enabled
- Attest to agent *truthfulness* — only to policy conformance at interception time

Document this clearly to security reviewers and customers.

## Redaction

Before classification and trace writes, arguments may be redacted (emails, known secret patterns) per config. Traces use redacted copies; policy matching uses the request as provided unless redaction is applied in the pipeline.

## Fail-closed defaults

| Condition | Default behavior |
|-----------|------------------|
| `unknown.unclassified` intent, no rule match | **BLOCK** |
| Classifier error (configurable) | `fail_on_classifier_error: BLOCK` |
| Challenge timeout | `onTimeout: BLOCK` (recommended) |
| Missing policy rule | `defaultVerdict: BLOCK` (recommended) |

`lexshield check --strict` warns on unsafe defaults.

## Local API hardening

- Default bind: `127.0.0.1:8787` (not `0.0.0.0`)
- Optional bearer token via `LEXSHIELD_LOCAL_TOKEN`
- No anonymous remote admin in v0.1

## Proxy upstream allowlist

Proxy mode forwards only to **explicit** upstream URLs configured per tool in `lexshield.yaml`. LexShield is not a generic open HTTP proxy.

## Agent-facing errors

Blocked/challenged calls return structured errors with `reason` and optionally `matchedRuleId`. Avoid echoing full arguments or policy YAML back to the model in production.

## Limitations

- Deterministic classifier covers known tool maps and regex patterns — novel tools need map entries or LLM
- Challenge resume requires local store coordination (`await_challenge` or manual re-eval)
- No built-in SIEM — use file/HTTP trace sinks or your own pipeline

## Reporting issues

Report vulnerabilities responsibly via your organization's security channel or GitHub Security Advisories on the [LexShield repository](https://github.com/latticeag/lexshield).

Do not include live secrets in issue reports.
