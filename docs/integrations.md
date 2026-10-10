# Framework integrations

LexShield core ships Python and TypeScript SDKs with `Shield.evaluate` and `Shield.guard`. Framework-specific wiring lives in **[contrib/](../contrib/)** — community examples, not officially supported packages.

## When to use contrib adapters

| Approach | Use when |
|----------|----------|
| `shield.guard` on your tool function | You own the tool implementation (simplest) |
| `shield.evaluate` before dispatch | Framework forwards tool calls to a queue or client |
| Contrib adapter | You want a copy-paste pattern for AI SDK, LangChain, or OpenAI Agents |

All paths evaluate policy **before** tool side effects.

## Available contrib patterns

| Framework | Path | Mechanism |
|-----------|------|-----------|
| Vercel AI SDK | [contrib/vercel-ai-sdk](../contrib/vercel-ai-sdk/) | `wrapToolWithLexshield()` wraps `tool().execute` |
| LangChain | [contrib/langchain](../contrib/langchain/) | `guard_structured_tool()` copies `StructuredTool` with guarded handler |
| OpenAI Agents SDK | [contrib/openai-agents](../contrib/openai-agents/) | `lexshield_function_tool()` + optional audit hooks |

Read [contrib/README.md](../contrib/README.md) for prerequisites and dev-dependency notes.

## Generic wrap pattern (~20 lines)

**TypeScript**

```typescript
const guarded = shield.guard("tool_name", async (args) => originalHandler(args));
```

**Python**

```python
@shield.guard(tool="tool_name")
async def tool_name(**kwargs):
    ...
```

Map framework tool names and argument dicts to LexShield `tool` and `arguments`. On `BLOCK`, raise or return an error the agent can handle.

## Production checklist

1. Pin `@latticeag/lexshield` / `lexshield` and your agent framework versions.
2. Run `lexshield check --strict` in CI for policy YAML.
3. Add integration tests for allow/block paths per guarded tool.
4. Configure trace sinks (`traces.ndjson` or stdout) for audit.

## Related docs

- [Python SDK](./sdk-python.md) — `Shield.guard`, challenges, sessions
- [TypeScript SDK](./sdk-typescript.md) — `Shield.guard`, edge config
- [Policy authoring](./policy.md)
- [Examples](../examples/README.md) — runnable allow/block/challenge demos
