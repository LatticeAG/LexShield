# Contrib framework adapters

Community-maintained examples for wiring LexShield into popular agent frameworks. These live outside core packages and are **not officially supported** — APIs may drift as upstream SDKs evolve.

| Adapter | Language | Pattern |
|---------|----------|---------|
| [vercel-ai-sdk](./vercel-ai-sdk/) | TypeScript | Wrap Vercel AI SDK `tool()` `execute` with `Shield.guard` |
| [langchain](./langchain/) | Python | Wrap LangChain `StructuredTool` with `Shield.guard` |
| [openai-agents](./openai-agents/) | Python | Sketch for OpenAI Agents SDK tool interception |

## Prerequisites

1. Install LexShield ([Python SDK](../docs/sdk-python.md) or [TypeScript SDK](../docs/sdk-typescript.md)).
2. Scaffold policy: `lexshield init --pack baseline-deny` (or copy `lexshield.yaml` + `policy.yaml` + `rules.yaml` from [examples/python-block-exfil](../examples/python-block-exfil/)).
3. Install the target framework as a **dev dependency** in your app — see each adapter README.

## Status

- No semver guarantees; contrib may lag framework releases.
- Issues and PRs welcome; core CI does not run framework-specific tests.
- For production, pin LexShield and your framework versions and add your own integration tests.

See [docs/integrations.md](../docs/integrations.md) for an overview and links.
