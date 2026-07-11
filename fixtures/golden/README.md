# Golden Fixtures

Shared regression fixtures for Python and TypeScript policy engines. Every fixture under `fixtures/golden/**` must produce **identical verdict decisions** in both engines.

## Directory layout

Each scenario is a directory named after the behavior under test:

```
fixtures/golden/<scenario>/
  request.json       # ToolCallRequest (see schemas/tool-call-request.schema.json)
  policy-ref.yaml    # Which pack/policy + rules to load (or inline policy.yaml)
  expected.json      # Expected verdict fields (subset of full Verdict)
  rules-ref.yaml     # Optional; defaults to pack rules.yaml
```

## `request.json`

A `ToolCallRequest` object. `id`, `shieldId`, and `timestamp` may be fixed in fixtures for stable traces; engines should accept omitted ids and generate ULIDs at runtime.

Required fields for evaluation:

- `caller` — `{ "id", "type", "roles?" }`
- `tool` — `{ "name" }`
- `arguments` — tool args object (may be `{}`)
- `context` — at minimum `environment` when policy matches on environment

## `policy-ref.yaml`

Points at a shipped pack or inline policy:

```yaml
pack: baseline-deny
policy: ../../../packs/baseline-deny/policy.yaml
rules: ../../../packs/baseline-deny/rules.yaml
```

Alternatively, embed a minimal `policy:` block for scenario-specific overrides.

## `expected.json`

Subset of verdict fields asserted by golden runners. Minimum:

```json
{
  "decision": "BLOCK",
  "matchedRuleId": "block-secret-exposure",
  "reason": "Possible secret exposure in tool arguments",
  "primaryIntent": "security.secret_exposure"
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `decision` | yes | `ALLOW`, `BLOCK`, `CHALLENGE`, or `DEFER` |
| `matchedRuleId` | usually | Omit when default verdict applies with no rule match |
| `reason` | yes | Exact string from winning policy rule |
| `primaryIntent` | recommended | Primary classification intent after deterministic (+ optional LLM) pipeline |

Engines run the **deterministic classifier only** in CI (no live LLM). Optional fields like `durationMs` and `challengeId` are not compared unless `strict: true`.

## Running (once engines exist)

```bash
# Python
pytest packages/engine-py/tests/test_golden.py

# TypeScript
pnpm --filter @latticeag/lexshield test:golden
```

**Current count: 60 scenarios** (SPEC §9B.9 matrix rows + extended regression set).

## Optional fixture files

| File | When to use |
|------|-------------|
| `rules-ref.yaml` | Override pack `rules.yaml` (tool_map, patterns) for the scenario |
| `classifications-ref.json` | Force classifier output when deterministic rules cannot express alternatives or multi-intent cases (e.g. `alternatives-intent-match`) |

### Not covered in golden CI

- **`prior-calls-no-cache`** — `ClassifierPipeline` disables fingerprint cache when `context.priorCalls` is set; golden runners evaluate `PolicyEngine` directly with deterministic classification only, so prior-call cache behavior is validated in unit tests (`test_pipeline.py`), not golden fixtures.

## Adding scenarios

1. Name the directory `{verdict}-{behavior}` (e.g. `block-secret-exposure`, `allow-health`).
2. Copy `policy-ref.yaml` from a sibling fixture or reference a pack.
3. Add `request.json` and `expected.json`.
4. Ensure the scenario is covered by a must-have security regression (SPEC §27.2) when applicable.

Target: **≥ 50 scenarios** for v0.1 tag; the suite currently has **60** scenarios including all §9B.9 matrix rows.
