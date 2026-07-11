# LexShield — Product & Engineering Specification

> **Status**: Planning (v0.2 — expanded)  
> **Owner**: LatticeAG  
> **License (OSS)**: MIT  
> **SaaS**: LexShield Cloud (invite-only), hosted by LatticeAG  
> **This document is the source of truth for build decisions until replaced by ADRs.**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem & User Value](#2-problem--user-value)
3. [Personas, Jobs, and Buyer Journey](#3-personas-jobs-and-buyer-journey)
4. [Product Positioning & Principles](#4-product-positioning--principles)
5. [Competitive Landscape](#5-competitive-landscape)
6. [Core Concepts & Glossary](#6-core-concepts--glossary)
7. [Success Metrics](#7-success-metrics)
8. [Scope: Goals, Non-Goals, and Phasing](#8-scope-goals-non-goals-and-phasing)
9. [Intent Taxonomy](#9-intent-taxonomy)
10. [Classifier Architecture](#10-classifier-architecture)
11. [Policy Language & Engine](#11-policy-language--engine)
12. [Verdicts, Challenges & Human-in-the-Loop](#12-verdicts-challenges--human-in-the-loop)
13. [Execution Interception & Integration Modes](#13-execution-interception--integration-modes)
14. [SDKs (Python & TypeScript)](#14-sdks-python--typescript)
15. [CLI Surface](#15-cli-surface)
16. [Local API & Proxy](#16-local-api--proxy)
17. [LexShield Cloud](#17-lexshield-cloud)
18. [Data Model](#18-data-model)
19. [Configuration Schema](#19-configuration-schema)
20. [Architecture & Request Pipeline](#20-architecture--request-pipeline)
21. [Performance, Caching & Reliability](#21-performance-caching--reliability)
22. [Security & Threat Model](#22-security--threat-model)
23. [Privacy, Compliance & Data Handling](#23-privacy-compliance--data-handling)
24. [Observability & Audit](#24-observability--audit)
25. [Error Handling & Failure Modes](#25-error-handling--failure-modes)
26. [Testing Strategy](#26-testing-strategy)
27. [Repository & Monorepo Layout](#27-repository--monorepo-layout)
28. [Tech Stack Recommendations](#28-tech-stack-recommendations)
29. [Developer Experience & Documentation](#29-developer-experience--documentation)
30. [Dashboard UX (Cloud)](#30-dashboard-ux-cloud)
31. [Pricing, Packaging & Go-to-Market](#31-pricing-packaging--go-to-market)
32. [MVP Milestones (6-Day Build)](#32-mvp-milestones-6-day-build)
33. [Post-MVP Roadmap](#33-post-mvp-roadmap)
34. [Open Questions (with Recommendations)](#34-open-questions-with-recommendations)
35. [Decision Log](#35-decision-log)
36. [Appendix A — Example Policy Packs](#appendix-a--example-policy-packs)
37. [Appendix B — Built-in Intent Catalog (MVP)](#appendix-b--built-in-intent-catalog-mvp)
38. [Appendix C — Trace Event Schema](#appendix-c--trace-event-schema)

---

## 1. Executive Summary

**LexShield** is an **agent intent router and policy firewall**. It sits between an AI agent and its tool fleet, classifies the *intent* behind each tool call, and enforces allow/block/challenge policy **before** execution.

Existing auth layers (RBAC, OAuth scopes, API keys) authorize *who* can call a tool. They do not understand *why* an agent is calling it in natural-language context. LexShield closes that gap.

**Recommendation — product shape (confident):**

| Layer | Form | Why |
|-------|------|-----|
| Core engine | Open-source library + CLI (MIT) | Trust, adoption, auditability, community |
| SDKs | Python first, TypeScript second | Matches agent ecosystem gravity |
| Hosted control plane | Invite-only SaaS (LexShield Cloud) | Policy distribution, retention, multi-team, alerts |
| Hosting | Cloudflare Workers + Durable Objects + D1/R2 | Edge latency, low ops, fits LatticeAG stack |

**One-line positioning:**  
*"The policy firewall for agent tool calls — open source for transparency, cloud for control."*

---

## 2. Problem & User Value

### 2.1 Problem

As agents gain tool-calling, every invocation is a security, compliance, and cost event. A single misclassified or malicious prompt can cause an agent to:

- Exfiltrate PII or secrets via “innocent” tools (`send_email`, `http_request`, `write_file`)
- Destroy resources (`delete_*`, `drop_table`, `revoke_*`)
- Spend money (`create_charge`, `provision_gpu`, `buy_*`)
- Violate customer or regulatory policy (data residency, least privilege, change windows)

Human-centric auth does not encode agent *intent*. Prompt injection and confused-deputy patterns make static scopes insufficient.

### 2.2 Value Proposition

| Stakeholder | Value |
|-------------|-------|
| Security / platform eng | Single control plane: what agents may do, why, and what happens on violation |
| Agent product teams | Ship tools to production with auditable guardrails |
| Compliance / GRC | Immutable traces tying natural-language context → intent → verdict → outcome |
| Developers | Local-first DX: YAML policies, CLI, SDKs, no SaaS required to evaluate |

### 2.3 Core Insight (recommendation)

**Authorize the intent of the tool call, not only the tool name.**  
Tool names are necessary but not sufficient (`http_request` can mean health-check or data exfil). Classification + policy over intent + arguments + context is the product.

---

## 3. Personas, Jobs, and Buyer Journey

### 3.1 Personas

| Persona | Role | Primary job | Pain |
|---------|------|-------------|------|
| **Ava** — Platform/Security Eng | Builds agent runtime | Prevent catastrophic tool use | No intent-aware controls; logs after the fact |
| **Dev** — Agent Framework Builder | Ships LangChain / custom agents | Need pluggable guardrails | Glue code; inconsistent policy |
| **Priya** — Vertical AI Founder | Customer-facing agents | Prove policy to enterprise buyers | Security questionnaires fail without audit trail |
| **Sam** — SRE / On-call | Owns production agents | Alert on policy spikes | Silent blocks or noisy false positives |

**Primary buyer**: Ava (platform/security).  
**Primary user (day-to-day)**: Dev + Ava.  
**Economic buyer (enterprise)**: CISO / Head of Platform.

### 3.2 Jobs To Be Done

1. Before production: “Define what this agent is allowed to do in YAML and test it in CI.”
2. At runtime: “Block or challenge dangerous tool calls with a clear reason.”
3. After incidents: “Show the exact request, classification, matched rule, and outcome.”
4. At scale: “Distribute versioned policies to many agents and alert on anomalies.”

### 3.3 Adoption Path (recommendation)

```
Local CLI eval → SDK wrap in one tool → Policy in repo + CI check
  → Proxy for multi-language agents → Cloud for policy publish + traces
```

Do **not** require Cloud signup for first value. Local-first is non-negotiable for OSS trust.

---

## 4. Product Positioning & Principles

### 4.1 Positioning

- **Category**: Agent policy firewall / intent authorization layer  
- **Not**: API gateway, WAF, secrets manager, agent framework, LLM firewall for prompts alone  
- **Adjacent but distinct**: Prompt guardrails (input filtering) and output filters — LexShield focuses on **tool-call authorization**

### 4.2 Product Principles (recommendations)

1. **Default-deny** — unknown intents and unmatched rules block unless policy opts into allow-by-default (discouraged; warn loudly).
2. **Local-first** — full evaluation works offline with file policies.
3. **Explainable verdicts** — every decision includes matched rule id, reason string, and classifications.
4. **Fast path first** — deterministic classifiers before LLM; never require LLM for ALLOW of known-safe patterns if policy author opts in.
5. **Fail closed on uncertainty (configurable)** — when classifiers disagree or confidence is low, default to `BLOCK` or `CHALLENGE`, not `ALLOW`.
6. **OSS is the product; Cloud is the control plane** — engine parity: Cloud must not be required for correctness.
7. **No credential custody** — LexShield does not store tool secrets.
8. **Policy as code** — policies live in git; Cloud versions them; CI validates them.
9. **Honest limits** — document that classification is probabilistic; LexShield reduces risk, does not eliminate adversarial risk.

### 4.3 Brand / Naming

| Name | Use |
|------|-----|
| LexShield | Product, CLI (`lexshield`), Python package `lexshield` |
| `@latticeag/lexshield` | TypeScript package |
| LexShield Cloud | Hosted SaaS |
| LatticeAG | Company / publisher |

**Recommendation**: Keep CLI binary name `lexshield` (no hyphens). Config file `lexshield.yaml`. Policy file default `policy.yaml`.

---

## 5. Competitive Landscape

| Approach | Examples | Gap vs LexShield |
|----------|----------|------------------|
| Prompt / content filters | LlamaGuard, OpenAI Moderation | Not tool-call / intent authorization |
| Agent frameworks’ callbacks | LangChain callbacks, custom middleware | Ad hoc; no policy language or audit product |
| API gateways | Kong, Cloudflare API Shield | No NL intent; not agent-context aware |
| Identity / IAM | OAuth scopes, Cedar, OPA | Powerful policy, weak agent-intent signal |
| Emerging agent security | Guardrails.ai, Portkey, custom wrappers | Overlap possible; LexShield differentiates on **intent taxonomy + policy firewall + OSS/Cloud split** |

**Recommendation**: Position against “OPA for agent tool calls” + “intent classification layer,” not against general LLM safety.

**Differentiation bets (confident):**

1. First-class **intent** object in the policy model  
2. Multi-stage classifier pipeline with deterministic primacy  
3. `CHALLENGE` / `DEFER` as first-class verdicts (HITL)  
4. OSS engine with identical evaluation semantics in Cloud  

---

## 6. Core Concepts & Glossary

| Concept | Definition |
|---------|------------|
| **Intent** | High-level goal inferred from a tool-call request (e.g. `read_customer_record`, `exfiltrate_data`, `delete_resource`). |
| **Signal** | Raw classification input: tool name, arguments, history, metadata, prior calls, env tags. |
| **Policy** | Versioned set of rules + default verdict. |
| **Rule** | Match criteria → verdict + reason (+ optional challenge config). |
| **Shield** | Bound instance: policy + classifiers + sinks (+ optional tool forwarders). |
| **Verdict** | `ALLOW` \| `BLOCK` \| `CHALLENGE` \| `DEFER` with reasoning. |
| **Trace** | Immutable record of request → classification → verdict → outcome. |
| **Classifier** | Component that maps signals → ranked intents + confidence. |
| **Sink** | Trace destination (stdout, file, OTLP, HTTP, SaaS). |
| **Caller** | Authenticated identity of the agent/user/service making the call (asserted by the host app). |
| **Challenge** | Human approval gate before execution. |
| **Defer** | Async review path; execution withheld until resolved (or timed out → fail closed). |
| **Policy pack** | Curated starter policies for domains (PII, finance, infra). |
| **Fingerprint** | Stable hash of (tool, normalized args, intent candidates, env) for caching. |

---

## 7. Success Metrics

### 7.1 Product / Business (Cloud + OSS)

| Metric | MVP target | Notes |
|--------|------------|-------|
| Time-to-first-eval | < 5 minutes from `pip install` / `npm i` | Include sample policy |
| OSS weekly evals (telemetry opt-in) | Track after M4 | Anonymous, off by default |
| Cloud waitlist → activated orgs | Conversion tracked | Invite-only |
| False-block rate (customer-reported) | Qualitative in MVP | Instrument later |
| p99 evaluate latency (deterministic path) | < 5 ms local | See perf section |

### 7.2 Engineering Quality

| Metric | Target |
|--------|--------|
| Unit test coverage (core policy engine) | ≥ 90% |
| Policy fixture golden tests | ≥ 50 scenarios in MVP |
| SDK API stability | SemVer; breaking changes only in major |

### 7.3 Security Outcomes (north-star, hard to measure early)

- % of tool calls with a recorded verdict (coverage)
- Block rate on high-severity intents
- Median time-to-approve for `CHALLENGE`

---

## 8. Scope: Goals, Non-Goals, and Phasing

### 8.1 MVP Goals (in-scope)

- YAML/JSON policy engine with rule priority, default-deny, CEL-lite expressions
- Deterministic classifier + LLM classifier (OpenAI-compatible)
- Python SDK (`@shield.guard`, `evaluate`)
- Local HTTP API + proxy execute mode
- CLI: `init`, `check`, `run`, `evaluate`, `traces`
- NDJSON + stdout sinks; OpenTelemetry hooks (basic)
- TypeScript SDK parity for `evaluate` + config load
- Cloud scaffold: orgs, policy CRUD/publish, trace ingest, invite gate
- Built-in intent catalog (~25–40 intents) + 2–3 policy packs

### 8.2 Explicit Non-Goals (MVP)

- Generic API gateway features (LB, primary rate limiting product, request rewrite)
- Being an agent / planner / workflow engine
- Secrets management / vault
- Replacing HITL for high-stakes actions (we formalize it)
- Mobile apps, browser extensions, consumer clients
- Full multi-region active-active (region *selection* can be stubbed)
- Guaranteed prompt-injection immunity
- Training proprietary foundation models
- In-core LangChain/OpenAI Agents adapters (contrib post-MVP; see decisions)

### 8.3 Soft Non-Goals (post-MVP candidates)

- Local embedding models as default
- Full Cedar / Rego interop
- Native WASM edge plugin for third-party gateways
- SIEM connectors beyond OTLP/webhook

---

## 9. Intent Taxonomy

### 9.1 Design Recommendations (confident)

1. **Hierarchical, dot-namespaced intents**: `data.read.pii`, `infra.delete.resource`, `comms.send.external`.
2. **Separate “benign” and “abuse” intents** where useful: `http.fetch` vs `data.exfiltrate` — abuse intents are assigned when signals suggest malice/sensitivity mismatch.
3. **Customer can extend** via `taxonomy.yaml`; built-ins are namespaced `lex.*` or unprefixed public catalog — **recommendation: unprefixed public catalog + `custom.*` for user intents** to keep policies readable.
4. **Every tool call gets ≥1 intent**; if unknown → `unknown.unclassified` with low confidence → default deny/challenge.
5. **Multi-label allowed**: primary intent + secondary tags (e.g. involves_pii=true) — for MVP, **single primary intent + alternatives list** is enough; sensitivity as tags on the request/context.

### 9.2 Classification Output Contract

```ts
interface Classification {
  intent: string;                 // primary
  confidence: number;             // 0..1
  alternatives: Array<{ intent: string; confidence: number }>;
  classifier: string;             // e.g. "deterministic:v1", "llm:openai:gpt-4o-mini"
  reasoning?: string;             // short, safe for logs (no secrets)
  signalsUsed?: string[];         // optional debug
}
```

### 9.3 Built-in Categories (see Appendix B for full MVP list)

- `data.read.*` / `data.write.*` / `data.delete.*`
- `comms.send.*` / `comms.read.*`
- `infra.provision.*` / `infra.mutate.*` / `infra.delete.*`
- `finance.charge.*` / `finance.transfer.*`
- `identity.auth.*` / `identity.permission.*`
- `code.execute.*` / `code.write.*`
- `network.request.*`
- `unknown.unclassified`

---

## 10. Classifier Architecture

### 10.1 Pipeline Order (recommendation — agreed)

```
1) Deterministic (patterns, tool maps, arg schemas)     → if high confidence, stop
2) Embedding / heuristic (optional; post-MVP default)   → if high confidence, stop
3) LLM classifier (OpenAI-compatible)                   → always available as fallback
4) Merge + conflict resolution
```

**MVP ships steps 1 and 3.** Step 2 is stub interface only.

### 10.2 Deterministic Classifier

**Inputs**: tool name, arg keys/values (stringified safely), optional regex rules file.

**Features**:

- Tool → intent map (`send_email` → `comms.send.email`)
- Arg pattern rules (e.g. `to` matches personal email domains → elevate sensitivity / alternate intent)
- Deny-pattern short-circuit (e.g. arg contains `AKIA...` AWS key → `security.secret_exfil`)

**Config (`rules.yaml`)**:

```yaml
version: 1
tool_map:
  send_email: comms.send.email
  execute_sql: data.query.sql
  http_request: network.request.http
patterns:
  - name: aws_key_in_args
    match:
      any_arg_regex: "AKIA[0-9A-Z]{16}"
    intent: security.secret_exposure
    confidence: 0.95
```

**Confidence policy**: tool_map alone → 0.7; tool_map + schema validation → 0.85; pattern hit → 0.9–0.99.

### 10.3 LLM Classifier

**Recommendation (confident):**

- Provider: **OpenAI-compatible HTTP API** (works with OpenAI, Azure, Groq, local gateways)
- Default model: `gpt-4o-mini` (cost/latency); override via config
- Structured output: JSON schema / response_format for `{ intent, confidence, alternatives, reasoning }`
- System prompt includes: allowed intent enum (from taxonomy), tool schema summary, safety instructions (“prefer unknown.unclassified over guessing dangerous as benign”)
- **Strip/redact secrets** from arguments before sending to LLM (pattern-based redaction)
- Timeout: 2s default; on timeout → treat as classifier failure (see fail-closed)
- Token budget: truncate conversation history to last N turns / M chars (defaults: 6 turns / 8k chars)

### 10.4 Conflict Resolution (recommendation)

| Situation | Resolution |
|-----------|------------|
| Deterministic confidence ≥ 0.9 | Use deterministic; skip LLM |
| Deterministic 0.7–0.9 and LLM disagrees | Prefer **more severe** intent for policy matching (security bias); record both |
| Both low confidence (< 0.55) | Primary = `unknown.unclassified`; verdict path likely BLOCK/CHALLENGE |
| LLM unavailable | Fall back to deterministic only; if none, `unknown.unclassified` |

**“More severe”**: maintain a severity rank table on intents (1–100). Abuse/delete/exfil > read.

### 10.5 Caching

- Key: hash(tool name + normalized JSON args + taxonomy version + classifier ids)
- TTL: 60s default
- **Do not cache** when conversation context is part of classification (or include context hash in key when `context.conversationId` present)
- **Recommendation**: context-aware classification **disables** cache by default when `priorCalls` or messages are provided

---

## 11. Policy Language & Engine

### 11.1 Format

- **Authoring**: YAML (primary), JSON (generated/API)
- **Expressions**: CEL-inspired subset (MVP) — **recommendation: implement a small safe expression language**, not full CEL yet; document as `expression` with documented operators

### 11.2 Rule Evaluation Semantics (recommendation)

1. Compile policy at load into sorted rules by `priority` ascending (lower number = higher precedence) — **or** descending?  
   **Recommendation: higher `priority` number wins** (explicit), with stable tie-break by rule id. Document clearly. Alternative many systems use first-match; we choose **highest priority match among matching rules**, then default verdict if none match.
2. A rule matches if all present `match` fields match (AND across fields; OR within list fields).
3. First/highest priority matching rule determines verdict.
4. If no rule matches → `defaultVerdict` (recommend `BLOCK`).

### 11.3 Match Dimensions (MVP)

| Field | Semantics |
|-------|-----------|
| `intents` | Primary intent in list, or any alternative ≥ confidence threshold |
| `tools` | Tool name glob (`send_*`) |
| `callers` | Caller id or role |
| `environments` | e.g. `production`, `staging` |
| `tags` | Request tags include required keys/values |
| `expression` | Boolean over bound variables |

**Bound variables for expressions (MVP):**

- `intent`, `confidence`, `tool.name`, `tool.namespace`
- `caller.id`, `caller.type`, `caller.roles`
- `env`, `tags`
- `args.<key>` for string/number/bool args only (no arbitrary code)

**Operators (MVP):** `== != in && || ! > >= < <= startsWith contains matches`

### 11.4 Policy File Shape

```yaml
version: 1
id: local-policy
name: production-default
description: Default-deny with safe read allowlist
defaultVerdict: BLOCK
severity_threshold:
  alternatives_min_confidence: 0.4
rules:
  - id: allow-health
    name: Allow health checks
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"

  - id: challenge-deletes-prod
    name: Challenge destructive infra in production
    priority: 200
    match:
      environments: ["production"]
      intents: ["infra.delete.resource", "data.delete.record"]
    verdict: CHALLENGE
    reason: "Destructive action in production requires approval"
    challenge:
      channel: "slack"   # local MVP: "stdout" | "webhook"
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-exfil
    name: Block likely exfiltration
    priority: 300
    match:
      intents: ["data.exfiltrate", "security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible data exfiltration or secret exposure"
```

### 11.5 Policy Versioning

- Local: file content + optional `version` field; git is source of truth
- Cloud: `publish` creates immutable version (`semver` or monotonic `vN`) — **recommendation: monotonic `vN` integer + optional semver label**
- Shields pin to `policyId@version` or `latest` (latest discouraged in prod)

### 11.6 Policy Packs (ship with OSS)

1. **`packs/baseline-deny.yaml`** — default deny, allow health + metrics  
2. **`packs/pii-guard.yaml`** — challenge/block PII egress via comms/network  
3. **`packs/change-window.yaml`** — block infra mutate outside maintenance tags  

---

## 12. Verdicts, Challenges & Human-in-the-Loop

### 12.1 Verdict Types

| Verdict | Meaning | Execution |
|---------|---------|-----------|
| `ALLOW` | Permitted | Proceed |
| `BLOCK` | Denied | Do not execute; return error to agent |
| `CHALLENGE` | Needs human approval | Hold; notify; resume on approve/deny |
| `DEFER` | Async review queue | Hold; no synchronous waiter required; timeout policy applies |

### 12.2 Challenge Flow (recommendation)

**Local MVP:**

- `CHALLENGE` returns verdict immediately to caller with `challengeId`
- Side channel: write to sink + optional webhook
- Approval via CLI: `lexshield challenge approve <id>` / `deny` (local store)
- SDK mode: `shield.guard` awaits challenge until timeout if `await_challenge: true` (default **false** for agents — return challenge error to agent loop)

**Cloud:**

- Challenge objects stored; Slack interactive approve/deny (post-MVP if Slack hard); MVP: dashboard button + webhook

**Timeouts:** default 1h; `onTimeout: BLOCK` (fail closed).

### 12.3 What Agents See on BLOCK/CHALLENGE

Return structured error (not only string):

```json
{
  "error": "lexshield_blocked",
  "verdict": "BLOCK",
  "reason": "Possible data exfiltration",
  "matchedRuleId": "block-exfil",
  "requestId": "...",
  "retryable": false
}
```

**Recommendation**: Do **not** include full policy or alternative exploit hints in agent-facing errors. Include enough for developers (`matchedRuleId`) gated by config `expose_rule_ids: true` (default true in dev, false in prod optional).

---

## 13. Execution Interception & Integration Modes

### 13.1 Modes

| Mode | How it works | Best for |
|------|--------------|----------|
| **SDK wrap** | Decorator/wrapper around tool functions | Python/TS monoliths |
| **Evaluate-only** | Caller asks for verdict, executes itself | Custom runtimes |
| **Local proxy** | HTTP proxy `/execute` forwards if ALLOW | Polyglot / sidecars |
| **Cloud evaluate** | Remote policy decision | Centralized governance |

### 13.2 Proxy Semantics (recommendation)

- Proxy is **explicit allowlist of upstream tool endpoints** configured in `lexshield.yaml` — LexShield is not an open forwarder.
- TLS termination local only by default (`127.0.0.1`)
- Forwards original headers except hop-by-hop; adds `X-LexShield-Request-Id`, `X-LexShield-Verdict`
- On BLOCK: HTTP 403 with structured body
- On CHALLENGE: HTTP 202 or 403 with challenge payload — **recommendation: 403 with `verdict: CHALLENGE`** for simpler agent error handling; optional 202 behind flag

### 13.3 Framework Adapters

**MVP**: none in core.  
**Post-MVP contrib**: OpenAI Agents SDK, LangChain tools, CrewAI, Vercel AI SDK `tools`.  
Document a 20-line “wrap your tool” pattern so users don’t wait.

---

## 14. SDKs (Python & TypeScript)

### 14.1 Python (primary)

**Package**: `lexshield` on PyPI  
**Python**: 3.10+  
**Async-first** with sync wrappers.

```python
from lexshield import Shield

shield = Shield.from_config("lexshield.yaml")

@shield.guard(tool="send_email")
async def send_email(to: str, subject: str, body: str):
    ...

verdict = await shield.evaluate(
    tool="send_email",
    arguments={"to": "...", "subject": "...", "body": "..."},
    caller={"id": "agent-1", "type": "agent"},
    context={"conversationId": "conv-42", "environment": "production"},
)

await shield.record_outcome(request_id, "EXECUTED")
```

**Behaviors**:

- On BLOCK: raise `LexShieldBlockedError`
- On CHALLENGE: raise `LexShieldChallengeError` (unless await mode)
- Propagation of `conversation_id` via contextvars helper `shield.session(...)`

### 14.2 TypeScript

**Package**: `@latticeag/lexshield`  
**Runtime**: Node 20+; edge-friendly core evaluate without Node FS (inject config)

```ts
import { Shield } from '@latticeag/lexshield';

const shield = await Shield.fromConfig('lexshield.yaml');

export const sendEmail = shield.guard('send_email', async (args) => { ... });
```

### 14.3 Versioning & Compatibility

- Shared JSON schemas for Policy / Verdict / Trace in `/schemas`
- Golden tests ensure Python and TS engines produce same verdict on fixture suite
- **Recommendation**: implement **policy engine once in a shared form** long-term (Rust/WASM or TS core). **MVP: duplicate carefully with shared fixtures** — faster ship; plan WASM core for v0.3+

---

## 15. CLI Surface

```bash
lexshield init                     # scaffold lexshield.yaml, policy.yaml, rules.yaml, samples
lexshield check                    # validate config + policy + taxonomy
lexshield run                      # start local server/proxy
lexshield evaluate                 # eval from flags or stdin JSON
lexshield traces list|show         # query local ndjson
lexshield challenge list|approve|deny
lexshield login                    # device flow / API key for Cloud
lexshield policy push|pull|diff
lexshield packs list|apply <name>
lexshield version
lexshield completion bash|zsh      # nice-to-have same week if cheap
```

**DX recommendations:**

- Colorized verdicts in TTY; `--json` for scripts
- `lexshield check` exits non-zero on invalid policy (CI-friendly)
- `init` offers interactive and `--pack baseline-deny`

---

## 16. Local API & Proxy

**Default bind**: `http://127.0.0.1:8787` (localhost-only by default — **do not** default to `0.0.0.0`).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/shields/:shieldId/evaluate` | Verdict only |
| POST | `/v1/shields/:shieldId/execute` | Evaluate + forward if ALLOW |
| GET | `/v1/shields/:shieldId/policy` | Current policy |
| POST | `/v1/shields/:shieldId/policy/reload` | Hot reload |
| GET | `/v1/traces` | List/filter traces |
| GET | `/v1/challenges` | Local challenge queue |
| POST | `/v1/challenges/:id/resolve` | approve/deny |
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Policy loaded + classifiers ready |

**Auth for local API (recommendation):** optional shared token via env `LEXSHIELD_LOCAL_TOKEN`; if set, require `Authorization: Bearer ...`. Default off for frictionless local use.

---

## 17. LexShield Cloud

### 17.1 Purpose

- Versioned policy distribution
- Multi-team orgs, API keys
- Long-term trace storage/search
- Alerts (email MVP; Slack soon)
- Invite-only onboarding

### 17.2 Architecture (recommendation)

| Component | Choice | Why |
|-----------|--------|-----|
| Compute | Cloudflare Workers | Edge, LatticeAG fit |
| Consistency / queues | Durable Objects | Per-org coordination, challenge state |
| DB | D1 | Policies, orgs, API keys metadata |
| Blobs / traces | R2 + optional D1 index | Cheap retention |
| Auth | API keys (MVP) + magic-link invite; Clerk/Auth0 later if needed |
| Dashboard | Next.js on Cloudflare Pages or Workers Assets | Fast to ship |

### 17.3 Cloud API (MVP)

```
POST   /v1/orgs/:orgId/policies
GET    /v1/orgs/:orgId/policies/:policyId
POST   /v1/orgs/:orgId/policies/:policyId/publish
GET    /v1/orgs/:orgId/policies/:policyId/versions
POST   /v1/orgs/:orgId/evaluate
POST   /v1/orgs/:orgId/traces/ingest
GET    /v1/orgs/:orgId/traces
POST   /v1/orgs/:orgId/alerts
GET    /v1/orgs/:orgId/alerts
POST   /v1/invites
POST   /v1/auth/api-keys
```

### 17.4 Multi-tenancy

- Strict `orgId` isolation on every query
- API keys hashed at rest (SHA-256 with pepper)
- Rate limit evaluate by org (Cloudflare rate limiting / DO counters)

### 17.5 Invite-only

- Public landing + waitlist
- Invites create org + owner seat
- No self-serve card billing in MVP (manual Pro upgrades OK)

---

## 18. Data Model

```ts
type VerdictType = 'ALLOW' | 'BLOCK' | 'CHALLENGE' | 'DEFER';
type CallerType = 'user' | 'agent' | 'service_account';
type OutcomeType = 'EXECUTED' | 'BLOCKED' | 'CHALLENGED' | 'DEFERRED' | 'ERROR' | 'APPROVED_EXECUTED' | 'DENIED';

interface Shield {
  id: string;
  name: string;
  policyRef: { policyId: string; version?: string }; // version optional = local file
  classifierIds: string[];
  sinks: SinkConfig[];
  toolUpstreams?: Record<string, UpstreamConfig>; // proxy mode
  createdAt: string; // ISO-8601
  updatedAt: string;
}

interface Policy {
  id: string;
  name: string;
  version: string;
  description?: string;
  defaultVerdict: VerdictType;
  rules: PolicyRule[];
  taxonomyRef?: string;
}

interface PolicyRule {
  id: string;
  name: string;
  priority: number;
  enabled?: boolean; // default true
  match: RuleMatch;
  verdict: VerdictType;
  reason: string;
  challenge?: ChallengeConfig;
}

interface RuleMatch {
  intents?: string[];
  tools?: string[];      // glob supported
  callers?: string[];
  roles?: string[];
  environments?: string[];
  tags?: Record<string, string[]>;
  minConfidence?: number;
  expression?: string;
}

interface ChallengeConfig {
  channel: 'stdout' | 'webhook' | 'slack' | 'dashboard';
  timeoutSeconds: number;
  onTimeout: 'BLOCK' | 'ALLOW'; // ALLOW strongly discouraged; warn on check
  reviewers?: string[];
}

interface ToolCallRequest {
  id: string; // ulid/uuid
  shieldId: string;
  timestamp: string;
  caller: Caller;
  tool: ToolRef;
  arguments: Record<string, unknown>;
  context: CallContext;
}

interface Caller {
  id: string;
  type: CallerType;
  roles?: string[];
  metadata?: Record<string, unknown>;
}

interface ToolRef {
  name: string;
  namespace?: string;
  version?: string;
}

interface CallContext {
  conversationId?: string;
  messages?: Array<{ role: string; content: string }>; // optional; size-limited
  priorCalls?: PriorCall[];
  environment?: string;
  tags?: Record<string, string>;
}

interface PriorCall {
  timestamp: string;
  tool: ToolRef;
  intent: string;
  verdict: VerdictType;
}

interface Classification {
  intent: string;
  confidence: number;
  alternatives: Array<{ intent: string; confidence: number }>;
  classifier: string;
  reasoning?: string;
}

interface Verdict {
  requestId: string;
  decision: VerdictType;
  matchedRuleId?: string;
  reason: string;
  classifications: Classification[];
  durationMs: number;
  challengeId?: string;
  policyVersion?: string;
}

interface Trace {
  id: string;
  request: ToolCallRequest;
  verdict: Verdict;
  outcome?: OutcomeType;
  outcomeAt?: string;
  redactions?: string[]; // which fields were redacted
  metadata?: Record<string, unknown>;
}

interface SinkConfig {
  type: 'stdout' | 'file' | 'http' | 'otlp' | 'saas';
  options: Record<string, unknown>;
}

interface UpstreamConfig {
  url: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
}

interface Organization {
  id: string;
  name: string;
  plan: 'free' | 'pro' | 'enterprise';
  createdAt: string;
}

interface ApiKey {
  id: string;
  orgId: string;
  name: string;
  hashedKey: string;
  prefix: string; // e.g. ls_live_abc
  createdAt: string;
  lastUsedAt?: string;
}

interface AlertRule {
  id: string;
  orgId: string;
  name: string;
  condition: {
    verdicts?: VerdictType[];
    intents?: string[];
    thresholdCount: number;
    windowSeconds: number;
  };
  channels: Array<{ type: 'email' | 'webhook' | 'slack'; target: string }>;
}
```

---

## 19. Configuration Schema

### 19.1 `lexshield.yaml` (canonical)

```yaml
version: 1
shield:
  id: local
  name: production-shield
  policy: ./policy.yaml
  taxonomy: ./taxonomy.yaml   # optional; defaults to built-in
  classifiers:
    - type: deterministic
      path: ./rules.yaml
    - type: llm
      model: openai:gpt-4o-mini
      base_url_env: OPENAI_BASE_URL   # optional
      api_key_env: OPENAI_API_KEY
      timeout_ms: 2000
      redact: true
  fail_on_classifier_error: BLOCK     # BLOCK | CHALLENGE | ALLOW(not recommended)
  sinks:
    - type: stdout
    - type: file
      path: ./traces.ndjson
    - type: saas
      org_id_env: LEXSHIELD_ORG_ID
      api_key_env: LEXSHIELD_API_KEY
  proxy:
    enabled: false
    upstreams:
      send_email:
        url: http://127.0.0.1:9001/send
        timeoutMs: 5000
server:
  host: 127.0.0.1
  port: 8787
  token_env: LEXSHIELD_LOCAL_TOKEN
```

### 19.2 Environment Variables

| Var | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | LLM classifier |
| `OPENAI_BASE_URL` | Compatible endpoint |
| `LEXSHIELD_ORG_ID` | Cloud org |
| `LEXSHIELD_API_KEY` | Cloud auth |
| `LEXSHIELD_LOCAL_TOKEN` | Local API auth |
| `LEXSHIELD_LOG_LEVEL` | debug/info/warn/error |

---

## 20. Architecture & Request Pipeline

```
┌─────────────────┐      ┌──────────────────────────────┐      ┌─────────────────┐
│  Agent / SDK    │─────▶│  LexShield Engine            │─────▶│  Tool Endpoint  │
│  / Proxy client │      │  1. Normalize + redact       │      │  (optional)     │
└─────────────────┘      │  2. Classify (det → LLM)     │      └─────────────────┘
                         │  3. Resolve intent severity  │
                         │  4. Match policy rules       │
                         │  5. Emit verdict             │
                         │  6. Async sinks / OTLP       │
                         └──────────────┬───────────────┘
                                        │ optional
                                        ▼
                         ┌──────────────────────────────┐
                         │  LexShield Cloud             │
                         │  policies · traces · alerts  │
                         └──────────────────────────────┘
```

### 20.1 Per-request steps

1. Accept `ToolCallRequest` (generate id if missing — **recommendation: ULID**)
2. Validate schema; reject malformed with 400
3. Redact secrets in args for classifier + trace copies
4. Run classifiers per §10
5. Evaluate policy per §11
6. Persist challenge if needed
7. Emit verdict to caller
8. If proxy execute + ALLOW → forward; record outcome
9. Async write sinks (never block tool path > 1ms for local file buffer)

---

## 21. Performance, Caching & Reliability

| Path | Target |
|------|--------|
| Deterministic classify + policy | p99 < 1–5 ms |
| Embedding (future) | p99 < 50 ms |
| LLM classify | p99 < 500 ms (best-effort; timeout 2s) |
| Trace sink | async; drop-on-overflow with counter metric |

**Recommendations:**

- Compile globs and expressions at policy load
- Use streaming NDJSON file append
- Circuit-breaker on LLM provider (after N failures, skip LLM for T seconds, metric `classifier.llm.circuit_open`)
- Backpressure: in-memory ring buffer for sinks (default 10k events)

---

## 22. Security & Threat Model

### 22.1 Trust Boundaries

| Boundary | Trust assumption |
|----------|------------------|
| Caller identity | **Host application authenticates**; LexShield trusts provided `caller` claims |
| Policy files | Trusted operators / git; Cloud publish is admin-only |
| LLM provider | Sees redacted args; treat as semi-trusted |
| Local server | Localhost by default; token optional |
| Cloud API | API key = org privilege |

### 22.2 Threats & Mitigations

| Threat | Mitigation |
|--------|------------|
| Prompt injection → tool misuse | Intent classify + default deny + challenge destructive intents |
| Policy bypass via evaluate vs execute mismatch | Single engine path; SDKs always evaluate before user code |
| Secret leakage to LLM/logs | Redaction filters; trace field allowlist |
| SSRF via proxy upstreams | Explicit upstream allowlist only |
| Trace tampering (local) | Best-effort; Cloud signed append-only |
| Supply chain | Lockfiles, signed releases later; MIT transparency |
| Cost amplification via LLM classify | Cache, timeouts, circuit breaker, optional `llm: false` for hot tools |
| Confused deputy | Bind shields to env + caller roles in policy |

### 22.3 Security Guarantees (honest)

LexShield **cannot** guarantee safety against all adversarial prompts. It **does** provide defense-in-depth, auditability, and policy enforcement points.

---

## 23. Privacy, Compliance & Data Handling

**Recommendations:**

- **Data minimization**: traces store redacted arguments by default (`trace_arguments: redacted | hash | full`) — default **redacted**
- **Retention**: local unbounded (user’s disk); Cloud Free 7 days; Pro 90 days; Enterprise custom
- **Region**: Cloud US-first MVP; EU option on Enterprise roadmap
- **DPA / SOC2**: roadmap; do not claim compliance until earned
- **Training**: never train models on customer traces by default; explicit opt-in only if ever offered
- **PII**: customers responsible for what they put in tool args; we provide redaction helpers

---

## 24. Observability & Audit

### 24.1 Traces

- Every evaluate produces a Trace (Appendix C)
- Local: NDJSON
- Cloud: ingest API + indexed search (tool, intent, verdict, rule, time, caller)

### 24.2 Metrics (MVP local counters; Cloud dashboard later)

- `lexshield_evaluations_total{verdict}`
- `lexshield_classify_duration_ms{classifier}`
- `lexshield_policy_match_total{rule_id}`
- `lexshield_sink_errors_total`
- `lexshield_llm_circuit_open`

### 24.3 OpenTelemetry

- Emit span `lexshield.evaluate` with attributes: tool, intent, verdict, rule id, duration
- Export via OTLP/HTTP sink config

### 24.4 Alerts (Cloud)

- Threshold on BLOCK/CHALLENGE counts
- Email webhook MVP; Slack post-MVP

---

## 25. Error Handling & Failure Modes

| Failure | Default behavior |
|---------|------------------|
| Invalid request | 400; no tool execution |
| Policy load error on startup | Process exit non-zero |
| Policy hot-reload invalid | Keep previous policy; log error |
| Deterministic classifier error | Treat as no det result |
| LLM timeout/error | Fallback per `fail_on_classifier_error` (default BLOCK if no det intent) |
| Sink failure | Log metric; do not fail verdict |
| Upstream tool error (proxy) | Return 502; outcome ERROR |
| Challenge timeout | `onTimeout` (default BLOCK) |

**Recommendation:** Never fail **open** silently. If config requests `ALLOW` on classifier error, `lexshield check` emits a **hard warning**.

---

## 26. Testing Strategy

### 26.1 Layers

1. **Unit**: expression parser, glob match, redaction, priority resolution  
2. **Golden fixtures**: JSON request + policy → expected verdict (shared Py/TS)  
3. **Classifier**: deterministic rules; LLM with recorded HTTP cassettes (VCR)  
4. **SDK integration**: decorator blocks/allows  
5. **CLI**: snapshot tests for `check`/`evaluate`  
6. **Cloud**: contract tests for authz isolation (org A cannot read org B)

### 26.2 Security regression fixtures (must-have)

- Exfil via `send_email` with PII body  
- `http_request` to suspicious host  
- Delete in production without challenge  
- Benign health check still ALLOW  

### 26.3 CI

- Lint + typecheck + unit + golden on every PR  
- No live LLM calls in CI (cassettes only)

---

## 27. Repository & Monorepo Layout

**Recommendation: monorepo** (pnpm or uv workspace + cargo later):

```
/
  SPEC.md
  README.md
  LICENSE
  schemas/                  # JSON Schema for policy, verdict, trace
  packs/                    # policy packs
  fixtures/                 # golden tests
  packages/
    engine-py/              # or /python
    engine-ts/
    cli/                    # Python Click/Typer OR TS; recommendation: Python Typer for MVP CLI
    cloud/                  # Workers + dashboard
  docs/
  examples/
    python-agent/
    ts-agent/
  contrib/                  # empty in MVP; adapters later
```

**Recommendation:** CLI in **Python** for MVP (same engine import). TS CLI can wait.

---

## 28. Tech Stack Recommendations

| Area | Choice | Rationale |
|------|--------|-----------|
| Python | 3.11+, `uv`, `pydantic` v2, `httpx`, `typer`, `rich` | Fast DX, validation, CLI |
| TS | TypeScript 5.x, `zod`, Node 20 | Schema parity |
| Local server | Python `fastapi` + `uvicorn` | Matches Py ecosystem; simple |
| Cloud | Cloudflare Workers, Hono or itty-router, D1, R2, DO | Edge + LatticeAG |
| Dashboard | Next.js App Router | Speed + CF Pages |
| IDs | ULID | Sortable traces |
| Policy expressions | Custom safe subset | Avoid full CEL complexity in week 1 |
| Testing | `pytest`, `vitest`, shared fixtures | — |
| Packaging | PyPI + npm | — |

---

## 29. Developer Experience & Documentation

### 29.1 Must-have docs (MVP)

1. Quickstart (5 minutes)  
2. Policy authoring guide  
3. Intent catalog reference  
4. SDK reference (Py + TS)  
5. Security model & limitations  
6. Cloud invite onboarding  

### 29.2 Examples

- Minimal Python tool guard  
- Block exfil demo  
- Challenge flow demo  
- CI `lexshield check` in GitHub Actions  

### 29.3 Telemetry (OSS)

**Recommendation:** Opt-in anonymous usage (`lexshield telemetry enable`) — off by default. Never send args/traces.

---

## 30. Dashboard UX (Cloud)

**MVP screens only (avoid dashboard sprawl):**

1. **Overview** — eval volume, block rate, latency (simple charts)  
2. **Policies** — list, editor (Monaco), publish, versions diff  
3. **Traces** — search/filter table, detail drawer  
4. **Challenges** — queue approve/deny  
5. **Settings** — API keys, team invites, alert endpoints  

**Design recommendations (product UI, not marketing site):**

- Dense, operator-first UI (this *is* a control-plane dashboard — exception to “no dashboard” landing rules)
- Dark/light follow system; avoid purple-glow AI cliché
- Verdict colors: ALLOW green, BLOCK red, CHALLENGE amber, DEFER blue — use consistently
- Policy editor validates on save via same schema as CLI `check`

**Marketing landing (separate):** brand-first, one hero composition; waitlist CTA — not part of app shell.

---

## 31. Pricing, Packaging & Go-to-Market

### 31.1 Packaging

| Tier | Price | Includes |
|------|-------|----------|
| OSS | Free (MIT) | Engine, CLI, SDKs, packs |
| Cloud Free | $0 | 1 org, 1 shield, 10k evals/mo, 7-day traces, community |
| Cloud Pro | **$99/mo per org** (see question below) | Unlimited shields, 1M evals/mo, 90-day traces, alerts, SSO later |
| Enterprise | Custom | Regions, audit export, SLA, SSO/SAML, dedicated support |

**Recommendation change vs early draft:** Prefer **per-org** pricing over **per-seat** for MVP simplicity (`$99/org/mo` Pro). Seats matter less until SSO/collaboration expands. Keep seat model as alternative if you sell to security teams that expect seats.

### 31.2 GTM Motion

1. OSS launch (GitHub + HN/Reddit/X + agent Discord communities)  
2. Content: “OPA for agent tools” + incident-style blog posts  
3. Invite-only Cloud for design partners (5–15 companies)  
4. Framework adapter contrib as growth loops  

### 31.3 Design Partner Profile

- Already running agents with ≥3 production tools  
- Has a security/platform owner  
- Willing to share anonymized false-positive feedback  

---

## 32. MVP Milestones (6-Day Build)

> Calendar days are organizational scaffolding only; treat these as **sequenced work packages** with hard deliverables.

| Mile | Focus | Deliverable | Exit criteria |
|------|-------|-------------|---------------|
| **M1** | Policy engine + deterministic classifier | YAML load, match, ALLOW/BLOCK, unit+golden tests | Fixtures pass; `check` works |
| **M2** | Python SDK + local API | `Shield.guard`, FastAPI `/evaluate`, `/healthz` | End-to-end block demo |
| **M3** | LLM classifier + taxonomy | OpenAI-compatible classify, built-in intents, redaction | Cassette-tested classify |
| **M4** | CLI + traces | `init/check/run/evaluate/traces`, NDJSON sink | 5-min quickstart works offline |
| **M5** | TypeScript SDK + proxy | npm package, `/execute` proxy, shared fixtures parity | Same golden verdicts |
| **M6** | Cloud scaffold + invite | Workers API, D1 schema, invite gate, policy publish, trace ingest stub | Design partner can push policy |

**Parallelization note:** Docs and examples written continuously from M2; do not leave docs to the end.

---

## 33. Post-MVP Roadmap

### v0.2

- Embedding classifier option  
- Slack challenges  
- LangChain + OpenAI Agents contrib adapters  
- Policy diff UX + dry-run against historical traces  

### v0.3

- Shared WASM/Rust evaluation core  
- OPA/Cedar import experiments  
- SIEM webhook pack  
- SSO (SAML/OIDC)  

### v1.0

- Stability guarantees, SOC2 path, SLA for Pro/Enterprise  
- Multi-region retention  
- Formal threat model whitepaper  

---

## 34. Open Questions (with Recommendations)

Use this section as the decision workshop checklist. **Bold** = recommended default if you want to move fast.

| # | Question | Recommendation | Confidence |
|---|----------|----------------|------------|
| Q1 | Per-seat vs per-org Pro pricing? | **Per-org $99/mo** for MVP; revisit seats at SSO | High |
| Q2 | Dual engine (Py+TS) vs shared core now? | **Dual + shared fixtures for MVP**; WASM core next | High |
| Q3 | Include framework adapters in MVP? | **No — contrib after M6** | High |
| Q4 | Local embedding classifier in MVP? | **No — interface only** | High |
| Q5 | Expression language: full CEL vs subset? | **Subset**; document upgrade path | High |
| Q6 | Challenge await in SDK default? | **Non-blocking raise**; opt-in await | High |
| Q7 | Cloud auth: Clerk vs API keys only? | **API keys + invite magic link MVP**; Clerk when dashboard multi-user hurts | Medium |
| Q8 | Default bind address ever non-localhost? | **Never without explicit `--host` and warning** | High |
| Q9 | Should BLOCK reasons be visible to the agent LLM? | **Short stable codes + human reason**; hide rule internals in prod option | Medium |
| Q10 | Trace arg storage default? | **Redacted** | High |
| Q11 | Severity-on-classifier-conflict bias? | **Prefer higher severity intent** | High |
| Q12 | Package namespace TS `@latticeag/lexshield` OK? | **Yes** | High |
| Q13 | Monetize OSS support? | Not MVP; optional later | Medium |
| Q14 | Name collision check “LexShield”? | Confirm trademark/domain (`lexshield.dev`?) before launch | Medium — **please confirm domains you own** |
| Q15 | Primary demo vertical? | **PII egress + destructive prod actions** as hero demos | High |
| Q16 | DEFER vs CHALLENGE in MVP UI? | Implement both in engine; **UI focus CHALLENGE only** | High |
| Q17 | Who hosts LLM for Cloud evaluate? | **Customer BYOK** for classification in hybrid; Cloud may offer managed classifier later | Medium |
| Q18 | GitHub org/repo public now? | **Public OSS from first tagged release**; develop in public if comfortable | Medium |

### Questions for you (please answer when ready)

1. **Domain / brand**: Do you already own a domain for LexShield? Preferred docs URL?  
2. **Pricing**: Stick with **$99/seat** from the original draft or switch to **$99/org** as recommended here?  
3. **Cloud auth**: Stay API-key-only for invite MVP, or do you want Clerk from day one?  
4. **Demo vertical**: Is your first design partner closer to **customer-support agents**, **devops/infra agents**, or **finance ops**? (Affects which policy pack we polish first.)  
5. **Engine strategy**: Accept dual Py/TS for speed, or do you want to invest early in a **Rust/WASM** core?  
6. **Adapters**: Any must-have framework for launch week (e.g. Vercel AI SDK) despite the recommendation to defer?  
7. **Telemetry**: Confirm **opt-in only** for OSS phone-home?  
8. **Compliance narrative**: Any near-term enterprise prospect that needs SOC2 language on the marketing site (careful — don’t overclaim)?  

---

## 35. Decision Log

| Decision | Recommendation | Status |
|----------|----------------|--------|
| Primary languages | Python first, TypeScript second | **Agreed** |
| Classifier fallback | Deterministic → (embedding later) → LLM | **Agreed** |
| Default verdict posture | `BLOCK` (default-deny) | **Agreed** |
| SaaS platform | Cloudflare Workers + Durable Objects + D1/R2 | **Agreed** |
| License | MIT | **Agreed** |
| Framework adapters in core MVP | No; contrib post-MVP | **Recommended** |
| LLM classifier | Remote OpenAI-compatible first; local post-MVP | **Recommended** |
| Pro pricing unit | Per-org not per-seat | **Recommended** (overrides earlier seat draft) |
| Shared evaluation core | Fixtures now; WASM later | **Recommended** |
| Local server default host | `127.0.0.1` only | **Recommended** |
| Trace args default | Redacted | **Recommended** |
| CLI implementation language | Python/Typer | **Recommended** |
| Expression language | Safe subset, not full CEL | **Recommended** |
| OSS telemetry | Opt-in, off by default | **Recommended** |
| Challenge SDK behavior | Raise by default; opt-in await | **Recommended** |

---

## Appendix A — Example Policy Packs

### A.1 Baseline deny (sketch)

- Default `BLOCK`
- ALLOW: `health_check`, `get_time`, metrics scrape tools
- CHALLENGE: any `*.delete.*` in `production`
- BLOCK: `data.exfiltrate`, `security.secret_exposure`

### A.2 PII guard (sketch)

- Tag requests with `data_class=pii` from caller
- BLOCK `comms.send.*` when `tags.data_class=pii` and recipient external
- CHALLENGE `network.request.http` when args URL not in allowlist host set

### A.3 Change window (sketch)

- ALLOW `infra.mutate.*` only when `tags.change_ticket` present and `environment!=production` OR maintenance tag set
- Otherwise CHALLENGE

---

## Appendix B — Built-in Intent Catalog (MVP)

> Final list may trim to ~30. Severity 1–100.

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

Customers add `custom.<name>` in taxonomy.

---

## Appendix C — Trace Event Schema

NDJSON line (logical):

```json
{
  "id": "01J...",
  "ts": "2026-07-11T12:00:00.000Z",
  "shieldId": "local",
  "request": {
    "id": "01J...",
    "caller": {"id": "agent-1", "type": "agent", "roles": ["support"]},
    "tool": {"name": "send_email"},
    "arguments_redacted": {"to": "a@b.com", "subject": "…", "body": "[REDACTED]"},
    "context": {"environment": "production", "conversationId": "c1"}
  },
  "classifications": [
    {"intent": "comms.send.email", "confidence": 0.82, "classifier": "deterministic:v1", "alternatives": []}
  ],
  "verdict": {
    "decision": "BLOCK",
    "matchedRuleId": "block-exfil",
    "reason": "Possible data exfiltration or secret exposure",
    "durationMs": 3,
    "policyVersion": "v3"
  },
  "outcome": "BLOCKED",
  "outcomeAt": "2026-07-11T12:00:00.003Z"
}
```

---

## Document History

| Version | Date | Notes |
|---------|------|-------|
| 0.1 | 2026-07-11 | Initial SPEC committed to main |
| 0.2 | 2026-07-11 | Expanded planning SPEC: personas, taxonomy, classifiers, policy semantics, Cloud, security, DX, pricing recommendation, open questions, appendices |

---

*End of SPEC.md — no implementation in this revision; planning only.*
