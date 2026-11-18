"""Run pdfluent-mcp from the OpenAI Agents SDK over stdio.

Two modes:

  python main.py report.pdf --offline
      Starts the server, lists its tools and calls extract_markdown once.
      No model and no API key needed.

  python main.py report.pdf "Which pages mention retention?"
      Hands the server to an agent. Needs OPENAI_API_KEY.

The server only reads files under --root, so the PDF's folder is passed as
the root.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


def make_server(root: Path) -> MCPServerStdio:
    return MCPServerStdio(
        name="pdfluent",
        params={
            "command": sys.executable,
            "args": ["-m", "pdfluent_mcp", "--root", str(root)],
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    )


async def offline(pdf: Path) -> None:
    async with make_server(pdf.parent) as server:
        tools = await server.list_tools()
        print("tools:", ", ".join(t.name for t in tools))
        result = await server.call_tool("extract_markdown", {"path": str(pdf)})
        text = "".join(getattr(c, "text", "") for c in result.content)
        print(text[:500])


async def ask(pdf: Path, question: str) -> None:
    async with make_server(pdf.parent) as server:
        agent = Agent(
            name="PDF reader",
            instructions=f"Answer questions about {pdf} using the pdfluent tools.",
            mcp_servers=[server],
        )
        result = await Runner.run(agent, question)
        print(result.final_output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("question", nargs="?", default="Summarise this document.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    pdf = args.pdf.resolve()
    asyncio.run(offline(pdf) if args.offline else ask(pdf, args.question))


if __name__ == "__main__":
    main()
