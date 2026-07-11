# OpenAI Agents SDK adapter (contrib)

Sketch for intercepting [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) function tools with LexShield **before** execution.

**Not officially supported.** The Agents SDK does not ship a first-class policy middleware; this contrib shows two integration paths:

1. **Wrap at definition time** (recommended) — decorate your handler with `shield.guard` before passing it to `function_tool`.
2. **Lifecycle hooks** — observe `on_tool_start` for audit/logging; blocking policy belongs in the wrapped handler, not in hooks alone.

## Dev dependencies

```bash
pip install lexshield openai-agents
# or, from this monorepo:
uv sync
uv pip install openai-agents
```

## Policy

```bash
lexshield init --pack baseline-deny
```

## Usage (wrap at definition time)

```python
from pathlib import Path

from agents import Agent, Runner, function_tool
from lexshield import Shield

from middleware import lexshield_function_tool

shield = Shield.from_config(Path("lexshield.yaml"))

@lexshield_function_tool(shield, name="send_email")
async def send_email(to: str, subject: str, body: str) -> dict:
    return {"status": "sent", "to": to}

agent = Agent(name="assistant", tools=[send_email])
# result = await Runner.run(agent, "Email the team...")
```

## Lifecycle hook sketch

For tracing only, subclass `RunHooksBase` and read `context.tool_name` / `context.tool_arguments` in `on_tool_start`. To **block** a call, rely on `lexshield_function_tool` (or call `await shield.evaluate(...)` inside the wrapped handler and raise before side effects).

See `middleware.py` for both patterns.

## Run the sketch

```bash
cd contrib/openai-agents
uv run --project ../.. python middleware.py
```

This runs a local policy evaluation demo without calling the OpenAI API.
