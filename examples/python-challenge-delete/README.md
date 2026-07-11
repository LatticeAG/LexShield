# Challenge Delete Demo

Demonstrates LexShield **CHALLENGE** for a destructive infra action in production. Uses deterministic classification only.

## Scenario

1. Agent calls `delete_resource` in `environment=production`.
2. Classifier maps tool → `infra.delete.resource`.
3. `baseline-deny` rule `challenge-delete-prod` returns **CHALLENGE**.
4. Approve via CLI, then re-evaluate or execute.

## Prerequisites

```bash
pip install lexshield
lexshield init --pack baseline-deny
```

## Run

```bash
python main.py
```

Expected: `LexShieldChallengeError` with a `challenge_id`. Approve with:

```bash
lexshield challenge approve <challenge_id>
```

Then re-run or call `shield.evaluate(...)` again after approval (documented in SDK once challenge resume is wired).

## Related

- Policy pack: `packs/baseline-deny/`
- CLI: `docs/cli.md`
