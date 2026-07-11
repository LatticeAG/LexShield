# CLI Reference

Commands for the `lexshield` Typer CLI. See [SPEC §16](../SPEC.md#16-cli-surface).

## Installation

```bash
pip install lexshield          # PyPI when published
# or from monorepo:
uv sync && uv run lexshield --help
```

## Global flags

All config-aware subcommands accept `-c, --config PATH` (default `./lexshield.yaml`). Set it once before the subcommand or on the subcommand itself:

```bash
lexshield -c examples/python-block-exfil/lexshield.yaml evaluate --tool health_check --args '{}'
lexshield evaluate --tool health_check --args '{}' -c ./lexshield.yaml
```

## Shell completion

```bash
# Bash — append to ~/.bashrc or source directly
lexshield completion bash >> ~/.bash_completion.d/lexshield
source ~/.bash_completion.d/lexshield

# Or use Typer's built-in installer
lexshield --install-completion bash
```

Supported shells: `bash`, `zsh`, `fish`.

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

Start the local FastAPI server (`/evaluate`, `/execute`, `/traces`, `/challenges`).

```bash
lexshield run
lexshield run --host 127.0.0.1 --port 8787
```

Requires `lexshield.yaml` in the working directory (or pass `-c`).

## `lexshield evaluate`

Offline tool-call evaluation.

```bash
lexshield evaluate --tool health_check --args '{}'
lexshield evaluate --tool send_email \
  --args '{"to":"user@example.com","body":"AKIA0123456789012345"}' \
  --json
```

### Examples (`lexshield evaluate --help`)

```bash
# Allow health check
lexshield evaluate --tool health_check --args '{}'

# Block AWS key in email body (deterministic pattern)
lexshield evaluate --tool send_email \
  --args '{"to":"user@example.com","body":"AKIA0123456789012345"}' \
  --json

# Challenge destructive prod delete
lexshield -c examples/python-challenge-delete/lexshield.yaml evaluate \
  --tool delete_resource \
  --args '{"resource_id":"db-primary-replica","reason":"cleanup"}' \
  --environment production \
  --json

# Evaluate a full ToolCallRequest from stdin
echo '{"tool":{"name":"health_check"},"arguments":{}}' \
  | lexshield evaluate --stdin --json

# Override policy paths for CI
lexshield evaluate --tool health_check --args '{}' \
  --policy packs/baseline-deny/policy.yaml \
  --rules packs/baseline-deny/rules.yaml
```

| Flag | Description |
|------|-------------|
| `--tool` | Tool name (required unless `--stdin`) |
| `--args` | JSON object of arguments (default `{}`) |
| `--caller` | Caller id or JSON object |
| `--caller-type` | Caller type when `--caller` is a plain id (default `agent`) |
| `--environment`, `--env` | Sets `context.environment` |
| `--tags` | Context tags as JSON object |
| `--json` | Machine-readable verdict on stdout |
| `--stdin` | Read full `ToolCallRequest` JSON from stdin |
| `-c, --config` | Config path |
| `--policy` / `--rules` | Override policy or rules paths |

Exit code is **0** for any verdict (including `BLOCK`). Parse `decision` from `--json` in scripts.

## `lexshield traces`

Query local NDJSON trace files configured in `lexshield.yaml`.

```bash
lexshield traces list
lexshield traces list --decision BLOCK --limit 10
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
# end-to-end demo: CHALLENGE → lexshield challenge approve → guarded execution

# Or step-by-step after CHALLENGE:
lexshield challenge approve <challenge_id> -c examples/python-challenge-delete
uv run --project ../.. python main.py --approve-only
```

## `lexshield packs`

```bash
lexshield packs list
lexshield packs apply baseline-deny
lexshield packs apply pii-guard --output policy.yaml --force
```

## `lexshield completion`

```bash
lexshield completion bash
lexshield completion zsh >> ~/.zfunc/_lexshield
```

## `lexshield version`

```bash
lexshield version
```

Prints CLI semver and git short SHA when available.

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
