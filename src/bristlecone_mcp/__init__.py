"""
Bristlecone Logic - Model Context Protocol (MCP) Server
Native stdio tool execution server for AI agents and developer workflows.
"""

import os
import asyncio
import httpx
from mcp.server.mcpserver import MCPServer

BRISTLECONE_API_URL = os.getenv("BRISTLECONE_API_URL", "https://api.bristleconelogic.com")
BRISTLECONE_API_KEY = os.getenv("BRISTLECONE_API_KEY", "")

server = MCPServer(name="bristlecone-logic")


@server.tool(
    name="bristlecone_extract_web",
    description="Extract and sanitize clean textual content from any target web page. Costs 1 micro-credit.",
)
async def extract_web(url: str) -> str:
    """Extract and sanitize clean textual content from a web page."""
    if not BRISTLECONE_API_KEY:
        return "Error: BRISTLECONE_API_KEY environment variable is not configured."

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BRISTLECONE_API_URL}/api/v1/tools/extract-web",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": BRISTLECONE_API_KEY,
            },
            json={"url": url},
        )

        if response.status_code != 200:
            return f"API Error {response.status_code}: {response.text}"

        data = response.json()
        return f"Title: {data.get('title')}\n\nContent:\n{data.get('clean_text')}"


@server.tool(
    name="bristlecone_validate_schema",
    description="Validate a JSON payload against a standard JSON Schema definition. Costs 1 micro-credit.",
)
async def validate_schema(schema: dict, data: dict) -> str:
    """Validate a JSON payload against a JSON schema."""
    if not BRISTLECONE_API_KEY:
        return "Error: BRISTLECONE_API_KEY environment variable is not configured."

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{BRISTLECONE_API_URL}/api/v1/tools/validate-schema",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": BRISTLECONE_API_KEY,
            },
            json={"schema": schema, "data": data},
        )

        if response.status_code != 200:
            return f"API Error {response.status_code}: {response.text}"

        res = response.json()
        return f"Valid: {res.get('valid')}\nErrors: {res.get('errors', [])}"


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())

def main():
    """CLI entrypoint for uvx / pip executions."""
    asyncio.run(server.run_stdio_async())

if __name__ == "__main__":
    main()
