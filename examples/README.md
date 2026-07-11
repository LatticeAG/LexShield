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

Expected: a `CHALLENGE` message with a `challenge_id`. LexShield writes an open challenge record under `.lexshield/challenges/` automatically when the guard raises.

Approve the challenge (run from the example directory):

```bash
lexshield challenge approve <challenge_id>
lexshield challenge list    # should show no open challenges
```

The challenge file is updated in place with `status: approved`.

> **Note:** v0.1 records the approval locally. Re-running the guarded tool still returns `CHALLENGE` unless you use `await_challenge=True` on the decorator (documented in [docs/sdk-python.md](../docs/sdk-python.md)). The approve step demonstrates the human-in-the-loop workflow and audit trail.

## TypeScript: evaluate-only

```bash
cd examples/ts-evaluate
npx tsx index.ts
```

Expected: JSON verdicts for `health_check` (`ALLOW`) and `send_email` with a secret in the body (`BLOCK`).

## Related docs

- [Policy authoring](../docs/policy.md)
- [Intent catalog](../docs/intents.md)
- [Python SDK](../docs/sdk-python.md)
- [TypeScript SDK](../docs/sdk-typescript.md)
- [CLI reference](../docs/cli.md)
- [Golden fixtures](../fixtures/golden/) — regression scenarios used in CI
