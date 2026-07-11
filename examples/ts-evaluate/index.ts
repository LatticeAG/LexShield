/**
 * TypeScript evaluate demo — verdict-only, no tool execution.
 */

import { Shield } from "@latticeag/lexshield";

async function main(): Promise<void> {
  const shield = await Shield.fromConfig("lexshield.yaml");

  const verdict = await shield.evaluate({
    tool: "health_check",
    arguments: {},
    caller: { id: "agent-1", type: "agent" },
    context: { environment: "production" },
  });

  console.log(JSON.stringify(verdict, null, 2));
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
