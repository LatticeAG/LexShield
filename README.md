# LexShield 🛡️

<p align="center">
  <a href="https://github.com/LatticeAG/LexShield/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/LatticeAG/LexShield?style=for-the-badge" alt="License" />
  </a>
  <a href="https://github.com/LatticeAG/LexShield">
    <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  </a>
  <a href="https://github.com/LatticeAG/LexShield">
    <img src="https://img.shields.io/badge/TypeScript-5.7%2B-blue?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
  </a>
  <a href="https://github.com/LatticeAG/LexShield/stargazers">
    <img src="https://img.shields.io/github/stars/LatticeAG/LexShield?style=for-the-badge" alt="GitHub stars" />
  </a>
  <a href="https://github.com/LatticeAG/LexShield/issues">
    <img src="https://img.shields.io/github/issues/LatticeAG/LexShield?style=for-the-badge" alt="GitHub issues" />
  </a>
</p>

<p align="center">
  <b>The open-source policy firewall for AI agent tool calls.</b><br/>
  Classify. Enforce. Audit. Before execution.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#why-lexshield">Why LexShield</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#features">Features</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#monorepo-layout">Layout</a> ·
  <a href="#acceptance">Testing</a> ·
  <a href="#known-issues">Known Issues</a> ·
  <a href="#documentation">Docs</a>
</p>

---

LexShield sits between an AI agent and its tool fleet, classifies the intent behind each tool call, and enforces allow/block/challenge policy **before** execution. Fully local-first -- deterministic evaluation works with no API keys.

Built for AI safety teams and agent platform operators who need a defense-in-depth layer between autonomous agents and sensitive tool surfaces. MIT-licensed, self-hostable, with zero mandatory external dependencies.

## Why LexShield

- **Default-deny security** - every tool call is blocked until a policy explicitly allows it. No trust-once, permit-forever footguns.
- **Deterministic by default** - no API key required for core policy enforcement. Regex pattern matching and intent classification run locally, every time.
- **Multi-verdict policy engine** - `ALLOW`, `BLOCK`, `CHALLENGE`, and `DEFER` give you graduated control, not binary pass/fail.
- **Human-in-the-loop** - `CHALLENGE` verdicts queue for human approval. Humans review via CLI/API; approvals are delivered to the agent through the local challenge store; webhook notifications are HMAC-signed.
- **Cross-platform SDKs** - Python and TypeScript SDKs with golden parity. Same deterministic behavior, same policy files, same audit traces.
- **Output plane (whole-value, non-streaming)** - After a tool or model produces a complete value, LexShield evaluates that emission before it leaves the agent boundary. Actions are `RELEASE`, `REDACT`, `REPLACE`, `DROP`, and `QUARANTINE`. Streaming token-by-token enforcement is not in v0.2.0.
- **Audit-native** - every evaluation appends to `traces.ndjson` with verdict, matched rule, and intent classification. Production-ready observability without extra tooling.

### How LexShield is different

- **Pre-execution, not post-hoc** - most agent safety tools *monitor* tool calls. LexShield *prevents* them. The shield evaluates before the tool runs, not after.
- **Intent classification layer** - not just URL/regex blocking. LexShield classifies the semantic intent of each tool call (`send_email`, `delete_resource`, `read_fs`) and applies intent-specific policies.
- **Local-first, no vendor lock-in** - the entire policy engine runs on your hardware with zero external API calls. No sending agent telemetry to a third party to get a verdict.

## Quick Start (5 minutes, deterministic-only)

No API key required.

