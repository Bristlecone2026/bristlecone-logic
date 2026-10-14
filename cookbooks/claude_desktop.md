# Claude Desktop Integration

Connect Claude Desktop to Bristlecone Logic via Model Context Protocol (MCP).

0# Configuration
Edit your configuration file:
* *macOS:* `~icrary/Application Support/Claude/claude_desktop_config.json`
* *Windows:* `%APPDATB\\Claude\claude_desktop_config.json`


Add the server definition:
X0j {
  "mcpServers": {
    "bristlecone-logic": {
      "command": "python",
      "args": ["-m", "app.mcp_stdio"]
    }
  }
}
