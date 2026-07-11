# CLI Reference

Commands for the `lexshield` Typer CLI. See [SPEC §16](../SPEC.md#16-cli-surface).

## Installation

```bash
pip install lexshield          # PyPI when published
# or from monorepo:
uv sync && uv run lexshield --help
```

## `lexshield init`

Scaffold `lexshield.yaml`, `policy.yaml`, `rules.yaml`, and `.gitignore` entries.

```bash
lexshield init
lexshield init --pack pii-guard
lexshield init --pack change-window --force
```

| Flag | Default | Description |
|------|---------|-------------|
| `--pack` | `baseline-deny` | `baseline-deny`, `pii-guard`, or `change-window` |
| `--force` | false | Overwrite existing files |

## `lexshield check`

Validate config, policy, and deterministic rules. **CI-friendly** — exits non-zero on errors.

```bash
lexshield check
lexshield check --strict
lexshield check --policy packs/baseline-deny/policy.yaml --rules packs/baseline-deny/rules.yaml
```

| Flag | Description |
|------|-------------|
| `-c, --config` | Path to `lexshield.yaml` (default: `./lexshield.yaml`) |
| `--policy` | Policy file (overrides config) |
| `--rules` | Rules file (overrides config) |
| `--strict` | Treat warnings as errors |

Validate all shipped packs (monorepo):

```bash
uv run lexshield-check-packs
```

## `lexshield run`

Start the local FastAPI server (evaluate, execute stub, traces, challenges).

```bash
lexshield run
lexshield run --host 127.0.0.1 --port 8787
```

Requires `lexshield.yaml` in the working directory.

## `lexshield evaluate`

Offline tool-call evaluation.

```bash
lexshield evaluate --tool health_check --args '{}'
lexshield evaluate --tool send_email \
  --args '{"to":"user@example.com","body":"AKIA0123456789012345"}' \
  --json
```

| Flag | Description |
|------|-------------|
| `--tool` | Tool name (required unless `--stdin`) |
| `--args` | JSON object of arguments (default `{}`) |
| `--caller` | Caller id |
| `--json` | Machine-readable verdict on stdout |
| `--stdin` | Read full `ToolCallRequest` JSON from stdin |
| `-c, --config` | Config path |
| `--policy` / `--rules` | Override policy or rules paths |

Exit code is **0** for any verdict (including `BLOCK`). Parse `decision` from `--json` in scripts.

## `lexshield traces`

Query local NDJSON trace files configured in `lexshield.yaml`.

```bash
lexshield traces list
lexshield traces show <request-id>
```

## `lexshield challenge`

Human-in-the-loop challenge queue (files under `.lexshield/challenges/`).

```bash
lexshield challenge list
lexshield challenge approve <challenge_id>
lexshield challenge deny <challenge_id>
```

Approve updates the challenge record to `status: approved`. Use with `@shield.guard(await_challenge=True)` to block until resolution.

Example flow:

```bash
cd examples/python-challenge-delete
uv run --project ../.. python main.py
# note challenge_id from output
lexshield challenge approve <challenge_id>
```

## `lexshield packs`

```bash
lexshield packs list
lexshield packs apply baseline-deny
lexshield packs apply pii-guard --output policy.yaml --force
```

## `lexshield version`

```bash
lexshield version
```

Prints CLI semver and git short SHA when available.

## Global flags

All subcommands accept `-c, --config PATH` where applicable (default `./lexshield.yaml`).

## CI usage

```yaml
- run: uv sync
- run: uv run pytest
- run: uv run lexshield-check-packs
```

```yaml
- run: pnpm install
- run: pnpm test
- run: pnpm test:golden
```

See [.github/workflows/ci.yml](../.github/workflows/ci.yml).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (including `evaluate` with any verdict) |
| 1 | Validation error, missing config, challenge not found |
| 2 | Reserved for partial failures |

`evaluate` does **not** use exit code to signal `BLOCK` vs `ALLOW` — inspect JSON output instead.
