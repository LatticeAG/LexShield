# Python SDK

Reference for the `lexshield` package. See [SPEC §15.1](../SPEC.md#151-python-primary).

## Installation

```bash
# From PyPI (when published)
pip install lexshield

# From this monorepo
uv sync
uv run python -c "from lexshield import Shield; print(Shield)"
```

Python **3.10+** (monorepo CLI requires 3.11+). Async-first API with sync guard helper.

## Quickstart

```python
import asyncio
from lexshield import Shield

shield = Shield.from_config("lexshield.yaml")

async def main():
    verdict = await shield.evaluate(
        tool="send_email",
        arguments={"to": "a@b.com", "body": "hello"},
        caller={"id": "agent-1", "type": "agent"},
        context={"environment": "production"},
    )
    print(verdict.decision, verdict.reason)

asyncio.run(main())
```

Scaffold config:

```bash
lexshield init --pack baseline-deny
```

## `Shield.from_config`

Loads `lexshield.yaml` and resolves relative paths for `policy.yaml`, deterministic `rules.yaml`, and trace sinks.

```python
from pathlib import Path
from lexshield import Shield

shield = Shield.from_config(Path("lexshield.yaml"))
```

Raises `LexShieldConfigError` if the file is missing or invalid.

## Inline policy paths (no config file)

Pass policy and rules paths directly:

```python
from pathlib import Path
from lexshield import Shield

shield = Shield(
    shield_id="my-agent",
    name="my-agent",
    policy_path=Path("policy.yaml"),
    rules_path=Path("rules.yaml"),
)
```

See [examples/python-block-exfil](../examples/python-block-exfil/main.py) (`LEXSHIELD_USE_CONFIG=0`).

## `shield.evaluate`

Evaluate a tool call **without executing** the tool. Returns a `Verdict` model.

```python
verdict = await shield.evaluate(
    tool="delete_resource",
    arguments={"resource_id": "db-1", "reason": "cleanup"},
    caller={"id": "agent-1", "type": "agent"},
    context={"environment": "production", "tags": {"team": "platform"}},
)
```

Fields on `Verdict`: `decision`, `reason`, `matched_rule_id`, `classifications`, `challenge_id`, `request_id`, `duration_ms`, `policy_version`.

## `@shield.guard` decorator

Wrap async tool functions. Evaluates policy before the body runs.

```python
@shield.guard(tool="send_email")
async def send_email(to: str, subject: str, body: str) -> dict:
    ...
```

- On `BLOCK`: raises `LexShieldBlockedError`
- On `CHALLENGE`: raises `LexShieldChallengeError` (unless `await_challenge=True`)
- On `ALLOW`: calls the wrapped function

Keyword arguments are passed as tool `arguments`.

## `shield.guard_sync`

Sync wrapper around the async guard (uses `asyncio.run` internally):

```python
@shield.guard_sync(tool="health_check")
def health_check() -> dict:
    return {"status": "ok"}
```

## `shield.session`

Context manager for session-scoped `context` fields:

```python
with shield.session(environment="production", conversation_id="conv-42"):
    await send_email(...)
```

Merges into `evaluate` / `guard` context when not explicitly set on the call.

## `shield.record_outcome`

Attach execution outcome to trace sinks after a tool runs:

```python
verdict = await shield.evaluate(tool="send_email", arguments={...})
# ... execute tool if ALLOW ...
await shield.record_outcome(verdict.request_id, "EXECUTED")
```

## Errors

| Exception | When |
|-----------|------|
| `LexShieldBlockedError` | Policy returned `BLOCK` |
| `LexShieldChallengeError` | Policy returned `CHALLENGE` (non-await mode) |
| `LexShieldConfigError` | Invalid config, policy, or guard misuse |

All inherit from `LexShieldError` with `.message`, `.verdict`, and `.request_id`.

```python
from lexshield.errors import LexShieldBlockedError

try:
    await send_email(...)
except LexShieldBlockedError as exc:
    print(exc.message, exc.verdict.matched_rule_id)
```

## Challenge opt-in (`await_challenge=True`)

```python
@shield.guard(tool="delete_resource", await_challenge=True)
async def delete_resource(resource_id: str, reason: str) -> dict:
    ...
```

When `CHALLENGE` is returned, the guard **blocks** until the challenge is approved via CLI or API, denied, or timed out (per rule `onTimeout`). Approve with:

```bash
lexshield challenge approve <challenge_id>
```

Challenge records are stored under `.lexshield/challenges/`.

## Configuration

`lexshield.yaml` shape:

```yaml
version: 1
shield:
  id: local
  name: local-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
  fail_on_classifier_error: BLOCK
  sinks:
    - type: stdout
    - type: file
      path: ./traces.ndjson
server:
  host: 127.0.0.1
  port: 8787
  token_env: LEXSHIELD_LOCAL_TOKEN
```

v0.1 runs fully on the deterministic classifier without API keys. LLM classifiers are optional and not required for the quickstart path.

## Local API client

Start the local server:

```bash
lexshield run
```

Endpoints (see [SPEC §17](../SPEC.md#17-local-api--proxy)):

- `POST /v1/shields/{id}/evaluate`
- `POST /v1/shields/{id}/execute`
- `GET /v1/challenges`
- `POST /v1/challenges/{id}/resolve`

Optional auth: set `LEXSHIELD_LOCAL_TOKEN` and pass `Authorization: Bearer ...`.

## Examples

| Example | Path |
|---------|------|
| Block secret in `send_email` | [examples/python-block-exfil](../examples/python-block-exfil/) |
| Challenge prod delete | [examples/python-challenge-delete](../examples/python-challenge-delete/) |

```bash
cd examples/python-block-exfil
uv run --project ../.. python main.py
```
