# LexShield

**The open-source policy firewall for agent tool calls.**

LexShield sits between an AI agent and its tool fleet, classifies the intent behind each tool call, and enforces allow/block/challenge policy **before** execution. Fully local-first — no SaaS required.

- **License**: MIT
- **Publisher**: [LatticeAG](https://latticeag.com)
- **Specification**: see [SPEC.md](./SPEC.md) for product scope, APIs, and v0.1 feature freeze

## Quickstart (5 minutes, deterministic-only)

No API key required for the deterministic path.

```bash
# Install (PyPI — coming soon)
pip install lexshield

# Scaffold config + baseline policy pack
lexshield init --pack baseline-deny

# Validate policy
lexshield check

# Evaluate a tool call offline
lexshield evaluate --tool send_email --args '{"to":"user@example.com","body":"AKIA0123456789012345"}' --json
# → BLOCK (security.secret_exposure)

# Allow a health check
lexshield evaluate --tool health_check --args '{}' --json
# → ALLOW
```

### Path outline

1. **Install** — `pip install lexshield` (Python SDK + CLI)
2. **Init** — `lexshield init` writes `lexshield.yaml`, `policy.yaml`, `rules.yaml`
3. **Check** — `lexshield check` validates policy in CI (exit non-zero on errors)
4. **Evaluate** — `lexshield evaluate` or `Shield.guard` decorator before tool execution
5. **Trace** — verdicts append to `traces.ndjson` for audit

For TypeScript: `npm install @latticeag/lexshield` (evaluate + guard parity).

## Monorepo layout

| Package | Path | Role |
|---------|------|------|
| Python engine | `packages/engine-py` | Policy engine, classifiers (source of truth) |
| Python CLI | `packages/cli` | `lexshield` Typer CLI |
| TypeScript SDK | `packages/engine-ts` | `@latticeag/lexshield` evaluate/guard |

## Development

```bash
# Python (uv workspace)
uv sync
uv run pytest

# TypeScript (pnpm workspace)
pnpm install
pnpm -r test
```

See [SPEC.md](./SPEC.md) for architecture, policy language, intent taxonomy, and acceptance criteria.
