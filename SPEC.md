# LexShield — Product & Engineering Specification

> **Status**: Planning (v0.4 — v0.1 feature freeze)  
> **Owner**: LatticeAG  
> **License**: MIT  
> **First build**: **Open-source only** (CLI + SDKs + engine). No SaaS.  
> **Deferred**: LexShield Cloud (hosted control plane) — post-MVP, only after OSS is solid.  
> **This document is the source of truth for build decisions until replaced by ADRs.**  
> **Ship list**: [§9 v0.1 Feature Freeze](#9-v01-feature-freeze-specific) · **Build readiness**: [§36](#36-build-readiness)

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
9. [v0.1 Feature Freeze (Specific)](#9-v01-feature-freeze-specific)
10. [Intent Taxonomy](#10-intent-taxonomy)
11. [Classifier Architecture](#11-classifier-architecture)
12. [Policy Language & Engine](#12-policy-language--engine)
13. [Verdicts, Challenges & Human-in-the-Loop](#13-verdicts-challenges--human-in-the-loop)
14. [Execution Interception & Integration Modes](#14-execution-interception--integration-modes)
15. [SDKs (Python & TypeScript)](#15-sdks-python--typescript)
16. [CLI Surface](#16-cli-surface)
17. [Local API & Proxy](#17-local-api--proxy)
18. [Deferred: LexShield Cloud](#18-deferred-lexshield-cloud)
19. [Data Model](#19-data-model)
20. [Configuration Schema](#20-configuration-schema)
21. [Architecture & Request Pipeline](#21-architecture--request-pipeline)
22. [Performance, Caching & Reliability](#22-performance-caching--reliability)
23. [Security & Threat Model](#23-security--threat-model)
24. [Privacy, Compliance & Data Handling](#24-privacy-compliance--data-handling)
25. [Observability & Audit](#25-observability--audit)
26. [Error Handling & Failure Modes](#26-error-handling--failure-modes)
27. [Testing Strategy](#27-testing-strategy)
28. [Repository & Monorepo Layout](#28-repository--monorepo-layout)
29. [Tech Stack Recommendations](#29-tech-stack-recommendations)
30. [Developer Experience & Documentation](#30-developer-experience--documentation)
31. [Go-to-Market (OSS)](#31-go-to-market-oss)
32. [MVP Milestones (OSS First Build)](#32-mvp-milestones-oss-first-build)
33. [Post-MVP Roadmap](#33-post-mvp-roadmap)
34. [Open Questions (with Recommendations)](#34-open-questions-with-recommendations)
35. [Decision Log](#35-decision-log)
36. [Build Readiness](#36-build-readiness)
37. [Appendix A — Example Policy Packs](#appendix-a--example-policy-packs)
38. [Appendix B — Built-in Intent Catalog (v0.1)](#appendix-b--built-in-intent-catalog-v01)
39. [Appendix C — Trace Event Schema](#appendix-c--trace-event-schema)
40. [Appendix D — v0.1 Acceptance Checklist](#appendix-d--v01-acceptance-checklist)

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

## 9. v0.1 Feature Freeze (Specific)

> This is the **authoritative ship list** for tag `v0.1.0`.  
> If it is not listed here as **IN**, it is **OUT** of v0.1 — even if mentioned elsewhere as future work.

### 9.1 Product promise (one sentence)

Install LexShield, wrap a tool (or hit `/evaluate`), load a YAML policy, and get an explainable `ALLOW` / `BLOCK` / `CHALLENGE` before the tool runs — fully offline except optional LLM classify.

### 9.2 IN — must ship in v0.1.0

#### A. Core engine (Python — source of truth)

| Feature | Exact behavior |
|---------|----------------|
| Policy load | Parse `policy.yaml` (YAML 1.2) + JSON equivalent; reject unknown fields in strict mode (`lexshield check --strict`) |
| Default deny | `defaultVerdict: BLOCK` required in shipped packs; engine allows override but `check` warns if `ALLOW` |
| Rule match | AND across match fields; OR within list fields; tool globs (`send_*`, `db.*`) |
| Priority | Highest `priority` number wins among matching rules; tie-break: lexicographic `rule.id` ascending |
| Verdicts | `ALLOW`, `BLOCK`, `CHALLENGE`, `DEFER` all implemented in engine |
| Expressions | Safe subset only — see §9.5; compile at load; no runtime `eval` |
| Deterministic classifier | `tool_map` + `patterns` (`any_arg_regex`, `arg_regex:<key>`) from `rules.yaml` |
| LLM classifier | OpenAI-compatible chat + JSON object response; default model `gpt-4o-mini`; timeout **2000ms**; skipped if no API key and config marks llm optional |
| Classifier order | Deterministic first; if confidence ≥ **0.90**, skip LLM; else run LLM and merge |
| Conflict bias | On disagreement, pick **higher severity** intent as primary; keep both in `classifications[]` |
| Redaction | Before LLM + before trace write: AWS keys, `sk-`/`sk-proj-` tokens, Bearer tokens, emails optional flag; default ON for secrets, emails hashed in traces |
| Fail closed | Classifier total failure with no deterministic hit → `unknown.unclassified` → apply policy (usually BLOCK) |
| Fingerprint cache | Deterministic-only results cached 60s; **disabled** when `context.messages` or `priorCalls` present |
| Traces | Append NDJSON; never block evaluate > buffered write |
| Challenges | Local store under `.lexshield/challenges/` (or config path); approve/deny via CLI/API; timeout → `onTimeout` (default BLOCK) |

#### B. Python SDK (`lexshield` on PyPI)

| API | Spec |
|-----|------|
| `Shield.from_config(path)` | Load yaml; validate; compile policy |
| `await shield.evaluate(...)` | Returns `Verdict`; never executes tool |
| `@shield.guard` / `@shield.guard(tool="name")` | Wraps async fn; sync wrapper via `shield.guard_sync` also shipped |
| `shield.session(conversation_id=..., environment=..., tags=...)` | contextvars for nested calls |
| `await shield.record_outcome(request_id, outcome)` | Updates last trace line / side index |
| Errors | `LexShieldBlockedError`, `LexShieldChallengeError`, `LexShieldConfigError` — all carry `verdict` / `request_id` |

**Decorator defaults (locked):**

- On `BLOCK` → raise `LexShieldBlockedError`  
- On `CHALLENGE` → raise `LexShieldChallengeError` (do **not** await approval)  
- Opt-in: `@shield.guard(await_challenge=True)` waits until approve/deny/timeout  

#### C. Local HTTP API (FastAPI)

Ship exactly these routes:

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/v1/shields/{shield_id}/evaluate` | body = ToolCallRequest (id optional → ULID) |
| `POST` | `/v1/shields/{shield_id}/execute` | evaluate + forward iff ALLOW + upstream configured |
| `GET` | `/v1/shields/{shield_id}/policy` | compiled policy JSON |
| `POST` | `/v1/shields/{shield_id}/policy/reload` | hot reload; keep old on failure |
| `GET` | `/v1/traces` | `?decision=&tool=&intent=&limit=&offset=` |
| `GET` | `/v1/challenges` | open challenges |
| `POST` | `/v1/challenges/{id}/resolve` | `{ "decision": "approve"\|"deny", "actor": "..." }` |
| `GET` | `/healthz` | liveness |
| `GET` | `/readyz` | policy loaded |

Defaults: host `127.0.0.1`, port `8787`. If `LEXSHIELD_LOCAL_TOKEN` set → require Bearer token.

#### D. Proxy execute (v0.1)

- Only tools listed under `shield.proxy.upstreams` may be forwarded  
- Adds headers `X-LexShield-Request-Id`, `X-LexShield-Verdict`  
- BLOCK/CHALLENGE/DEFER → **HTTP 403** + JSON error body (no 202 in v0.1)  
- Upstream timeout default **5000ms**  

#### E. CLI (`lexshield`)

| Command | Must do |
|---------|---------|
| `lexshield init [--pack baseline-deny\|pii-guard\|change-window]` | Write `lexshield.yaml`, `policy.yaml`, `rules.yaml`, `.gitignore` entries for traces/challenges |
| `lexshield check [--strict]` | Exit 0/1; print rule count, intent refs, warnings |
| `lexshield run [--host 127.0.0.1] [--port 8787]` | Start API; refuse `0.0.0.0` unless `--i-understand-bind-all` |
| `lexshield evaluate --tool T --args '{}' [--caller ...] [-c config]` | Print verdict; `--json` for machine output |
| `lexshield evaluate --stdin` | Read ToolCallRequest JSON |
| `lexshield traces list [--decision BLOCK] [--limit 50]` | Read NDJSON |
| `lexshield traces show <request_id>` | One trace |
| `lexshield challenge list` | Open challenges |
| `lexshield challenge approve <id>` / `deny <id>` | Resolve |
| `lexshield packs list` / `packs apply <name>` | Copy pack files into cwd |
| `lexshield version` | Semver + git sha if available |

#### F. TypeScript SDK (`@latticeag/lexshield`)

**v0.1 parity (required):**

- `Shield.fromConfig` / `evaluate` / `guard` for async functions  
- Same verdict JSON shape as Python  
- Golden fixtures: **100% identical decisions** on `fixtures/golden/**`  

**v0.1 not required in TS:** CLI, FastAPI server, challenge file store (TS may call local HTTP API for challenges).

#### G. Built-in content

| Asset | Exact v0.1 set |
|-------|----------------|
| Intents | **24** locked in Appendix B (no more, no fewer for v0.1 tag) |
| Packs | `baseline-deny`, `pii-guard`, `change-window` — full YAML in Appendix A |
| Examples | `examples/python-block-exfil`, `examples/python-challenge-delete`, `examples/ts-evaluate` |
| Schemas | JSON Schema for Policy, ToolCallRequest, Verdict, Trace |
| CI example | `.github/workflows/lexshield-check.example.yml` |

#### H. Docs (required pages)

1. README quickstart (≤5 minutes, deterministic-only path)  
2. `docs/policy.md` — authoring + priority + expressions  
3. `docs/intents.md` — catalog + severity  
4. `docs/sdk-python.md` / `docs/sdk-typescript.md`  
5. `docs/security.md` — threat model + honest limits  
6. `docs/cli.md`  

### 9.3 OUT — explicitly cut from v0.1

Do **not** build these even if “easy”:

- LexShield Cloud, login, policy push/pull, saas sink  
- Embedding classifier (interface stub OK, no model)  
- Framework adapters (LangChain, OpenAI Agents, CrewAI, Vercel AI SDK)  
- Slack / email challenge channels (webhook + stdout only)  
- Full CEL / OPA / Cedar  
- Rate limiting product, quotas, anomaly ML  
- Web dashboard / policy UI  
- Telemetry phone-home (even opt-in — defer to v0.2)  
- Sync multi-region anything  
- Argument mutation / rewriting tool calls  
- Streaming tool responses through proxy  
- DEFER resolution UI (engine accepts `DEFER`; CLI only lists; no separate defer workflow beyond challenge-like timeout)  
- Windows-first packaging quirks beyond “should work on Win/Mac/Linux” best effort  

### 9.4 v0.1 “wow” demos (ship as runnable examples)

These three demos define the product story. Each must run with **deterministic classifier only** (no API key):

1. **Block exfil** — `send_email` with AWS key in body → `security.secret_exposure` → `BLOCK`  
2. **Challenge delete** — `delete_resource` in `environment=production` → `CHALLENGE` → CLI approve → re-evaluate/execute path documented  
3. **Allow health** — `health_check` → `ALLOW` under default-deny policy  

LLM demo (optional fourth, docs-only): same exfil without secret pattern, LLM suggests `data.exfiltrate` — cassette-tested, not required for quickstart.

### 9.5 Expression language (frozen subset)

**Allowed:**

```
intent, confidence, tool.name, tool.namespace,
caller.id, caller.type, caller.roles,
env, tags.<key>, args.<key>
```

**Operators:** `== != > >= < <= && || !` · `in` (list) · `startsWith` · `contains` · `matches` (RE2-ish subset)

**Disallow:** function calls beyond above, attribute chaining loops, imports, side effects.

Example:

```yaml
expression: 'env == "production" && confidence >= 0.7 && args.to contains "@gmail.com"'
```

### 9.6 Redaction rules (frozen defaults)

| Pattern | Replacement |
|---------|-------------|
| `AKIA[0-9A-Z]{16}` | `[REDACTED_AWS_KEY]` |
| `sk-[a-zA-Z0-9]{20,}` / `sk-proj-[...]` | `[REDACTED_API_KEY]` |
| `Bearer [A-Za-z0-9._\-]+` | `Bearer [REDACTED]` |
| `(?i)password\s*[:=]\s*\S+` | `password=[REDACTED]` |

Config: `redact.emails: hash | redact | off` — default **`hash`** (sha256 prefix) in traces; **`redact`** when sending to LLM.

### 9.7 Error JSON (frozen)

Agent/HTTP facing body:

```json
{
  "error": "lexshield_blocked",
  "verdict": "BLOCK",
  "reason": "Possible secret exposure in tool arguments",
  "request_id": "01J...",
  "matched_rule_id": "block-secret-exposure",
  "retryable": false
}
```

`error` enum: `lexshield_blocked` | `lexshield_challenged` | `lexshield_deferred` | `lexshield_config` | `lexshield_upstream`.

Config `expose_rule_ids: true` default in v0.1 (devs need it); document how to set `false` for prod agent-facing surfaces.

### 9.8 Performance budgets (v0.1 gate)

| Path | Gate |
|------|------|
| Deterministic evaluate (no LLM) | p99 < **5ms** on laptop-class CI runner for 100-rule policy |
| Policy load + compile | < **100ms** for packs shipped |
| LLM path | timeout hard-stop **2000ms**; not a p99 gate |

### 9.9 Release artifacts

- PyPI: `lexshield==0.1.0`  
- npm: `@latticeag/lexshield@0.1.0`  
- GitHub release notes + checksums for sdist/wheel  
- `LICENSE` MIT + `NOTICE` (LatticeAG)  

### 9.10 Suggested cut order if timeboxed

If scope must shrink further, cut in this order (keep product coherent):

1. Keep: engine + Py SDK + CLI `check/evaluate` + baseline pack + exfil demo  
2. Then: local API + traces  
3. Then: challenges  
4. Then: TS SDK + proxy  
5. Then: other packs + LLM classifier  

**Never cut:** default-deny, explainable verdicts, redaction, golden fixtures.

---

## 10. Intent Taxonomy

### 10.1 Design Recommendations (confident)

1. **Hierarchical, dot-namespaced intents**: `data.read.pii`, `infra.delete.resource`, `comms.send.external`.
2. **Separate “benign” and “abuse” intents** where useful: `http.fetch` vs `data.exfiltrate` — abuse intents are assigned when signals suggest malice/sensitivity mismatch.
3. **Customer can extend** via `taxonomy.yaml`; built-ins are namespaced `lex.*` or unprefixed public catalog — **recommendation: unprefixed public catalog + `custom.*` for user intents** to keep policies readable.
4. **Every tool call gets ≥1 intent**; if unknown → `unknown.unclassified` with low confidence → default deny/challenge.
5. **Multi-label allowed**: primary intent + secondary tags (e.g. involves_pii=true) — for MVP, **single primary intent + alternatives list** is enough; sensitivity as tags on the request/context.

### 10.2 Classification Output Contract

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

### 10.3 Built-in Categories (see Appendix B for full MVP list)

- `data.read.*` / `data.write.*` / `data.delete.*`
- `comms.send.*` / `comms.read.*`
- `infra.provision.*` / `infra.mutate.*` / `infra.delete.*`
- `finance.charge.*` / `finance.transfer.*`
- `identity.auth.*` / `identity.permission.*`
- `code.execute.*` / `code.write.*`
- `network.request.*`
- `unknown.unclassified`

---

## 11. Classifier Architecture

### 11.1 Pipeline Order (recommendation — agreed)

```
1) Deterministic (patterns, tool maps, arg schemas)     → if high confidence, stop
2) Embedding / heuristic (optional; post-MVP default)   → if high confidence, stop
3) LLM classifier (OpenAI-compatible)                   → always available as fallback
4) Merge + conflict resolution
```

**MVP ships steps 1 and 3.** Step 2 is stub interface only.

### 11.2 Deterministic Classifier

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

### 11.3 LLM Classifier

**Recommendation (confident):**

- Provider: **OpenAI-compatible HTTP API** (works with OpenAI, Azure, Groq, local gateways)
- Default model: `gpt-4o-mini` (cost/latency); override via config
- Structured output: JSON schema / response_format for `{ intent, confidence, alternatives, reasoning }`
- System prompt includes: allowed intent enum (from taxonomy), tool schema summary, safety instructions (“prefer unknown.unclassified over guessing dangerous as benign”)
- **Strip/redact secrets** from arguments before sending to LLM (pattern-based redaction)
- Timeout: 2s default; on timeout → treat as classifier failure (see fail-closed)
- Token budget: truncate conversation history to last N turns / M chars (defaults: 6 turns / 8k chars)

### 11.4 Conflict Resolution (recommendation)

| Situation | Resolution |
|-----------|------------|
| Deterministic confidence ≥ 0.9 | Use deterministic; skip LLM |
| Deterministic 0.7–0.9 and LLM disagrees | Prefer **more severe** intent for policy matching (security bias); record both |
| Both low confidence (< 0.55) | Primary = `unknown.unclassified`; verdict path likely BLOCK/CHALLENGE |
| LLM unavailable | Fall back to deterministic only; if none, `unknown.unclassified` |

**“More severe”**: maintain a severity rank table on intents (1–100). Abuse/delete/exfil > read.

### 11.5 Caching

- Key: hash(tool name + normalized JSON args + taxonomy version + classifier ids)
- TTL: 60s default
- **Do not cache** when conversation context is part of classification (or include context hash in key when `context.conversationId` present)
- **Recommendation**: context-aware classification **disables** cache by default when `priorCalls` or messages are provided

---

## 12. Policy Language & Engine

### 12.1 Format

- **Authoring**: YAML (primary), JSON (generated/API)
- **Expressions**: CEL-inspired subset (MVP) — **recommendation: implement a small safe expression language**, not full CEL yet; document as `expression` with documented operators

### 12.2 Rule Evaluation Semantics (recommendation)

1. Compile policy at load into sorted rules by `priority` ascending (lower number = higher precedence) — **or** descending?  
   **Recommendation: higher `priority` number wins** (explicit), with stable tie-break by rule id. Document clearly. Alternative many systems use first-match; we choose **highest priority match among matching rules**, then default verdict if none match.
2. A rule matches if all present `match` fields match (AND across fields; OR within list fields).
3. First/highest priority matching rule determines verdict.
4. If no rule matches → `defaultVerdict` (recommend `BLOCK`).

### 12.3 Match Dimensions (MVP)

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

### 12.4 Policy File Shape

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

### 12.5 Policy Versioning

- Local: file content + optional `version` field; **git is source of truth**
- `lexshield check` validates before merge
- Future Cloud may add immutable published versions — not in first build

### 12.6 Policy Packs (ship with OSS)

1. **`packs/baseline-deny.yaml`** — default deny, allow health + metrics  
2. **`packs/pii-guard.yaml`** — challenge/block PII egress via comms/network  
3. **`packs/change-window.yaml`** — block infra mutate outside maintenance tags  

---

## 13. Verdicts, Challenges & Human-in-the-Loop

### 13.1 Verdict Types

| Verdict | Meaning | Execution |
|---------|---------|-----------|
| `ALLOW` | Permitted | Proceed |
| `BLOCK` | Denied | Do not execute; return error to agent |
| `CHALLENGE` | Needs human approval | Hold; notify; resume on approve/deny |
| `DEFER` | Async review queue | Hold; no synchronous waiter required; timeout policy applies |

### 13.2 Challenge Flow (recommendation)

**Local only (first build):**

- `CHALLENGE` returns verdict immediately to caller with `challengeId`
- Side channel: write to sink + optional webhook
- Approval via CLI: `lexshield challenge approve <id>` / `deny` (local store)
- SDK mode: `shield.guard` awaits challenge until timeout if `await_challenge: true` (default **false** for agents — return challenge error to agent loop)

**Timeouts:** default 1h; `onTimeout: BLOCK` (fail closed).

Hosted challenge UIs (dashboard / Slack) are **deferred with Cloud**.

### 13.3 What Agents See on BLOCK/CHALLENGE

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

## 14. Execution Interception & Integration Modes

### 14.1 Modes

| Mode | How it works | Best for |
|------|--------------|----------|
| **SDK wrap** | Decorator/wrapper around tool functions | Python/TS monoliths |
| **Evaluate-only** | Caller asks for verdict, executes itself | Custom runtimes |
| **Local proxy** | HTTP proxy `/execute` forwards if ALLOW | Polyglot / sidecars |

### 14.2 Proxy Semantics (recommendation)

- Proxy is **explicit allowlist of upstream tool endpoints** configured in `lexshield.yaml` — LexShield is not an open forwarder.
- TLS termination local only by default (`127.0.0.1`)
- Forwards original headers except hop-by-hop; adds `X-LexShield-Request-Id`, `X-LexShield-Verdict`
- On BLOCK: HTTP 403 with structured body
- On CHALLENGE: HTTP 202 or 403 with challenge payload — **recommendation: 403 with `verdict: CHALLENGE`** for simpler agent error handling; optional 202 behind flag

### 14.3 Framework Adapters

**MVP**: none in core.  
**Post-MVP contrib**: OpenAI Agents SDK, LangChain tools, CrewAI, Vercel AI SDK `tools`.  
Document a 20-line “wrap your tool” pattern so users don’t wait.

---

## 15. SDKs (Python & TypeScript)

### 15.1 Python (primary)

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

### 15.2 TypeScript

**Package**: `@latticeag/lexshield`  
**Runtime**: Node 20+; edge-friendly core evaluate without Node FS (inject config)

```ts
import { Shield } from '@latticeag/lexshield';

const shield = await Shield.fromConfig('lexshield.yaml');

export const sendEmail = shield.guard('send_email', async (args) => { ... });
```

### 15.3 Versioning & Compatibility

- Shared JSON schemas for Policy / Verdict / Trace in `/schemas`
- Golden tests ensure Python and TS engines produce same verdict on fixture suite
- **Recommendation**: implement **policy engine once in a shared form** long-term (Rust/WASM or TS core). **MVP: duplicate carefully with shared fixtures** — faster ship; plan WASM core for v0.3+

---

## 16. CLI Surface

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

## 17. Local API & Proxy

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

## 18. Deferred: LexShield Cloud

**Status: out of scope for the first build.**

A future hosted control plane *may* add:

- Versioned policy distribution across teams
- Long-term trace storage/search and alerts
- Org/API keys, invite onboarding, dashboard

**Suggested future stack (when revisited):** Cloudflare Workers + Durable Objects + D1 + R2 + Next.js dashboard.

Until then: policies and traces stay on the user’s machine / git / their own sinks (file, HTTP, OTLP). Do not scaffold `packages/cloud` in the first build.

---

## 19. Data Model

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

## 20. Configuration Schema

### 20.1 `lexshield.yaml` (canonical)

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

### 20.2 Environment Variables

| Var | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | LLM classifier |
| `OPENAI_BASE_URL` | Compatible endpoint |
| `LEXSHIELD_LOCAL_TOKEN` | Local API auth |
| `LEXSHIELD_LOG_LEVEL` | debug/info/warn/error |

---

## 21. Architecture & Request Pipeline

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

### 21.1 Per-request steps

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

## 22. Performance, Caching & Reliability

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

## 23. Security & Threat Model

### 23.1 Trust Boundaries

| Boundary | Trust assumption |
|----------|------------------|
| Caller identity | **Host application authenticates**; LexShield trusts provided `caller` claims |
| Policy files | Trusted operators / git |
| LLM provider | Sees redacted args; treat as semi-trusted |
| Local server | Localhost by default; token optional |

### 23.2 Threats & Mitigations

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

### 23.3 Security Guarantees (honest)

LexShield **cannot** guarantee safety against all adversarial prompts. It **does** provide defense-in-depth, auditability, and policy enforcement points.

---

## 24. Privacy, Compliance & Data Handling

**Recommendations:**

- **Data minimization**: traces store redacted arguments by default (`trace_arguments: redacted | hash | full`) — default **redacted**
- **Retention**: local unbounded (user’s disk / their sinks)
- **Training**: never send customer data anywhere except user-configured LLM/OTLP endpoints
- **PII**: customers responsible for what they put in tool args; we provide redaction helpers
- Hosted retention/region/DPA topics apply only when/if Cloud is built later

---

## 25. Observability & Audit

### 25.1 Traces

- Every evaluate produces a Trace (Appendix C)
- Local: NDJSON; optional HTTP/OTLP export to the user’s stack

### 25.2 Metrics (local counters)

- `lexshield_evaluations_total{verdict}`
- `lexshield_classify_duration_ms{classifier}`
- `lexshield_policy_match_total{rule_id}`
- `lexshield_sink_errors_total`
- `lexshield_llm_circuit_open`

### 25.3 OpenTelemetry

- Emit span `lexshield.evaluate` with attributes: tool, intent, verdict, rule id, duration
- Export via OTLP/HTTP sink config

### 25.4 Alerts

- Not built-in for first build — users alert off their own log/OTLP pipeline
- Optional: document a sample Grafana/Datadog query on OTLP attributes

---

## 26. Error Handling & Failure Modes

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

## 27. Testing Strategy

### 27.1 Layers

1. **Unit**: expression parser, glob match, redaction, priority resolution  
2. **Golden fixtures**: JSON request + policy → expected verdict (shared Py/TS)  
3. **Classifier**: deterministic rules; LLM with recorded HTTP cassettes (VCR)  
4. **SDK integration**: decorator blocks/allows  
5. **CLI**: snapshot tests for `check`/`evaluate`  
6. **Contract/security**: org isolation N/A until Cloud; focus on redaction + fail-closed tests

### 27.2 Security regression fixtures (must-have)

- Exfil via `send_email` with PII body  
- `http_request` to suspicious host  
- Delete in production without challenge  
- Benign health check still ALLOW  

### 27.3 CI

- Lint + typecheck + unit + golden on every PR  
- No live LLM calls in CI (cassettes only)

---

## 28. Repository & Monorepo Layout

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

## 29. Tech Stack Recommendations

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

## 30. Developer Experience & Documentation

### 30.1 Must-have docs (first build)

1. Quickstart (5 minutes)  
2. Policy authoring guide  
3. Intent catalog reference  
4. SDK reference (Py + TS)  
5. Security model & limitations  
6. CI example (`lexshield check` in GitHub Actions)

### 30.2 Examples

- Minimal Python tool guard  
- Block exfil demo  
- Challenge flow demo  
- CI `lexshield check` in GitHub Actions  

### 30.3 Telemetry (OSS)

**v0.1: none.** No phone-home. Revisit opt-in anonymous telemetry in v0.2.

---

## 31. Go-to-Market (OSS)

**First build is free MIT OSS. No pricing page, no seats, no Cloud tiers.**

### 31.1 Launch motion

1. Public GitHub repo + clear README/quickstart  
2. Post to agent/security communities (HN, relevant Discords, X)  
3. Content: “OPA for agent tools” + demo GIFs of block/challenge  
4. Collect design-partner feedback via GitHub Issues / Discord  

### 31.2 Design Partner Profile

- Already running agents with ≥3 production tools  
- Has a security/platform owner  
- Willing to share anonymized false-positive feedback  

### 31.3 Monetization

Deferred. Revisit Cloud/support only after OSS traction and clear demand for hosted control plane.

---

## 32. MVP Milestones (OSS First Build)

> Sequenced work packages with hard deliverables. No Cloud milestone.

| Mile | Focus | Deliverable | Exit criteria |
|------|-------|-------------|---------------|
| **M1** | Policy engine + deterministic classifier | YAML load, match, ALLOW/BLOCK, unit+golden tests | Fixtures pass; `check` works |
| **M2** | Python SDK + local API | `Shield.guard`, FastAPI `/evaluate`, `/healthz` | End-to-end block demo |
| **M3** | LLM classifier + taxonomy | OpenAI-compatible classify, built-in intents, redaction | Cassette-tested classify |
| **M4** | CLI + traces + challenges | `init/check/run/evaluate/traces/challenge`, NDJSON sink | 5-min quickstart works offline |
| **M5** | TypeScript SDK + proxy | npm package, `/execute` proxy, shared fixtures parity | Same golden verdicts |
| **M6** | Docs, packs, examples, polish | Packs YAML, 3 demos, README, security docs, CI example, Appendix D checklist | Tag `v0.1.0` green |

**Authoritative scope:** [§9 Feature Freeze](#9-v01-feature-freeze-specific). If a feature is not IN there, do not build it in these milestones.

---

## 33. Post-MVP Roadmap

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

## 34. Open Questions (with Recommendations)

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

## 35. Decision Log

| Decision | Recommendation | Status |
|----------|----------------|--------|
| First build shape | **OSS only** — no SaaS | **Locked** |
| v0.1 feature set | §9 freeze (IN/OUT/demos/packs) | **Locked** |
| Intent catalog size | **24** built-ins | **Locked** |
| Challenge SDK default | Raise; no await | **Locked** |
| Proxy deny status | HTTP **403** for BLOCK/CHALLENGE/DEFER | **Locked** |
| Telemetry in v0.1 | **None** (defer opt-in to v0.2) | **Locked** |
| Primary languages | Python first, TypeScript second | **Agreed** |
| Classifier fallback | Deterministic → LLM (embed later) | **Agreed** |
| Default verdict posture | `BLOCK` (default-deny) | **Agreed** |
| License | MIT | **Agreed** |
| LexShield Cloud | Deferred post-OSS | **Locked** |
| Framework adapters in core | No | **Locked** |
| LLM classifier | OpenAI-compatible; 2s timeout; `gpt-4o-mini` default | **Locked** |
| Shared evaluation core | Fixtures now; WASM later | **Recommended** |
| Local server default host | `127.0.0.1` only | **Locked** |
| Trace args default | Redacted | **Locked** |
| CLI language | Python/Typer | **Locked** |
| Expression language | Frozen subset §9.5 | **Locked** |

---

## 36. Build Readiness

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

> Full YAML below is **normative for v0.1** (may tweak reason strings, not semantics).

### A.1 `baseline-deny`

```yaml
version: 1
id: baseline-deny
name: Baseline default-deny
description: Allow health/ping only; challenge prod deletes; block secret exposure and exfil.
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

  - id: challenge-delete-prod
    name: Challenge destructive actions in production
    priority: 200
    match:
      environments: ["production"]
      intents: ["infra.delete.resource", "data.delete.record"]
    verdict: CHALLENGE
    reason: "Destructive action in production requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-secret-exposure
    name: Block secret exposure
    priority: 300
    match:
      intents: ["security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible secret exposure in tool arguments"

  - id: block-exfil
    name: Block exfiltration
    priority: 300
    match:
      intents: ["data.exfiltrate"]
    verdict: BLOCK
    reason: "Possible data exfiltration"
```

### A.2 `pii-guard`

```yaml
version: 1
id: pii-guard
name: PII egress guard
description: Extends baseline; challenges external comms when tagged pii; blocks non-allowlisted HTTP.
defaultVerdict: BLOCK
rules:
  - id: allow-health
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"

  - id: challenge-pii-email
    priority: 220
    match:
      intents: ["comms.send.email", "comms.send.external"]
      tags:
        data_class: ["pii"]
    verdict: CHALLENGE
    reason: "Sending PII requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-http-non-allowlist
    priority: 250
    match:
      intents: ["network.request.http"]
      expression: '!(args.url startsWith "https://api.mycompany.com/")'
    verdict: BLOCK
    reason: "HTTP to non-allowlisted host"

  - id: block-secret-exposure
    priority: 300
    match:
      intents: ["security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible secret exposure in tool arguments"

  - id: block-exfil
    priority: 300
    match:
      intents: ["data.exfiltrate"]
    verdict: BLOCK
    reason: "Possible data exfiltration"
```

### A.3 `change-window`

```yaml
version: 1
id: change-window
name: Infra change window
description: Infra mutate/provision in production requires change_ticket tag; otherwise challenge.
defaultVerdict: BLOCK
rules:
  - id: allow-health
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"

  - id: allow-infra-with-ticket
    priority: 180
    match:
      environments: ["production"]
      intents: ["infra.mutate.resource", "infra.provision.resource"]
      expression: 'tags.change_ticket != ""'
    verdict: ALLOW
    reason: "Change ticket present"

  - id: challenge-infra-prod
    priority: 200
    match:
      environments: ["production"]
      intents: ["infra.mutate.resource", "infra.provision.resource", "infra.delete.resource"]
    verdict: CHALLENGE
    reason: "Production infra change requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-secret-exposure
    priority: 300
    match:
      intents: ["security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible secret exposure in tool arguments"
```

### A.4 Companion `rules.yaml` (deterministic) — ship with `init`

```yaml
version: 1
tool_map:
  health_check: network.request.health
  ping: network.request.health
  send_email: comms.send.email
  send_slack: comms.send.slack
  http_request: network.request.http
  execute_sql: data.query.sql
  delete_resource: infra.delete.resource
  create_resource: infra.provision.resource
  update_resource: infra.mutate.resource
  create_charge: finance.charge.create
  transfer_funds: finance.transfer.create
  run_shell: code.execute.shell
  write_file: code.write.repo
patterns:
  - name: aws_access_key
    match:
      any_arg_regex: "AKIA[0-9A-Z]{16}"
    intent: security.secret_exposure
    confidence: 0.98
  - name: openai_sk
    match:
      any_arg_regex: "sk-(proj-)?[a-zA-Z0-9]{20,}"
    intent: security.secret_exposure
    confidence: 0.98
```

---

## Appendix B — Built-in Intent Catalog (v0.1)

> **Frozen at 24 intents** for `v0.1.0`. Severity 1–100.  
> Users extend via `custom.<name>` in `taxonomy.yaml` (not listed here).

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
    "arguments_redacted": {"to": "a@b.com", "subject": "…", "body": "[REDACTED_AWS_KEY]"},
    "context": {"environment": "production", "conversationId": "c1"}
  },
  "classifications": [
    {"intent": "security.secret_exposure", "confidence": 0.98, "classifier": "deterministic:v1", "alternatives": []}
  ],
  "verdict": {
    "decision": "BLOCK",
    "matchedRuleId": "block-secret-exposure",
    "reason": "Possible secret exposure in tool arguments",
    "durationMs": 3,
    "policyVersion": "1"
  },
  "outcome": "BLOCKED",
  "outcomeAt": "2026-07-11T12:00:00.003Z"
}
```

---

## Appendix D — v0.1 Acceptance Checklist

Ship `v0.1.0` only when all boxes pass:

**Engine**
- [ ] Default-deny packs block unknown tools
- [ ] Highest priority rule wins; golden fixtures ≥ 50 green on Python
- [ ] Deterministic secret pattern → `security.secret_exposure` → BLOCK
- [ ] LLM path cassette-tested; timeout 2s; no key → skip LLM cleanly
- [ ] Redaction applied to LLM payload and NDJSON traces

**Python SDK + API + CLI**
- [ ] `@shield.guard` raises on BLOCK/CHALLENGE
- [ ] `lexshield init && check && evaluate` works offline
- [ ] `/evaluate` + `/execute` + `/traces` + challenge resolve work on 127.0.0.1:8787
- [ ] Bind-all refused without explicit flag

**TS**
- [ ] Golden fixtures 100% match Python decisions
- [ ] `evaluate` + `guard` documented example passes

**Content / docs**
- [ ] 3 packs + 3 demos runnable without API key
- [ ] README 5-minute quickstart verified on clean machine
- [ ] `docs/security.md` states probabilistic limits honestly

**Release**
- [ ] PyPI + npm 0.1.0 published from tag
- [ ] MIT LICENSE present

---

## Document History

| Version | Date | Notes |
|---------|------|-------|
| 0.1 | 2026-07-11 | Initial SPEC committed to main |
| 0.2 | 2026-07-11 | Expanded planning SPEC |
| 0.3 | 2026-07-11 | OSS-first lock; SaaS deferred |
| 0.4 | 2026-07-11 | **v0.1 feature freeze**: exact IN/OUT, demos, expressions, redaction, packs YAML, acceptance checklist |

---

*End of SPEC.md — planning only; implementation starts when build is kicked off.*
