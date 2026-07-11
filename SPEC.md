# LexShield Specification

## 1. Problem & User Value

As AI agents gain the ability to call external tools, every tool invocation becomes a security, compliance, and cost event. A single misclassified or malicious prompt can cause an agent to exfiltrate data, delete resources, spend money, or violate policy. Existing authorization layers were designed for humans (RBAC, OAuth scopes) and do not understand the *intent* expressed in natural language that drives an agent action.

LexShield is an agent intent router and policy firewall. It sits between an agent and its tool fleet, classifies the intent behind each tool call, and enforces allow/block policy before execution. It gives operators a single control plane for what agents are allowed to do, why they are doing it, and what happens when they try something disallowed.

## 2. Target User

- **Primary**: Platform and security engineers building agent runtime infrastructure at startups and enterprises.
- **Secondary**: Developers of agent frameworks and vertical AI products that need to prove policy compliance to customers.
- **Buyer context**: Teams that already have agents calling real tools (databases, APIs, SaaS actions) and need guardrails before production scale.

## 3. Product Positioning

- **Open-source CLI and SDK** (MIT): `LexShield` — install locally, run as a library or standalone proxy, inspect and contribute to the engine.
- **Invite-only hosted SaaS**: `LexShield Cloud` — managed policy backend, audit log retention, multi-team controls, SLA. Hosted by LatticeAG.
- **Pattern**: trust through OSS transparency, speed and moat through SaaS.

## 4. Core Concepts

| Concept | Definition |
|---------|------------|
| **Intent** | The high-level goal inferred from an agent tool-call request (e.g., `read_customer_record`, `send_notification`, `delete_resource`). |
| **Signal** | A raw input to classification: tool name, arguments, conversation history, request metadata, prior tool calls. |
| **Policy** | A set of allow/block rules matched against intent and signal context. |
| **Shield** | A configured instance of LexShield bound to a policy and one or more tools. |
| **Verdict** | The decision output: `ALLOW`, `BLOCK`, `CHALLENGE`, or `DEFER`, with reasoning and matched rules. |
| **Trace** | An immutable record of a tool-call request, its classification, verdict, and outcome. |

## 5. Core Features

### 5.1 Intent Classification
- Classify tool-call requests into a customer-defined or built-in intent taxonomy.
- Support multiple classifiers: deterministic (pattern/rule), heuristic (keyword/embedding), and LLM-based (local or remote).
- Use conversation history and prior tool calls as classification context.
- Output confidence, alternative intents, and reasoning.

### 5.2 Policy Engine
- Define policies as YAML/JSON files or through the SaaS dashboard.
- Rule dimensions: intent, tool, caller identity, environment, time, data sensitivity, rate, and custom tags.
- Verdict types: `ALLOW`, `BLOCK`, `CHALLENGE` (require human approval), `DEFER` (async review).
- Rule ordering, overrides, and default-deny posture.

### 5.3 Execution Interception
- Standalone proxy mode that intercepts tool calls over HTTP(S).
- SDK hooks for Python (async-first) and TypeScript that wrap tool functions.
- Middleware adapters for popular agent frameworks (OpenAI Agents, LangChain, CrewAI via plugin/contrib).

### 5.4 Audit & Observability
- Emit structured traces for every request/verdict/outcome triple.
- OpenTelemetry-compatible span export.
- Local log sink, file sink, and SaaS upload sink.
- Dashboard views: request volume, top blocked intents, policy hit counts, latency percentiles.

### 5.5 Local-First Development
- Run the full engine offline with built-in classifiers and local policy files.
- No SaaS account required for local evaluation and unit testing.
- Hot-reload policy files in development.

### 5.6 SaaS Control Plane
- Hosted policy distribution, versioned policy sets, and team-level policy scopes.
- Long-term trace storage, search, and alerting.
- API keys and organization scoping.
- Slack/email alerts for BLOCK and CHALLENGE spikes.

## 6. Non-Goals

- LexShield is not a generic API gateway (no load balancing, rate limiting as primary value, or request rewriting).
- It is not an agent itself; it does not plan, reason, or execute workflows.
- It is not a secrets manager; credentials remain the responsibility of the caller or an external vault.
- It does not replace human-in-the-loop review for high-stakes actions; it formalizes and routes those reviews.
- No mobile apps, browser extensions, or consumer-facing clients in MVP.

## 7. Data Model

