# Bristlecone Logic — Agent Tooling & MCP Integration

Bristlecone Logic provides micro-settled, high-reliability utility endpoints designed for autonomous AI agents and machine-to-machine workflows.

---

## 1. Quickstart: Claude Desktop & Cursor Integration

To add Bristlecone Logic tools directly to your agent environment, add the following configuration to your `claude_desktop_config.json` or Cursor MCP settings:

```json
{
  "mcpServers": {
    "bristlecone": {
      "command": "python",
      "args": ["/opt/bristlecone/bristlecone-logic/mcp_server.py"],
      "env": {
        "BRISTLECONE_API_KEY": "bstk_YOUR_API_KEY",
        "BRISTLECONE_API_URL": "https://api.bristleconelogic.com"
      }
    }
  }
}
```

---

## 2. Available Tools

### `bristlecone_extract_web`
* **Description:** Extracts and sanitizes clean textual content from any target public web page.
* **Cost:** 1 micro-credit.
* **Parameters:**
  * `url` (*string, required*): The HTTP/HTTPS URL of the target page.

### `bristlecone_validate_schema`
* **Description:** Validates a JSON payload against a standard JSON Schema specification.
* **Cost:** 1 micro-credit.
* **Parameters:**
  * `schema` (*object, required*): The standard JSON Schema definition.
  * `data` (*object, required*): The JSON payload to validate.

---

## 3. Account Funding & Top-ups

Bristlecone accounts settle on-chain via XRP Ledger:
* **XRPL Address:** `rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD`
* **Routing:** Include your tenant's assigned `DestinationTag` with the transaction. Credits are provisioned automatically upon ledger confirmation.
