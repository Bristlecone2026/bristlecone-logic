# Cursor IDE Integration Guide

Integrate Bristlecone Logic runtime security, schema repair, and XRPL tools directly into Cursor Agent, Composer, and inline chat workflows using the Model Context Protocol (MCP).

### 1. Project-Level Configuration (`.cursor/mcp.json`)
Create or edit `.cursor/mcp.json` in your repository root to configure the Bristlecone tool server for the project workspace:

```json
{
  "mcpServers": {
    "bristlecone-security": {
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

### 2. Global Cursor Settings
To make Bristlecone tools available across all Cursor projects:
1. Open Cursor Settings (`Ctrl + Shift + J` or `Cmd + Shift + J`).
2. Navigate to **Features** -> **MCP Servers**.
3. Click **Add New MCP Server**:
   * **Name:** `bristlecone-security`
   * **Type:** `stdio`
   * **Command:** `python -m app.mcp_stdio`

### 3. Cursor System Rules (`.cursorrules`)
Instruct Cursor Composer and Agent to automatically route network operations and unformatted JSON payloads through Bristlecone guards:

```markdown
# Bristlecone Defensive Architecture Rules

When fetching documentation, scraping external sites, or processing untrusted network endpoints:
1. Always invoke `bristlecone-security:bristlecone_audit_dns` or `bristlecone-security:extract_web` before opening raw sockets.
2. If an LLM-generated JSON payload fails initial schema parsing, route it through `bristlecone-security:bristlecone_repair_json` rather than re-prompting.
3. For deterministic arithmetic or mathematical formulas, use `bristlecone-security:bristlecone_eval_math` to avoid LLM floating-point hallucination.
```

### 4. Verification in Cursor Composer
Open Cursor Composer (`Ctrl + I` or `Cmd + I`) and run:
> "Use bristlecone_eval_math to calculate ((1500 * 12) / 4) + 250.75"

The agent will execute the tool via stdio and return `4750.75` through the AST sandbox.
