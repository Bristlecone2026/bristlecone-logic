# Cursor IDE Integration

Integrate Bristlecone Logic tools directly into Cursor Agent and Composer.

## Option A: Project-Scoped Configuration
Create `.cursor/mcp.json` in your repository root:
X0j {
  "mcpServers": {
    "bristlecone-security": {
      "command": "python",
      "args": ["-m", "app.mcp_stdio"]
    }
  }
}
