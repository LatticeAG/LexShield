# Contributing to LexShield

Thank you for helping improve LexShield. This guide covers local development, testing, and the v0.1 acceptance gate.

## Prerequisites

- **Python** 3.11+
- **[uv](https://docs.astral.sh/uv/)** — Python workspace and dependency management
- **Node.js** 20+
- **[pnpm](https://pnpm.io/)** 9+ — TypeScript monorepo

## Clone and install

```bash
git clone https://github.com/latticeag/lexshield.git
cd lexshield

# Python (engine + CLI into .venv)
uv sync

# TypeScript (engine SDK + examples)
pnpm install
```

After `uv sync`, CLI commands are available as `uv run lexshield …` or `.venv/bin/lexshield`.

## Project layout

| Path | Role |
|------|------|
| `packages/engine-py` | Python policy engine (`lexshield` package) |
| `packages/cli` | Typer CLI (`lexshield-cli` package) |
| `packages/engine-ts` | TypeScript SDK (`@latticeag/lexshield`) |
| `packs/` | Shipped policy packs |
| `fixtures/golden/` | Cross-engine regression scenarios |
| `taxonomy/builtin.yaml` | Frozen 24-intent catalog (SPEC Appendix B) |
| `scripts/acceptance_v01.py` | Appendix D checklist runner |

## Running tests

### Make targets (recommended)

```bash
make test         # Python pytest + TypeScript unit + golden tests
make acceptance   # Appendix D v0.1 release checklist
make build        # Build TypeScript SDK (no publish)
```

### Python

From the repo root:

```bash
uv run pytest                    # all Python tests
uv run pytest -m golden          # golden fixtures only
uv run pytest packages/engine-py  # engine only
uv run pytest packages/cli        # CLI only
```

Golden tests load scenarios from `fixtures/golden/<scenario>/`:

- `request.json` — tool call input
- `policy-ref.yaml` — pack or inline policy
- `expected.json` — expected verdict fields (`decision`, `reason`, `matchedRuleId`, `primaryIntent`)

See [fixtures/golden/README.md](./fixtures/golden/README.md) for the full contract.

### TypeScript

```bash
pnpm test              # all workspace packages
pnpm test:golden       # golden parity (must match Python decisions)
pnpm --filter @latticeag/lexshield build
```

### Policy packs

```bash
uv run lexshield-check-packs
```

Validates `baseline-deny`, `pii-guard`, and `change-window` with `lexshield check --strict`.

## Golden fixtures

Both engines must produce **identical** verdict fields on every scenario:

| Field | Compared |
|-------|----------|
| `decision` | yes |
| `reason` | yes |
| `matchedRuleId` | when present in `expected.json` |
| `primaryIntent` | when present in `expected.json` |

CI runs deterministic classification only (no live LLM). Add a new scenario:

1. Create `fixtures/golden/<scenario-name>/` with `request.json`, `policy-ref.yaml`, `expected.json`
2. Run `uv run pytest -m golden` and `pnpm test:golden`
3. Name directories `{verdict}-{behavior}` (e.g. `block-secret-exposure`)

## Linting

```bash
uv run ruff check packages/engine-py packages/cli
uv run ruff format --check packages/engine-py packages/cli
```

## Examples

Runnable without API keys:

```bash
# Python block exfiltration demo
cd examples/python-block-exfil && uv run --project ../.. python main.py

# Challenge + approve flow
cd examples/python-challenge-delete && uv run --project ../.. python main.py

# TypeScript evaluate
cd examples/ts-evaluate && pnpm exec tsx index.ts
```

## v0.1 acceptance checklist

Before tagging `v0.1.0`, run:

```bash
make acceptance
# or: uv run python scripts/acceptance_v01.py
```

This automates [SPEC Appendix D](./SPEC.md#appendix-d--v01-acceptance-checklist): golden counts, pytest/pnpm golden parity, pack validation, LICENSE, taxonomy, demos, docs, and CLI smoke flows. Exit code `0` means all automated checks passed.

Manual items (README quickstart on a clean machine, PyPI/npm publish) are documented in the script output but not enforced without credentials.

## Pull requests

1. Branch from `main`
2. Add or update tests for behavior changes
3. Run `make test` locally
4. Keep golden fixtures in sync across Python and TypeScript
5. Update [CHANGELOG.md](./CHANGELOG.md) for user-visible changes

## Specification

Architecture, policy language, and acceptance criteria live in [SPEC.md](./SPEC.md). Built-in intents are frozen at 24 for v0.1 — see [taxonomy/builtin.yaml](./taxonomy/builtin.yaml) and [docs/intents.md](./docs/intents.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
