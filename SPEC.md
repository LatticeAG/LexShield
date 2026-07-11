# LexShield — Product & Engineering Specification

> **Status**: Planning (v0.3 — OSS-first build)  
> **Owner**: LatticeAG  
> **License**: MIT  
> **First build**: **Open-source only** (CLI + SDKs + engine). No SaaS.  
> **Deferred**: LexShield Cloud (hosted control plane) — post-MVP, only after OSS is solid.  
> **This document is the source of truth for build decisions until replaced by ADRs.**  
> **Build readiness**: Yes for OSS MVP — see [§35 Build Readiness](#35-build-readiness).

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
17. [Deferred: LexShield Cloud](#17-deferred-lexshield-cloud)
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
30. [Go-to-Market (OSS)](#30-go-to-market-oss)
31. [MVP Milestones (OSS First Build)](#31-mvp-milestones-oss-first-build)
32. [Post-MVP Roadmap](#32-post-mvp-roadmap)
33. [Open Questions (with Recommendations)](#33-open-questions-with-recommendations)
34. [Decision Log](#34-decision-log)
35. [Build Readiness](#35-build-readiness)
36. [Appendix A — Example Policy Packs](#appendix-a--example-policy-packs)
37. [Appendix B — Built-in Intent Catalog (MVP)](#appendix-b--built-in-intent-catalog-mvp)
38. [Appendix C — Trace Event Schema](#appendix-c--trace-event-schema)

---

## 1. Executive Summary

**LexShield** is an **agent intent router and policy firewall**. It sits between an AI agent and its tool fleet, classifies the *intent* behind each tool call, and enforces allow/block/challenge policy **before** execution.

Existing auth layers (RBAC, OAuth scopes, API keys) authorize *who* can call a tool. They do not understand *why* an agent is calling it in natural-language context. LexShield closes that gap.

**Recommendation — product shape for first build (locked):**

| Layer | Form | First build? |
|-------|------|--------------|
| Core engine | Open-source library + CLI (MIT) | **Yes** |
| SDKs | Python first, TypeScript second | **Yes** |
| Policy packs + examples | Shipped in repo | **Yes** |
| Hosted SaaS (LexShield Cloud) | Future control plane | **No — deferred** |

**One-line positioning (OSS launch):**  
*"The open-source policy firewall for agent tool calls."*

Cloud / paid control plane is a **later** option if users ask for hosted policy distribution, long-term trace retention, and multi-team controls. It is **out of scope for the first build**.

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
  → Proxy for multi-language agents → (later) optional Cloud
```

First value is fully offline. No account, no hosted dependency.

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
6. **OSS is the product** — the first build is MIT open source only; no hosted dependency for correctness or usefulness.
7. **No credential custody** — LexShield does not store tool secrets.
8. **Policy as code** — policies live in git; CI validates them with `lexshield check`.
9. **Honest limits** — document that classification is probabilistic; LexShield reduces risk, does not eliminate adversarial risk.

### 4.3 Brand / Naming

| Name | Use |
|------|-----|
| LexShield | Product, CLI (`lexshield`), Python package `lexshield` |
| `@latticeag/lexshield` | TypeScript package |
| LexShield Cloud | **Deferred** hosted SaaS — not in first build |
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
| Emerging agent security | Guardrails.ai, Portkey, custom wrappers | Overlap possible; LexShield differentiates on **intent taxonomy + policy firewall + local-first OSS** |

**Recommendation**: Position against “OPA for agent tool calls” + “intent classification layer,” not against general LLM safety.

**Differentiation bets (confident):**

1. First-class **intent** object in the policy model  
2. Multi-stage classifier pipeline with deterministic primacy  
3. `CHALLENGE` / `DEFER` as first-class verdicts (HITL)  
4. Fully local, auditable OSS engine with policy-as-code DX  

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
| **Sink** | Trace destination (stdout, file, OTLP, HTTP). |
| **Caller** | Authenticated identity of the agent/user/service making the call (asserted by the host app). |
| **Challenge** | Human approval gate before execution. |
| **Defer** | Async review path; execution withheld until resolved (or timed out → fail closed). |
| **Policy pack** | Curated starter policies for domains (PII, finance, infra). |
| **Fingerprint** | Stable hash of (tool, normalized args, intent candidates, env) for caching. |

---

## 7. Success Metrics

### 7.1 Product / OSS

| Metric | MVP target | Notes |
|--------|------------|-------|
| Time-to-first-eval | < 5 minutes from `pip install` / `npm i` | Include sample policy |
| `lexshield check` in CI | Documented GitHub Action example | Exit non-zero on bad policy |
| Golden fixture count | ≥ 50 scenarios | Py/TS parity |
| Stars / design-partner installs | Qualitative early | Track manually |

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

### 8.1 MVP Goals (in-scope) — OSS only

- YAML/JSON policy engine with rule priority, default-deny, CEL-lite expressions
- Deterministic classifier + LLM classifier (OpenAI-compatible)
- Python SDK (`@shield.guard`, `evaluate`)
- Local HTTP API + proxy execute mode
- CLI: `init`, `check`, `run`, `evaluate`, `traces`, `challenge`
- NDJSON + stdout + optional OTLP/HTTP sinks
- TypeScript SDK parity for `evaluate` + config load
- Built-in intent catalog (~25–40 intents) + 2–3 policy packs
- Docs: quickstart, policy guide, security model, examples
- Local challenge queue (CLI approve/deny)

### 8.2 Explicit Non-Goals (first build)

- **Any SaaS / LexShield Cloud** (dashboard, hosted policies, invite flow, billing)
- Generic API gateway features (LB, primary rate limiting product, request rewrite)
- Being an agent / planner / workflow engine
- Secrets management / vault
- Replacing HITL for high-stakes actions (we formalize it)
- Mobile apps, browser extensions, consumer clients
- Guaranteed prompt-injection immunity
- Training proprietary foundation models
- In-core LangChain/OpenAI Agents adapters (contrib later)
- SSO, multi-tenant org management, cloud alerts

### 8.3 Soft Non-Goals (post-OSS-MVP candidates)

- LexShield Cloud (hosted control plane)
- Local embedding models as default
- Full Cedar / Rego interop
- Framework adapters in `contrib/`
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

- Local: file content + optional `version` field; **git is source of truth**
- `lexshield check` validates before merge
- Future Cloud may add immutable published versions — not in first build

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

**Local only (first build):**

- `CHALLENGE` returns verdict immediately to caller with `challengeId`
- Side channel: write to sink + optional webhook
- Approval via CLI: `lexshield challenge approve <id>` / `deny` (local store)
- SDK mode: `shield.guard` awaits challenge until timeout if `await_challenge: true` (default **false** for agents — return challenge error to agent loop)

**Timeouts:** default 1h; `onTimeout: BLOCK` (fail closed).

Hosted challenge UIs (dashboard / Slack) are **deferred with Cloud**.

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
lexshield packs list|apply <name>
lexshield version
lexshield completion bash|zsh      # nice-to-have if cheap
```

> Cloud commands (`login`, `policy push|pull`) are **not in the first build**.

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

## 17. Deferred: LexShield Cloud

**Status: out of scope for the first build.**

A future hosted control plane *may* add:

- Versioned policy distribution across teams
- Long-term trace storage/search and alerts
- Org/API keys, invite onboarding, dashboard

**Suggested future stack (when revisited):** Cloudflare Workers + Durable Objects + D1 + R2 + Next.js dashboard.

Until then: policies and traces stay on the user’s machine / git / their own sinks (file, HTTP, OTLP). Do not scaffold `packages/cloud` in the first build.

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
  type: 'stdout' | 'file' | 'http' | 'otlp';
  options: Record<string, unknown>;
}

interface UpstreamConfig {
  url: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
}
```

> Cloud-only types (`Organization`, `ApiKey`, `AlertRule`) are deferred and omitted from the first-build data model.

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
| `LEXSHIELD_LOCAL_TOKEN` | Local API auth |
| `LEXSHIELD_LOG_LEVEL` | debug/info/warn/error |

---

## 20. Architecture & Request Pipeline

```
┌─────────────────┐      ┌──────────────────────────────┐      ┌─────────────────┐
│  Agent / SDK    │─────▶│  LexShield Engine (OSS)      │─────▶│  Tool Endpoint  │
│  / Proxy client │      │  1. Normalize + redact       │      │  (optional)     │
└─────────────────┘      │  2. Classify (det → LLM)     │      └─────────────────┘
                         │  3. Resolve intent severity  │
                         │  4. Match policy rules       │
                         │  5. Emit verdict             │
                         │  6. Async sinks / OTLP       │
                         └──────────────────────────────┘
```

No hosted control plane in the request path for the first build.

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
| Policy files | Trusted operators / git |
| LLM provider | Sees redacted args; treat as semi-trusted |
| Local server | Localhost by default; token optional |

### 22.2 Threats & Mitigations

| Threat | Mitigation |
|--------|------------|
| Prompt injection → tool misuse | Intent classify + default deny + challenge destructive intents |
| Policy bypass via evaluate vs execute mismatch | Single engine path; SDKs always evaluate before user code |
| Secret leakage to LLM/logs | Redaction filters; trace field allowlist |
| SSRF via proxy upstreams | Explicit upstream allowlist only |
| Trace tampering (local) | Best-effort; users can ship traces to their own immutable store |
| Supply chain | Lockfiles, signed releases later; MIT transparency |
| Cost amplification via LLM classify | Cache, timeouts, circuit breaker, optional `llm: false` for hot tools |
| Confused deputy | Bind shields to env + caller roles in policy |

### 22.3 Security Guarantees (honest)

LexShield **cannot** guarantee safety against all adversarial prompts. It **does** provide defense-in-depth, auditability, and policy enforcement points.

---

## 23. Privacy, Compliance & Data Handling

**Recommendations:**

- **Data minimization**: traces store redacted arguments by default (`trace_arguments: redacted | hash | full`) — default **redacted**
- **Retention**: local unbounded (user’s disk / their sinks)
- **Training**: never send customer data anywhere except user-configured LLM/OTLP endpoints
- **PII**: customers responsible for what they put in tool args; we provide redaction helpers
- Hosted retention/region/DPA topics apply only when/if Cloud is built later

---

## 24. Observability & Audit

### 24.1 Traces

- Every evaluate produces a Trace (Appendix C)
- Local: NDJSON; optional HTTP/OTLP export to the user’s stack

### 24.2 Metrics (local counters)

- `lexshield_evaluations_total{verdict}`
- `lexshield_classify_duration_ms{classifier}`
- `lexshield_policy_match_total{rule_id}`
- `lexshield_sink_errors_total`
- `lexshield_llm_circuit_open`

### 24.3 OpenTelemetry

- Emit span `lexshield.evaluate` with attributes: tool, intent, verdict, rule id, duration
- Export via OTLP/HTTP sink config

### 24.4 Alerts

- Not built-in for first build — users alert off their own log/OTLP pipeline
- Optional: document a sample Grafana/Datadog query on OTLP attributes

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
6. **Contract/security**: org isolation N/A until Cloud; focus on redaction + fail-closed tests

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
    cli/                    # Python Typer CLI
  docs/
  examples/
    python-agent/
    ts-agent/
  contrib/                  # empty in first build; adapters later
```

**Recommendation:** CLI in **Python** for MVP (same engine import). No `packages/cloud` until Cloud is greenlit.

---

## 28. Tech Stack Recommendations

| Area | Choice | Rationale |
|------|--------|-----------|
| Python | 3.11+, `uv`, `pydantic` v2, `httpx`, `typer`, `rich` | Fast DX, validation, CLI |
| TS | TypeScript 5.x, `zod`, Node 20 | Schema parity |
| Local server | Python `fastapi` + `uvicorn` | Matches Py ecosystem; simple |
| IDs | ULID | Sortable traces |
| Policy expressions | Custom safe subset | Avoid full CEL complexity in week 1 |
| Testing | `pytest`, `vitest`, shared fixtures | — |
| Packaging | PyPI + npm | — |

> Cloudflare / Next.js dashboard stack is **deferred** with Cloud.

---

## 29. Developer Experience & Documentation

### 29.1 Must-have docs (first build)

1. Quickstart (5 minutes)  
2. Policy authoring guide  
3. Intent catalog reference  
4. SDK reference (Py + TS)  
5. Security model & limitations  
6. CI example (`lexshield check` in GitHub Actions)

### 29.2 Examples

- Minimal Python tool guard  
- Block exfil demo  
- Challenge flow demo  
- CI `lexshield check` in GitHub Actions  

### 29.3 Telemetry (OSS)

**Recommendation:** Opt-in anonymous usage (`lexshield telemetry enable`) — off by default. Never send args/traces. Can ship after first public tag; not required for M1–M5.

---

## 30. Go-to-Market (OSS)

**First build is free MIT OSS. No pricing page, no seats, no Cloud tiers.**

### 30.1 Launch motion

1. Public GitHub repo + clear README/quickstart  
2. Post to agent/security communities (HN, relevant Discords, X)  
3. Content: “OPA for agent tools” + demo GIFs of block/challenge  
4. Collect design-partner feedback via GitHub Issues / Discord  

### 30.2 Design Partner Profile

- Already running agents with ≥3 production tools  
- Has a security/platform owner  
- Willing to share anonymized false-positive feedback  

### 30.3 Monetization

Deferred. Revisit Cloud/support only after OSS traction and clear demand for hosted control plane.

---

## 31. MVP Milestones (OSS First Build)

> Sequenced work packages with hard deliverables. No Cloud milestone.

| Mile | Focus | Deliverable | Exit criteria |
|------|-------|-------------|---------------|
| **M1** | Policy engine + deterministic classifier | YAML load, match, ALLOW/BLOCK, unit+golden tests | Fixtures pass; `check` works |
| **M2** | Python SDK + local API | `Shield.guard`, FastAPI `/evaluate`, `/healthz` | End-to-end block demo |
| **M3** | LLM classifier + taxonomy | OpenAI-compatible classify, built-in intents, redaction | Cassette-tested classify |
| **M4** | CLI + traces + challenges | `init/check/run/evaluate/traces/challenge`, NDJSON sink | 5-min quickstart works offline |
| **M5** | TypeScript SDK + proxy | npm package, `/execute` proxy, shared fixtures parity | Same golden verdicts |
| **M6** | Docs, packs, examples, polish | Policy packs, examples, README, security docs, CI action | Public-ready OSS tag `v0.1.0` |

**Parallelization note:** Docs and examples written continuously from M2; M6 is hardening, not starting docs from zero.

---

## 32. Post-MVP Roadmap

### After OSS v0.1

- Embedding classifier option  
- LangChain + OpenAI Agents + Vercel AI SDK contrib adapters  
- Policy dry-run against fixture/trace corpora  
- Shared WASM/Rust evaluation core (optional)

### Later (only if demanded)

- **LexShield Cloud** — hosted policies, traces, alerts, dashboard  
- Slack challenges, SSO, SIEM packs  
- SOC2 / enterprise packaging  

---

## 33. Open Questions (with Recommendations)

| # | Question | Recommendation | Confidence |
|---|----------|----------------|------------|
| Q1 | SaaS in first build? | **No — OSS only** | **Locked** |
| Q2 | Dual engine (Py+TS) vs shared core now? | **Dual + shared fixtures**; WASM later | High |
| Q3 | Framework adapters in first build? | **No — contrib after v0.1** | High |
| Q4 | Local embedding classifier? | **No — interface only** | High |
| Q5 | Expression language: full CEL vs subset? | **Subset** | High |
| Q6 | Challenge await in SDK default? | **Non-blocking raise**; opt-in await | High |
| Q7 | Default bind address? | **`127.0.0.1` only** without explicit `--host` | High |
| Q8 | BLOCK reasons visible to agent LLM? | Short reason + optional hide rule ids in prod | Medium |
| Q9 | Trace arg storage default? | **Redacted** | High |
| Q10 | Severity-on-classifier-conflict? | **Prefer higher severity intent** | High |
| Q11 | TS package name `@latticeag/lexshield`? | **Yes** | High |
| Q12 | Primary demo vertical? | **PII egress + destructive prod actions** | High |
| Q13 | DEFER in first UI/CLI? | Engine yes; **CLI focus CHALLENGE** | High |
| Q14 | Domain / GitHub public now? | Public at first tagged release | Medium |

### Still useful to confirm

1. **Domain**: docs/site URL you own?  
2. **Demo vertical**: support vs devops/infra vs finance for the polished pack?  
3. **Must-have adapter** at launch despite deferral? (default: none)  
4. **Telemetry**: confirm opt-in only / can wait until after v0.1?

---

## 34. Decision Log

| Decision | Recommendation | Status |
|----------|----------------|--------|
| First build shape | **OSS only** — no SaaS | **Locked** |
| Primary languages | Python first, TypeScript second | **Agreed** |
| Classifier fallback | Deterministic → (embedding later) → LLM | **Agreed** |
| Default verdict posture | `BLOCK` (default-deny) | **Agreed** |
| License | MIT | **Agreed** |
| LexShield Cloud | Deferred post-OSS | **Locked** |
| Framework adapters in core | No; contrib after v0.1 | **Recommended** |
| LLM classifier | Remote OpenAI-compatible first | **Recommended** |
| Shared evaluation core | Fixtures now; WASM later | **Recommended** |
| Local server default host | `127.0.0.1` only | **Recommended** |
| Trace args default | Redacted | **Recommended** |
| CLI implementation language | Python/Typer | **Recommended** |
| Expression language | Safe subset, not full CEL | **Recommended** |
| OSS telemetry | Opt-in, off by default; optional post-v0.1 | **Recommended** |
| Challenge SDK behavior | Raise by default; opt-in await | **Recommended** |

---

## 35. Build Readiness

### Verdict: **Yes — ready to build the OSS MVP.**

The problem, scope, API shapes, data model, milestones, and fail-closed defaults are clear enough to start M1 without waiting on Cloud, pricing, or auth vendors.

### Ready enough

- Core loop is well-defined: classify → policy → verdict → trace  
- Default-deny + deterministic-first reduces early product risk  
- Python → local API → CLI → TS is a sane build order  
- Non-goals (especially **no SaaS**) keep scope shippable  

### Accept residual ambiguity (do not block)

- Exact intent catalog wording can evolve behind semver  
- Expression language can start tiny and grow  
- Dual Py/TS engine duplication is a known debt  
- Design-partner vertical can be chosen during pack polish (M6)  

### Do this on day 1 of build

1. Scaffold monorepo (`engine-py`, schemas, fixtures, packs)  
2. Implement policy load + match + golden fixtures  
3. Keep Cloud / dashboard / billing out of the tree  

### Do **not** start until blocked (none currently)

- No SaaS credentials, Clerk, or Cloudflare account needed for first build  
- LLM key only needed from M3; M1–M2 can be deterministic-only  

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
| 0.2 | 2026-07-11 | Expanded planning SPEC |
| 0.3 | 2026-07-11 | **OSS-first lock**: SaaS/Cloud removed from first build; M6 = docs/polish; build-readiness = go |

---

*End of SPEC.md — planning only; implementation starts when build is kicked off.*
