# TypeScript SDK

Reference for `@latticeag/lexshield`.

## Installation

```bash
npm install @latticeag/lexshield
# or
pnpm add @latticeag/lexshield
```

**Node 20+**. ESM-only (`"type": "module"`).

From this monorepo:

```bash
pnpm install
pnpm --filter @latticeag/lexshield build
```

## Quickstart

```typescript
import { Shield } from "@latticeag/lexshield";

const shield = await Shield.fromConfig("lexshield.yaml");

const verdict = await shield.evaluate({
  tool: "health_check",
  arguments: {},
  caller: { id: "agent-1", type: "agent" },
  context: { environment: "production" },
});

console.log(verdict.decision, verdict.reason);
```

## `Shield.fromConfig`

Loads and validates `lexshield.yaml`, resolves `policy.yaml` and deterministic `rules.yaml` relative to the config directory.

```typescript
import { resolve } from "node:path";
import { Shield } from "@latticeag/lexshield";

const shield = await Shield.fromConfig(resolve("lexshield.yaml"));
```

Throws `LexShieldConfigError` on missing files or schema validation failures.

## `Shield.fromOptions`

Inject parsed config for edge/serverless environments without filesystem access:

```typescript
import { Shield } from "@latticeag/lexshield";

const shield = Shield.fromOptions({
  config: shieldConfig,
  policy: policyDocument,
  deterministicRules: rulesDocument,
});
```

## `shield.evaluate`

Returns a `Verdict` without executing the tool.

```typescript
const verdict = await shield.evaluate({
  tool: "send_email",
  arguments: { to: "user@example.com", body: "hello" },
  caller: { id: "agent-1", type: "agent" },
  context: {
    environment: "production",
    tags: { data_class: "pii" },
  },
});
```

## `shield.guard`

Wrap an async tool implementation:

```typescript
const sendEmail = shield.guard(
  "send_email",
  async (args: { to: string; subject: string; body: string }) => {
    return { status: "sent" };
  },
);

await sendEmail({ to: "a@b.com", subject: "hi", body: "..." });
```

- `BLOCK` → `LexShieldBlockedError`
- `CHALLENGE` → `LexShieldChallengeError` (unless `awaitChallenge: true` in guard options)

## Verdict JSON shape

```json
{
  "requestId": "req-...",
  "decision": "BLOCK",
  "matchedRuleId": "block-secret-exposure",
  "reason": "Possible secret exposure in tool arguments",
  "classifications": [
    {
      "intent": "security.secret_exposure",
      "confidence": 0.98,
      "classifier": "deterministic:v1"
    }
  ],
  "durationMs": 1.2,
  "challengeId": null,
  "policyVersion": "1"
}
```

CamelCase aliases match the Python SDK and CLI `--json` output.

## Edge / inject config

For Workers, Lambda, or tests without disk IO, parse YAML/JSON yourself and call `Shield.fromOptions`. Policy and rules schemas are exported from the package for Zod validation.

## Parity with Python

Golden fixtures under `fixtures/golden/` are run by both engines:

```bash
pnpm test:golden
uv run pytest -m golden
```

Deterministic-only CI (`LEXSHIELD_GOLDEN_DETERMINISTIC_ONLY=1`) ensures Python and TypeScript produce identical `decision`, `matchedRuleId`, `reason`, and `primaryIntent`.

## Local API for challenges

The Python `lexshield run` server exposes challenge list/resolve endpoints. TypeScript clients can call them with `fetch` when coordinating human approval across processes.

## Examples

```bash
pnpm example:ts-evaluate
```

See [examples/ts-evaluate](../examples/ts-evaluate/index.ts) for evaluate-only usage with local policy files.
