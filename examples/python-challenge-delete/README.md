# Challenge Delete Demo

Demonstrates LexShield **CHALLENGE** for a destructive infra action in production. Uses deterministic classification only.

## Scenario

1. Agent calls `delete_resource` in `environment=production`.
2. Classifier maps tool → `infra.delete.resource`.
3. Rule `challenge-delete-prod` returns **CHALLENGE** and writes a record to `.lexshield/challenges/`.
4. Approve via CLI; the demo re-runs with `await_challenge=True` and executes after approval.

## Run (end-to-end)

```bash
cd examples/python-challenge-delete
uv run --project ../.. python main.py
```

Expected flow:

1. `CHALLENGE while awaiting approval: challenge_id=...`
2. `lexshield challenge approve <challenge_id> -c .` (invoked automatically by the demo)
3. `ALLOW after approval: {'status': 'deleted', ...}`

## Run (step-by-step)

Trigger CHALLENGE only, then run the full demo after manual approval:

```bash
uv run --project ../.. python main.py --challenge-only
lexshield challenge approve <challenge_id> -c examples/python-challenge-delete
uv run --project ../.. python main.py
```

## Related

- Golden fixture: `fixtures/golden/challenge-delete-prod/`
- Policy pack: `packs/baseline-deny/`
- CLI: [docs/cli.md](../../docs/cli.md)
