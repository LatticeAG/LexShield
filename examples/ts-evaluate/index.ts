/**
 * TypeScript evaluate demo — verdict-only, no tool execution.
 *
 * Run from repo root after `pnpm install && pnpm --filter @latticeag/lexshield build`:
 *   cd examples/ts-evaluate && npx tsx index.ts
 */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Shield } from "@latticeag/lexshield";

const exampleDir = dirname(fileURLToPath(import.meta.url));

async function main(): Promise<void> {
  const shield = await Shield.fromConfig(resolve(exampleDir, "lexshield.yaml"));

  const health = await shield.evaluate({
    tool: "health_check",
    arguments: {},
    caller: { id: "agent-1", type: "agent" },
    context: { environment: "production" },
  });
  console.log("health_check verdict:");
  console.log(JSON.stringify(health, null, 2));

  const blocked = await shield.evaluate({
    tool: "send_email",
    arguments: {
      to: "user@example.com",
      subject: "keys",
      body: "AKIAIOSFODNN7EXAMPLE",
    },
    caller: { id: "agent-1", type: "agent" },
    context: { environment: "production" },
  });
  console.log("\nsend_email (secret in body) verdict:");
  console.log(JSON.stringify(blocked, null, 2));
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