```ts
interface Shield {
  id: string;
  name: string;
  policyId: string;
  classifierIds: string[];
  sinks: SinkConfig[];
  createdAt: string;
  updatedAt: string;
}

interface Policy {
  id: string;
  name: string;
  version: string;
  description?: string;
  defaultVerdict: VerdictType;
  rules: PolicyRule[];
}

interface PolicyRule {
  id: string;
  name: string;
  priority: number;
  match: RuleMatch;
  verdict: VerdictType;
  reason: string;
  challenge?: ChallengeConfig;
}

interface RuleMatch {
  intents?: string[];
  tools?: string[];
  callers?: string[];
  environments?: string[];
  tags?: Record<string, string[]>;
  expression?: string; // CEL-style boolean expression
}

interface ToolCallRequest {
  id: string;
  shieldId: string;
  timestamp: string;
  caller: Caller;
  tool: ToolRef;
  arguments: Record<string, unknown>;
  context: CallContext;
}

interface Caller {
  id: string;
  type: 'user' | 'agent' | 'service_account';
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
  alternatives: { intent: string; confidence: number }[];
  classifier: string;
  reasoning?: string;
}

interface Verdict {
  requestId: string;
  decision: 'ALLOW' | 'BLOCK' | 'CHALLENGE' | 'DEFER';
  matchedRuleId?: string;
  reason: string;
  classifications: Classification[];
  durationMs: number;
}

interface Trace {
  request: ToolCallRequest;
  verdict: Verdict;
  outcome?: 'EXECUTED' | 'BLOCKED' | 'CHALLENGED' | 'DEFERRED' | 'ERROR';
  outcomeAt?: string;
  metadata?: Record<string, unknown>;
}

type VerdictType = 'ALLOW' | 'BLOCK' | 'CHALLENGE' | 'DEFER';

interface SinkConfig {
  type: 'stdout' | 'file' | 'http' | 'saas';
  options: Record<string, unknown>;
}
```

## 8. API / Integration Surface

### 8.1 LexShield Local API

Base path: `http://127.0.0.1:8787` (default proxy mode).

```
POST /v1/shields/:shieldId/evaluate
  body: ToolCallRequest
  returns: Verdict

POST /v1/shields/:shieldId/execute
  body: ToolCallRequest
  behavior: evaluate + forward allowed calls to configured tool endpoint
  returns: { verdict: Verdict, result?: unknown }

GET /v1/shields/:shieldId/policy
  returns: Policy

POST /v1/shields/:shieldId/policy/reload
  behavior: reload local policy file
  returns: { ok: true }

GET /v1/traces
  query: limit, offset, decision, intent, tool
  returns: Trace[]

GET /healthz
  returns: { status: "ok" }
```

### 8.2 LexShield Cloud API

```
POST /v1/org/:orgId/policies
  body: Policy
  returns: Policy

GET /v1/org/:orgId/policies/:policyId
  returns: Policy

POST /v1/org/:orgId/policies/:policyId/publish
  behavior: create immutable policy version
  returns: { version: string }

POST /v1/org/:orgId/evaluate
  body: ToolCallRequest + policyId
  returns: Verdict

GET /v1/org/:orgId/traces
  query: full-text search + filters
  returns: Trace[] (paginated)

POST /v1/org/:orgId/alerts
  body: AlertRule
  returns: AlertRule
```

### 8.3 SDK Methods (Python / TypeScript)

```python
from lexshield import Shield

shield = Shield.from_config("lexshield.yaml")

# As a decorator
@shield.guard
async def send_email(to: str, subject: str, body: str):
    ...

# As an explicit call
verdict = await shield.evaluate(
    tool="send_email",
    arguments={"to": "...", "subject": "...", "body": "..."},
    caller={"id": "agent-1", "type": "agent"},
    context={"conversationId": "conv-42"}
)
```

```ts
import { Shield } from '@latticeag/lexshield';

const shield = await Shield.fromConfig('lexshield.yaml');

const verdict = await shield.evaluate({
  tool: 'send_email',
  arguments: { to: '...', subject: '...', body: '...' },
  caller: { id: 'agent-1', type: 'agent' },
  context: { conversationId: 'conv-42' },
});
```

### 8.4 CLI Commands

```bash
lexshield init                     # Create lexshield.yaml and sample policy
lexshield check                    # Validate policy and classifier config
lexshield run                      # Start local proxy/API server
lexshield evaluate --tool ...      # Evaluate a single request from stdin or flags
lexshield traces                   # Query local traces
lexshield login                    # Authenticate CLI with LexShield Cloud
lexshield policy push              # Upload local policy to cloud
lexshield policy pull              # Download cloud policy to local file
lexshield version
```

### 8.5 Configuration File (`lexshield.yaml`)

```yaml
version: 1
shield:
  name: production-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
    - type: llm
      model: openai:gpt-4o-mini
      api_key_env: OPENAI_API_KEY
  sinks:
    - type: stdout
    - type: file
      path: ./traces.ndjson
    - type: saas
      org_id_env: LEXSHIELD_ORG_ID
      api_key_env: LEXSHIELD_API_KEY
server:
  host: 127.0.0.1
  port: 8787
```

## 9. Security Model

