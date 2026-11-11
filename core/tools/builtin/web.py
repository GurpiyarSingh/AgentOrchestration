"""HTTP GET tool."""

from __future__ import annotations

import httpx
from langchain_core.tools import BaseTool, StructuredTool, ToolException

MAX_BODY_CHARS = 20_000


def make_http_get(transport: httpx.AsyncBaseTransport | None = None, timeout_s: float = 15.0) -> BaseTool:
    """Build the http_get tool. `transport` lets tests inject a mock transport."""

    async def http_get(url: str) -> str:
        """Fetch a web page or API URL with HTTP GET and return the status code and the body as text.

        Only http and https URLs are allowed. Long bodies are truncated.
        """
        if not url.lower().startswith(("http://", "https://")):
            raise ToolException("Only http:// and https:// URLs are allowed.")
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=timeout_s,
                follow_redirects=True,
                headers={"User-Agent": "agent-orchestration-poc/0.1"},
            ) as client:
                resp = await client.get(url)
        except httpx.TimeoutException as e:
            raise ToolException(f"Request timed out after {timeout_s:.0f}s.") from e
        except httpx.HTTPError as e:
            raise ToolException(f"Request failed: {type(e).__name__}.") from e

        body = resp.text
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + f"\n[truncated: {len(resp.text) - MAX_BODY_CHARS} more chars]"
        ctype = resp.headers.get("content-type", "unknown")
        return f"HTTP {resp.status_code} ({ctype})\n\n{body}"

    return StructuredTool.from_function(
        coroutine=http_get,
        name="builtin__http_get",
        description=http_get.__doc__ or "",
        handle_tool_error=True,
    )
