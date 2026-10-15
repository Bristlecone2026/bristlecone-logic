# Claude Desktop Integration Guide

Connect Anthropic's Claude Desktop application directly to Bristlecone Logic tools using the Model Context Protocol (MCP) over local standard I/O (`stdio`).

### 1. Configuration File Locations
Locate and edit your Claude Desktop configuration file based on your operating system:
* **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
* **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

### 2. Server Configuration
Add the `bristlecone-logic` server block to the `mcpServers` object:

```json
{
  "mcpServers": {
    "bristlecone-logic": {
      "command": "python",
      "args": ["-m", "app.mcp_stdio"],
      "env": {
        "BRISTLECONE_BASE_URL": "[https://api.bristleconelogic.com](https://api.bristleconelogic.com)",
        "BRISTLECONE_API_KEY": "YOUR_API_KEY_HERE"
      }
    }
  }
}
```

*Note: For local development, set `"BRISTLECONE_BASE_URL": "http://127.0.0.1:8000"`.*

### 3. Exposing Tools to Claude
Once configured, restart Claude Desktop. The hammer icon in the bottom right corner will display the active Bristlecone toolset:
* `bristlecone_audit_dns`: Pre-flight SSRF and private CIDR defense.
* `bristlecone_repair_json`: Deterministic JSON syntax and schema recovery.
* `bristlecone_eval_math`: Sandboxed AST evaluation.
* `bristlecone_xrpl_ledger`: Real-time validated XRPL ledger state.

### 4. Verification Prompt
In a new Claude Desktop chat session, verify execution with this prompt:
> "Run a DNS audit on domain 169.254.169.254 using Bristlecone tools and explain the security result."
