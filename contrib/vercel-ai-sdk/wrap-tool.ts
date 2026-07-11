/**
 * Contrib example — wrap a Vercel AI SDK tool with LexShield guard.
 *
 * Dev deps for full AI SDK usage: ai, zod, tsx (see README.md)
 * LexShield: @latticeag/lexshield
 */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Shield } from "@latticeag/lexshield";

/** Minimal stand-in for AI SDK Tool shape (matches `tool()` return type). */
export interface AiSdkTool<TInput extends Record<string, unknown> = Record<string, unknown>> {
  description?: string;
  inputSchema?: unknown;
  execute?: (input: TInput, options?: unknown) => Promise<unknown> | unknown;
}

/**
 * Wrap an AI SDK tool's `execute` with `shield.guard`.
 * Tools without `execute` are returned unchanged.
 */
export function wrapToolWithLexshield<TInput extends Record<string, unknown>>(
  shield: Shield,
  toolName: string,
  aiTool: AiSdkTool<TInput>,
): AiSdkTool<TInput> {
  if (!aiTool.execute) {
    return aiTool;
  }

  const originalExecute = aiTool.execute;

  return {
    ...aiTool,
    execute: shield.guard(toolName, async (input: TInput) => originalExecute(input)),
  };
}

async function demo(): Promise<void> {
  const exampleDir = dirname(fileURLToPath(import.meta.url));
  const policyDir = resolve(exampleDir, "../../examples/python-block-exfil");
  const shield = await Shield.fromConfig(resolve(policyDir, "lexshield.yaml"));

  const sendEmail = wrapToolWithLexshield(shield, "send_email", {
    description: "Send an email",
    execute: async ({ to }) => ({ status: "sent", to }),
  });

  if (!sendEmail.execute) {
    throw new Error("demo tool missing execute");
  }

  try {
    await sendEmail.execute({
      to: "user@example.com",
      subject: "keys",
      body: "AKIAIOSFODNN7EXAMPLE",
    });
    console.error("Unexpected: tool call was allowed");
    process.exit(1);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.log("BLOCKED (expected):", message);
  }
}

const isMain =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  demo().catch((err: unknown) => {
    console.error(err);
    process.exit(1);
  });
}
