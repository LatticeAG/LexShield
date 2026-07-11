# LexShield

**The open-source policy firewall for agent tool calls.**

LexShield sits between an AI agent and its tool fleet, classifies the intent behind each tool call, and enforces allow/block/challenge policy **before** execution. Fully local-first — deterministic evaluation works with no API keys.

- **License**: MIT
- **Publisher**: [LatticeAG](https://latticeag.com)
- **Specification**: [SPEC.md](./SPEC.md)

## Quickstart (5 minutes, deterministic-only)

No API key required. These steps were verified against this repository.

```bash
# 1. Clone and install (Python SDK + CLI)
git clone https://github.com/latticeag/lexshield.git
cd lexshield
uv sync

# 2. Scaffold config in a scratch directory
mkdir /tmp/lexshield-demo && cd /tmp/lexshield-demo
lexshield init --pack baseline-deny    # uses uv/venv lexshield on PATH after uv sync

# 3. Validate policy (CI-friendly)
lexshield check --strict

# 4. Evaluate a tool call offline
lexshield evaluate \
  --tool send_email \
  --args '{"to":"user@example.com","body":"AKIA0123456789012345"}' \
  --json
# → "decision": "BLOCK", "matchedRuleId": "block-secret-exposure"

lexshield evaluate --tool health_check --args '{}' --json
# → "decision": "ALLOW", "matchedRuleId": "allow-health"
```

> **Tip:** After `uv sync`, run CLI commands via `uv run lexshield …` from the repo root, or use the `.venv/bin/lexshield` binary directly.

### Path outline

1. **Install** — `uv sync` (monorepo) or `pip install lexshield` (PyPI)
2. **Init** — `lexshield init` writes `lexshield.yaml`, `policy.yaml`, `rules.yaml`
3. **Check** — `lexshield check` validates policy in CI (`uv run lexshield-check-packs` for all packs)
4. **Evaluate** — `lexshield evaluate` or `Shield.guard` before tool execution
5. **Trace** — verdicts append to `traces.ndjson` when a file sink is configured

### TypeScript evaluate

```bash
pnpm install
pnpm --filter @latticeag/lexshield build
cd examples/ts-evaluate && pnpm exec tsx index.ts
```

### Challenge flow (human approval)

```bash
cd examples/python-challenge-delete
uv run --project ../.. python main.py
# prints challenge_id

lexshield challenge approve <challenge_id>
lexshield challenge list   # no open challenges
```

See [examples/README.md](./examples/README.md) and [docs/cli.md](./docs/cli.md).

## Documentation

| Doc | Topic |
|-----|-------|
| [docs/policy.md](./docs/policy.md) | Policy authoring |
| [docs/intents.md](./docs/intents.md) | Intent catalog |
| [docs/sdk-python.md](./docs/sdk-python.md) | Python SDK |
| [docs/sdk-typescript.md](./docs/sdk-typescript.md) | TypeScript SDK |
| [docs/integrations.md](./docs/integrations.md) | Framework adapters (contrib) |
| [docs/cli.md](./docs/cli.md) | CLI reference |
| [docs/security.md](./docs/security.md) | Threat model |

## Examples

| Example | Description |
|---------|-------------|
| [python-block-exfil](./examples/python-block-exfil/) | `BLOCK` on AWS key in `send_email` |
| [python-challenge-delete](./examples/python-challenge-delete/) | `CHALLENGE` prod delete + CLI approve |
| [ts-evaluate](./examples/ts-evaluate/) | TypeScript `evaluate()` demo |

## Framework adapters (contrib)

Community copy-paste patterns for Vercel AI SDK, LangChain, and OpenAI Agents — **not officially supported**. See [contrib/](./contrib/) and [docs/integrations.md](./docs/integrations.md).

## Monorepo layout

| Package | Path | Role |
|---------|------|------|
| Python engine | `packages/engine-py` | Policy engine, classifiers |
| Python CLI | `packages/cli` | `lexshield` Typer CLI |
| TypeScript SDK | `packages/engine-ts` | `@latticeag/lexshield` |
| Policy packs | `packs/` | `baseline-deny`, `pii-guard`, `change-window` |
| Golden fixtures | `fixtures/golden/` | Cross-engine regression scenarios |

## Development

```bash
# Python
uv sync
uv run pytest

# TypeScript
pnpm install
pnpm test
pnpm test:golden

# Policy packs
uv run lexshield-check-packs
```

CI runs all of the above on every push — see [.github/workflows/ci.yml](./.github/workflows/ci.yml).

See [SPEC.md](./SPEC.md) for architecture, policy language, intent taxonomy, and v0.1 acceptance criteria.
