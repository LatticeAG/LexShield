# LexShield Examples

Runnable demos for LexShield v0.1. All examples use the **deterministic classifier only** — no API keys or LLM calls.

## Prerequisites

From the repository root:

```bash
uv sync          # Python SDK + CLI
pnpm install     # TypeScript SDK
pnpm --filter @latticeag/lexshield build
```

Each example ships its own `lexshield.yaml`, `policy.yaml`, and `rules.yaml`. You do not need to run `lexshield init` inside an example directory.

## Examples

| Directory | Language | Demonstrates |
|-----------|----------|--------------|
| [`python-block-exfil/`](./python-block-exfil/) | Python | `@shield.guard` blocks `send_email` when args contain an AWS key |
| [`python-challenge-delete/`](./python-challenge-delete/) | Python | `CHALLENGE` for `delete_resource` in production + CLI approve flow |
| [`ts-evaluate/`](./ts-evaluate/) | TypeScript | `shield.evaluate()` returns verdict JSON without executing tools |

## Python: block secret exposure

```bash
cd examples/python-block-exfil
uv run --project ../.. python main.py
```

Expected output:

```
BLOCKED: Possible secret exposure in tool arguments (rule=block-secret-exposure)
```

The demo loads policy via `Shield.from_config("lexshield.yaml")` by default. To use inline paths instead (no config file), set `LEXSHIELD_USE_CONFIG=0`:

```bash
LEXSHIELD_USE_CONFIG=0 uv run --project ../.. python main.py
```

## Python: challenge destructive delete

```bash
cd examples/python-challenge-delete
uv run --project ../.. python main.py
```

Expected: `CHALLENGE` → CLI approve → `ALLOW after approval` with deleted resource payload.

Manual approve step (if you triggered CHALLENGE separately):

```bash
uv run --project ../.. python main.py --challenge-only
lexshield challenge approve <challenge_id> -c examples/python-challenge-delete
uv run --project ../.. python main.py
```

## TypeScript: evaluate-only

```bash
pnpm example:ts-evaluate
```

Or from the example directory:

```bash
cd examples/ts-evaluate
pnpm exec tsx index.ts
```

Expected: JSON verdicts for `health_check` (`ALLOW`) and `send_email` with a secret in the body (`BLOCK`).

## Related docs

- [Policy authoring](../docs/policy.md)
- [Intent catalog](../docs/intents.md)
- [Python SDK](../docs/sdk-python.md)
- [TypeScript SDK](../docs/sdk-typescript.md)
- [CLI reference](../docs/cli.md)
- [Golden fixtures](../fixtures/golden/) — regression scenarios used in CI
