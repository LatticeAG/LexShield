# LangChain adapter (contrib)

Wrap [LangChain](https://python.langchain.com/) `StructuredTool` instances with `lexshield.Shield.guard` so policy runs before `invoke` / `ainvoke`.

**Not officially supported.** Copy `tool-guard.py` into your project or use it as a reference.

## Dev dependencies

```bash
pip install lexshield langchain-core
# or, from this monorepo:
uv sync
uv pip install langchain-core
```

`langchain-core` is enough for `StructuredTool`; full `langchain` is optional.

## Policy

```bash
lexshield init --pack baseline-deny
# or copy from examples/python-block-exfil/
```

## Usage

```python
from pathlib import Path

from langchain_core.tools import StructuredTool
from lexshield import Shield

from tool_guard import guard_structured_tool

shield = Shield.from_config(Path("lexshield.yaml"))

async def send_email(to: str, subject: str, body: str) -> dict:
    return {"status": "sent", "to": to}

raw_tool = StructuredTool.from_function(
    coroutine=send_email,
    name="send_email",
    description="Send an email",
)

guarded_tool = guard_structured_tool(shield, raw_tool)

# await guarded_tool.ainvoke({"to": "...", "subject": "...", "body": "..."})
```

`BLOCK` / `CHALLENGE` raise `LexShieldBlockedError` / `LexShieldChallengeError`. Catch them around `ainvoke` or let your agent executor surface the error.

## How it works

`guard_structured_tool` builds a new `StructuredTool` whose underlying function/coroutine is wrapped with `@shield.guard(tool=…)`. Keyword arguments from LangChain become LexShield `arguments`.

## Run the included demo

```bash
cd contrib/langchain
uv run --project ../.. python tool-guard.py
```

Expect `BLOCKED` when the demo passes an AWS key in the email body.