```bash
# 1. Clone and install
git clone https://github.com/LatticeAG/LexShield.git
cd LexShield
uv sync

# 2. Scaffold config in a scratch directory
mkdir /tmp/lexshield-demo && cd /tmp/lexshield-demo
lexshield init --pack baseline-deny
# -> writes lexshield.yaml, policy.yaml (4 rules), rules.yaml

# 3. Validate policy (CI-friendly)
lexshield check --strict
# -> OK policy=.../policy.yaml (exit 0)

# 4. Evaluate a tool call offline
lexshield evaluate \
  --tool send_email \
  --args '{"to":"user@example.com","body":"key AKIAIOSFODNN7EXAMPLE"}' \
  --json
# -> "decision": "BLOCK", "matchedRuleId": "block-secret-exposure"

lexshield evaluate --tool health_check --args '{}' --json
# -> "decision": "ALLOW", "matchedRuleId": "allow-health"
```

All outputs above verified against `lexshield 0.2.0` with the `baseline-deny` pack.

### TypeScript evaluate

```bash
pnpm install
pnpm --filter @latticeag/lexshield build
pnpm example:ts-evaluate
```

### Challenge flow (human approval)

```bash
cd examples/python-challenge-delete
uv run --project ../.. python main.py
# end-to-end: CHALLENGE -> CLI approve -> guarded delete succeeds
```

## Architecture

```mermaid
flowchart LR
  Agent["Agent / LLM"]
  Shield["LexShield engine"]
  Classify["Classifiers\n(deterministic + optional LLM)"]
  Policy["Policy YAML\n+ rules.yaml"]
  Tools["Tool upstreams"]
  Traces["Trace sinks\n(stdout / NDJSON)"]
  Challenges["Challenge store\n(.lexshield/challenges)"]

  Agent -->|"ToolCallRequest"| Shield
  Shield --> Classify
  Classify --> Policy
  Policy -->|"ALLOW / BLOCK / CHALLENGE"| Shield
  Shield -->|"ALLOW only"| Tools
  Shield --> Traces
  Shield --> Challenges
```

## Features

### Policy Engine

| Feature | Description |
|---------|------------|
| **Default-deny YAML policies** | Priority rules, globs, tags, and safe expressions. No implicit allow. |
| **Intent classification** | Deterministic tool maps + regex patterns; optional OpenAI-compatible LLM fallback for ambiguous calls. |
| **Multi-verdict system** | `ALLOW`, `BLOCK`, `CHALLENGE`, `DEFER` with audit-friendly reasons for every verdict. |
| **Policy packs** | `baseline-deny`, `pii-guard`, `change-window` -- drop-in policies for common guardrail scenarios. `output-baseline` for the output plane. |

### SDK & CLI

| Feature | Description |
|---------|------------|
| **Python SDK** | `Shield.evaluate`, `@shield.guard`, `evaluate_output` / `guard_output`, `await_challenge`, trace sinks |
| **TypeScript SDK** | `@latticeag/lexshield` with golden parity on deterministic paths; `evaluateOutput` / `guardOutput` |
| **CLI** | `init`, `check`, `evaluate`, `output evaluate`, `run`, `traces`, `challenge`, `packs`, shell completion |
| **Local API** | FastAPI server on `127.0.0.1:8787` -- evaluate, execute, traces, challenge resolve |

### Audit & Observability

| Feature | Description |
|---------|------------|
| **Structured traces** | Every verdict appended to `traces.ndjson` with tool name, args, matched rule, latency |
| **Cross-engine golden parity** | Python and TypeScript engines tested against the same golden fixture suite |
| **Framework adapters** | Community patterns for Vercel AI SDK, LangChain, and OpenAI Agents SDK |

## Configuration

The CLI loads `lexshield.yaml` from the current directory by default; override per-invocation:

```bash
lexshield --config ./lexshield.yaml check --strict
lexshield run --port 8787   # local API on 127.0.0.1:8787
```

| Item | Description |
|------|-------------|
| `lexshield.yaml` | Engine config: policy path, taxonomy, trace sinks, challenge store |
| `policy.yaml` | Priority-ordered rules (default-deny; `baseline-deny` ships 4 rules) |
| `rules.yaml` | Intent classification rules and tool maps |
| `packs/` | Built-in starting points: `baseline-deny`, `pii-guard`, `change-window`, `output-baseline` |
| `lexshield run` | Serves the local FastAPI on `127.0.0.1:8787` (evaluate, execute, traces, challenge resolve) |

