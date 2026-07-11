# Challenge Delete Demo

Demonstrates LexShield **CHALLENGE** for a destructive infra action in production. Uses deterministic classification only.

## Scenario

1. Agent calls `delete_resource` in `environment=production`.
2. Classifier maps tool → `infra.delete.resource`.
3. Rule `challenge-delete-prod` returns **CHALLENGE** and writes a record to `.lexshield/challenges/`.
4. Approve via CLI; use `await_challenge=True` on the guard to wait for approval.

## Run

```bash
cd examples/python-challenge-delete
uv run --project ../.. python main.py
```

Expected: `CHALLENGE` with a `challenge_id`.

Approve:

```bash
lexshield challenge approve <challenge_id>
lexshield challenge list
```

## Related

- Golden fixture: `fixtures/golden/challenge-delete-prod/`
- Policy pack: `packs/baseline-deny/`
- CLI: [docs/cli.md](../../docs/cli.md)
