# TypeScript Evaluate Demo

Minimal `@latticeag/lexshield` evaluate-only example. No tool execution — prints verdict JSON.

## Scenario

Evaluate a tool call against local `lexshield.yaml` (deterministic classifier only).

## Prerequisites

```bash
npm install @latticeag/lexshield
lexshield init --pack baseline-deny
```

## Run

```bash
npx tsx index.ts
```

## Related

- Golden fixtures: `fixtures/golden/`
- SDK reference: `docs/sdk-typescript.md`
