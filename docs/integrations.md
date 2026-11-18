# Agent framework integrations

`pdfluent-mcp` is a stdio MCP server, so any framework with an MCP client can launch it. Each snippet starts the server with `--root` set to the folder your PDFs live in. The server only reads inside that folder, and tool paths must be absolute.

Install the server once: `pip install pdfluent-mcp`. The snippets use `python -m pdfluent_mcp`, which runs the same server as the `pdfluent-mcp` command.

## OpenAI Agents SDK

A runnable example is in [`examples/openai-agents-sdk`](../examples/openai-agents-sdk). The core is:

```python
import sys
from agents import Agent
from agents.mcp import MCPServerStdio

async with MCPServerStdio(
    name="pdfluent",
    params={"command": sys.executable, "args": ["-m", "pdfluent_mcp", "--root", "/path/to/documents"]},
    client_session_timeout_seconds=30,
) as server:
    agent = Agent(name="PDF reader", instructions="Use the pdfluent tools.", mcp_servers=[server])
```

## CrewAI

Needs `pip install "crewai-tools[mcp]"`.

```python
import sys
from crewai import Agent
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

params = StdioServerParameters(
    command=sys.executable,
    args=["-m", "pdfluent_mcp", "--root", "/path/to/documents"],
)

with MCPServerAdapter(params) as tools:
    reader = Agent(
        role="PDF reader",
        goal="Answer questions about local PDFs",
        backstory="Reads documents with the pdfluent tools.",
        tools=tools,
    )
```

## DSPy

Needs `pip install dspy mcp`. `dspy.Tool.from_mcp_tool` wraps each MCP tool.

```python
import sys
import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command=sys.executable,
    args=["-m", "pdfluent_mcp", "--root", "/path/to/documents"],
)

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        tools = [dspy.Tool.from_mcp_tool(session, t) for t in listed.tools]
        react = dspy.ReAct("question -> answer", tools=tools)
        result = await react.acall(question="Which pages of /path/to/documents/policy.pdf mention retention?")
```

Set the language model first with `dspy.configure(lm=dspy.LM(...))`. Keep the `async with` blocks open while the program runs.

## Vercel AI SDK

Needs `npm install ai @ai-sdk/mcp`.

```ts
import { createMCPClient } from '@ai-sdk/mcp';
import { Experimental_StdioMCPTransport } from '@ai-sdk/mcp/mcp-stdio';
import { generateText } from 'ai';

const client = await createMCPClient({
  transport: new Experimental_StdioMCPTransport({
    command: 'python',
    args: ['-m', 'pdfluent_mcp', '--root', '/path/to/documents'],
  }),
});

try {
  const tools = await client.tools();
  const { text } = await generateText({
    model, // any AI SDK model
    tools,
    prompt: 'Which pages of /path/to/documents/policy.pdf mention retention?',
  });
  console.log(text);
} finally {
  await client.close();
}
```

## Licence

`pdfluent-mcp` is AGPL-3.0 or commercial, like the `pdfluent` package it runs on. See the [README](../README.md#licence).