- **Default-deny posture**: any request not explicitly allowed is blocked unless the policy says otherwise.
- **Policy immutability**: published policy versions are immutable; changes create a new version.
- **Caller identity**: policy decisions rely on caller claims; callers must be authenticated by the consuming application before reaching LexShield.
- **Secrets**: LexShield never stores tool credentials. It may store API keys for classifiers and SaaS sinks only with explicit configuration.
- **Data residency**: SaaS traces are scoped to an organization. Region selection is available in paid tiers.
- **Audit integrity**: traces are append-only and signed in SaaS; local traces can be exported for external storage.
- **No prompt injection immunity**: classification is probabilistic. LexShield reduces risk but cannot guarantee safety against adversarial inputs.

## 10. Deployment Model

### Local / Self-Hosted
- Install via `pip install lexshield` or `npm install @latticeag/lexshield`.
- Run CLI as a local proxy or embed the SDK directly in an agent application.
- Policy files live in the customer's repository or filesystem.

### LexShield Cloud
- Multi-tenant SaaS hosted by LatticeAG on Cloudflare Workers / Durable Objects.
- Policy distribution via signed HTTPS.
- Trace ingestion via OTLP or direct API.
- Invite-only onboarding; free tier for small teams, paid tiers for organizations.

### Hybrid
- Development and CI use the OSS engine with local policies.
- Production uses the same engine but sources policies and sinks traces from LexShield Cloud.

## 11. Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Agent / SDK    │─────▶│  LexShield       │─────▶│  Tool Endpoint  │
│                 │      │  - Classify      │      │  (SaaS, DB, API)│
└─────────────────┘      │  - Policy Match  │      └─────────────────┘
                         │  - Verdict       │
                         │  - Trace / Sink  │
                         └──────────────────┘
                                   │
                                   ▼
                         ┌──────────────────┐
                         │  LexShield Cloud │
                         │  (optional SaaS) │
                         └──────────────────┘
```

**Pipeline per request**:
1. Receive tool-call request (SDK, proxy, or Cloud API).
2. Resolve caller and context.
3. Run configured classifiers in order (fast deterministic first, LLM fallback).
4. Merge classifications into a ranked intent list.
5. Evaluate policy rules against intent + signal context.
6. Emit verdict.
7. If `ALLOW`, forward to tool endpoint (proxy/execute) or return and let caller execute (SDK).
8. If `BLOCK`, return rejection with reason.
9. If `CHALLENGE`/`DEFER`, route to human-in-the-loop queue.
10. Record trace to configured sinks.

## 12. Performance & Caching

- Deterministic classification targets p99 < 1 ms.
- Embedding classification targets p99 < 50 ms with local cache.
- LLM classification targets p99 < 500 ms; optional async classification for non-blocking paths.
- Policy compilation: load and compile rules into a decision graph at startup; hot-reload in development.
- Classifier result cache keyed by request fingerprint with configurable TTL (default 60 seconds).
- Trace sinks are asynchronous; tool execution is never blocked by sink writes.

## 13. 6-Day MVP Milestones

| Day | Milestone | Deliverable |
|-----|-----------|-------------|
| M1 | Policy engine + deterministic classifier | YAML policy parser, rule matcher, `ALLOW`/`BLOCK` verdicts, unit tests. |
| M2 | SDK hook (Python) + local API | `@shield.guard` decorator, FastAPI-style `/evaluate` endpoint, local server. |
| M3 | LLM classifier + intent taxonomy | OpenAI classifier integration, built-in intent catalog, confidence scoring. |
| M4 | CLI + traces | `init`, `check`, `run`, `evaluate`, `traces` commands, ndjson trace sink. |
| M5 | TypeScript SDK + proxy mode | npm package, HTTP proxy that forwards allowed tool calls, parity with Python SDK. |
| M6 | Cloud scaffold + invite flow | Cloudflare Workers API skeleton, org/policy/traces tables, invite-only signup page. |

## 14. Pricing & Positioning

- **Open-source CLI/SDK**: free forever under MIT.
- **LexShield Cloud Free**: 1 organization, 1 shield, 10k evaluations/month, 7-day trace retention, community support.
- **LexShield Cloud Pro**: $99/seat/month — unlimited shields, 1M evaluations/month included, 90-day trace retention, Slack alerts, SSO.
- **LexShield Cloud Enterprise**: custom — unlimited evaluations, custom regions, audit exports, SLA, dedicated support.
- **Positioning statement**: "The policy firewall for agent tool calls — open source for transparency, cloud for control."

## 15. Decisions

| Decision | Recommendation | Status |
|----------|----------------|--------|
| Primary languages | Python first (agent ecosystem), TypeScript second (web/agent frameworks). | Agreed |
| Default classifier fallback | Deterministic → embedding → LLM. | Agreed |
| Default verdict posture | `BLOCK` (default-deny). | Agreed |
| SaaS platform | Cloudflare Workers + Durable Objects. | Agreed |
| License | MIT. | Agreed |
| Initial framework adapters | OpenAI Agents SDK and LangChain via contrib repo; not in core MVP. | Pending review |
| Embedded vs remote LLM classifier | Remote first (OpenAI-compatible); local option post-MVP. | Pending review |
