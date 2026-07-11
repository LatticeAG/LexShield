# TypeScript Evaluate Demo

Minimal `@latticeag/lexshield` evaluate-only example. No tool execution — prints verdict JSON.

## Run

```bash
# from repo root
pnpm install
pnpm --filter @latticeag/lexshield build

cd examples/ts-evaluate
pnpm exec tsx index.ts
```

Expected: `ALLOW` for `health_check`, `BLOCK` for `send_email` with an AWS key in the body.

## Related

- Golden fixtures: `fixtures/golden/`
- SDK reference: [docs/sdk-typescript.md](../../docs/sdk-typescript.md)
