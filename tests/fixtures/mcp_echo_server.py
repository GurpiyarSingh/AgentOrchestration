"""Tiny MCP server for tests (stdio): `add` (read-only) and `wipe` (destructive)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("echo")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def wipe(target: str) -> str:
    """Pretend to delete something (destructive)."""
    return f"wiped {target}"


if __name__ == "__main__":
    mcp.run()
