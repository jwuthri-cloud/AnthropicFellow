"""Call Parallax MCP tools over stdio, for sessions where the ``parallax`` MCP server is not loaded.

Parallax is the local research workspace in the sibling ``Helper`` folder (see
``.claude/skills/parallax/SKILL.md``). This starts its MCP server for one call and prints the
result.

Usage: uv run python scripts/parallax.py TOOL ['{"json": "arguments"}']
       uv run python scripts/parallax.py --tools          # list tools and their input schemas
Environment: PARALLAX_HELPER (default ../Helper), PARALLAX_WORKSPACE_ID (default "default").
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(os.environ.get("PARALLAX_HELPER", ROOT.parent / "Helper")).resolve()


def server() -> StdioServerParameters:
    """The Parallax MCP server, on the same data directory as the app."""
    return StdioServerParameters(
        command=shutil.which("node") or "node",
        args=[str(HELPER / "node_modules/tsx/dist/cli.mjs"), str(HELPER / "mcp/server.ts")],
        cwd=str(HELPER),
        env={
            "PATH": os.environ.get("PATH", ""),
            "PARALLAX_DATA_DIR": str(HELPER / "data"),
            "PARALLAX_WORKSPACE_ID": os.environ.get("PARALLAX_WORKSPACE_ID", "default"),
            "PARALLAX_RESEARCH_ROOT": str(ROOT),
        },
    )


@asynccontextmanager
async def parallax():
    """Yield ``call(tool, **arguments)``, which returns the tool's JSON result (or text)."""
    async with stdio_client(server()) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        async def call(tool: str, **arguments: object) -> object:
            result = await session.call_tool(tool, arguments)
            text = "".join(getattr(block, "text", "") for block in result.content)
            if result.is_error:
                raise RuntimeError(f"{tool}: {text}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text

        yield call


async def main() -> None:
    async with stdio_client(server()) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        if sys.argv[1] == "--tools":
            for tool in (await session.list_tools()).tools:
                print(f"## {tool.name}\n{tool.description}\n{json.dumps(tool.input_schema)}\n")
            return
        arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        result = await session.call_tool(sys.argv[1], arguments)
        print("".join(getattr(block, "text", "") for block in result.content))
        sys.exit(1 if result.is_error else 0)


if __name__ == "__main__":
    asyncio.run(main())
