# Block Exfil Demo

Demonstrates LexShield blocking a `send_email` tool call that contains an AWS access key in the body. Uses the **deterministic classifier only** (no API key required).

## Scenario

1. Agent calls `send_email` with `AKIA...` in the message body.
2. Deterministic patterns in `rules.yaml` classify intent as `security.secret_exposure`.
3. `baseline-deny` policy rule `block-secret-exposure` returns **BLOCK**.

## Prerequisites

```bash
pip install lexshield   # once published
lexshield init --pack baseline-deny
```

## Run

```bash
python main.py
```

Expected: `LexShieldBlockedError` with reason *"Possible secret exposure in tool arguments"*.

## Related

- Golden fixture: `fixtures/golden/block-secret-exposure/`
- Policy pack: `packs/baseline-deny/`