Full authoring reference: [docs/policy.md](./docs/policy.md), [docs/output.md](./docs/output.md), [docs/cli.md](./docs/cli.md).

## Monorepo Layout

```text
lexshield/
├── packages/
│   ├── engine-py/          # Python policy engine + classifiers
│   ├── cli/                # lexshield Typer CLI
│   └── engine-ts/          # @latticeag/lexshield (TypeScript)
├── packs/                  # baseline-deny, pii-guard, change-window, output-baseline
├── fixtures/
│   ├── golden/             # Cross-engine regression scenarios (67 files)
│   ├── output-golden/      # Output-plane regression scenarios (14 files)
│   └── redteam/authz/      # Honest recorded outcomes (knownGap)
├── schemas/                # policy, verdict, trace, tool-call-request JSON schemas
├── taxonomy/               # builtin.yaml + output-findings.yaml intent catalog
├── examples/
│   ├── python-block-exfil/       # BLOCK on AWS key in send_email
│   ├── python-challenge-delete/  # CHALLENGE + CLI approve + execution
│   └── ts-evaluate/              # TypeScript evaluate() demo
├── contrib/                # Community framework adapters
├── docs/                   # policy.md, output.md, intents.md, sdk-python.md, sdk-typescript.md, cli.md, security.md
├── SPEC.md                 # Full architecture + policy language spec
├── LICENSE                 # MIT
└── README.md               # This file
```

## Documentation

| Doc | Topic |
|-----|-------|
| [docs/policy.md](./docs/policy.md) | Policy authoring language |
| [docs/output.md](./docs/output.md) | Output plane (whole-value, non-streaming) |
| [docs/intents.md](./docs/intents.md) | Intent catalog and taxonomy |
| [docs/sdk-python.md](./docs/sdk-python.md) | Python SDK reference |
| [docs/sdk-typescript.md](./docs/sdk-typescript.md) | TypeScript SDK reference |
| [docs/integrations.md](./docs/integrations.md) | Framework adapters |
| [docs/cli.md](./docs/cli.md) | CLI command reference |
| [docs/security.md](./docs/security.md) | Threat model and assumptions |

## Acceptance

```bash
# v0.2 acceptance suite
uv sync && uv run pytest && uv run lexshield-check-packs \
  && pnpm install && pnpm test && pnpm test:golden && pnpm test:output-golden \
  && uv run python scripts/acceptance_v02.py
```

Measured on `lexshield 0.2.0`:

| Suite | Result |
|-------|--------|
| `uv run pytest` | 246 passed |
| `pnpm test` (engine-ts, 16 files) | 108 passed |
| `pnpm test:golden` | 3 passed |
| `pnpm test:output-golden` | 15 passed |
| `uv run lexshield-check-packs` | 4 packs/policies OK |

## Development

```bash
# Python
uv sync
uv run pytest

# TypeScript
pnpm install
pnpm test
pnpm test:golden
pnpm test:output-golden

# Policy packs
uv run lexshield-check-packs

# Full acceptance
make acceptance   # scripts/acceptance_v01.py
uv run python scripts/acceptance_v02.py
```

CI runs on every push -- [.github/workflows/ci.yml](./.github/workflows/ci.yml). Tag `v*` triggers release validation.

## Known Issues

- **LLM classifier latency** - When the optional LLM classifier is enabled, evaluation latency increases by 500-2000ms depending on provider. Deterministic-only mode has no such overhead.
- **Large policy trees** - Policy files with 100+ rules are validated and performant, but `lexshield check --strict` may take several seconds for very large rule sets. Break policies into focused packs where possible.
- **Challenge expiry** - Challenge TTL expiry is lazy; it runs on `list_open()`/`await_challenge` polling only. There is no background sweeper.

## License

MIT -- see [LICENSE](./LICENSE). Copyright &copy; 2026 LatticeAG.
