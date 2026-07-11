# Block Exfil Demo

Demonstrates LexShield blocking a `send_email` tool call that contains an AWS access key in the body. Uses the **deterministic classifier only** (no API key required).

## Scenario

1. Agent calls `send_email` with `AKIA…` in the message body.
2. Deterministic patterns in `rules.yaml` classify intent as `security.secret_exposure`.
3. Policy rule `block-secret-exposure` returns **BLOCK**.

## Run

From the repository root:

```bash
cd examples/python-block-exfil
uv run --project ../.. python main.py
```

Expected:

```
BLOCKED: Possible secret exposure in tool arguments (rule=block-secret-exposure)
```

## Config modes

- **Default:** `Shield.from_config("lexshield.yaml")` — files ship in this directory.
- **Inline paths:** `LEXSHIELD_USE_CONFIG=0 uv run --project ../.. python main.py` — constructs `Shield` with explicit `policy_path` / `rules_path`.

## Related

- Golden fixture: `fixtures/golden/block-secret-exposure/`
- Policy pack: `packs/baseline-deny/`
