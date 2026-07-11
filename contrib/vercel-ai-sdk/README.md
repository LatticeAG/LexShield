# Vercel AI SDK adapter (contrib)

Wrap [Vercel AI SDK](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling) tools with `@latticeag/lexshield` before the model invokes `execute`.

**Not officially supported.** Copy `wrap-tool.ts` into your project or use it as a reference.

## Dev dependencies

```bash
pnpm add @latticeag/lexshield
pnpm add -D ai zod tsx
```

From this monorepo:

```bash
pnpm install
pnpm --filter @latticeag/lexshield build
```

## Policy

Copy config from an example or init in your app directory:

```bash
lexshield init --pack baseline-deny
# or
cp examples/python-block-exfil/{lexshield.yaml,policy.yaml,rules.yaml} ./your-app/
```

## Usage

```typescript
import { tool } from "ai";
import { z } from "zod";
import { Shield } from "@latticeag/lexshield";
import { wrapToolWithLexshield } from "./wrap-tool.js";

const shield = await Shield.fromConfig("lexshield.yaml");

const sendEmail = wrapToolWithLexshield(
  shield,
  "send_email",
  tool({
    description: "Send an email",
    inputSchema: z.object({
      to: z.string(),
      subject: z.string(),
      body: z.string(),
    }),
    execute: async ({ to, subject, body }) => ({ status: "sent", to }),
  }),
);

// Pass to generateText / streamText:
// tools: { send_email: sendEmail }
```

`BLOCK` and `CHALLENGE` surface as `LexShieldBlockedError` / `LexShieldChallengeError` from `@latticeag/lexshield`. Map them in your agent error handler or return a tool result string the model can read.

## How it works

`wrapToolWithLexshield` replaces `execute` with `shield.guard(toolName, …)`. The first argument to `execute` (tool input) is passed as LexShield `arguments`. Optional `ToolExecutionOptions` are forwarded unchanged to your original handler.

Tools without `execute` (client-forwarded tool calls) are returned as-is — evaluate those separately with `shield.evaluate()` when you handle tool calls on the client.

## Run the included demo

```bash
pnpm install
pnpm --filter @latticeag/lexshield build
cd contrib/vercel-ai-sdk && pnpm exec tsx wrap-tool.ts
```

Expect `LexShieldBlockedError` when the demo passes an AWS key in the email body.
