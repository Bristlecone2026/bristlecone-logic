import sys
import asyncio
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP stdio server
mcp = FastMCP("bristlecone-logic")

@mcp.tool()
def health_check() -> str:
    """Returns the operational status of Bristlecone Logic utilities."""
    return "Bristlecone Logic utilities active."

if __name__ == "__main__":
    mcp.run(transport="stdio")
