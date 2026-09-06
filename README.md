# Bristlecone Guard

Deterministic runtime guardrails and M2M (machine-to-machine) safety primitives for autonomous AI agent pipelines.

Exposes high-speed validation, AST evaluation, schema enforcement, and web/DNS auditing tools via standard HTTP and the Anthropic Model Context Protocol (MCP).

---

## Tools

* **audit_dns**: Forward DNS resolution and network routing verification. Guards against Server-Side Request Forgery (SSRF).
* **chunk_text**: Sliding-window text segmentation with configurable overlap for RAG ingestion.
* **eval_expression**: Deterministic mathematical and boolean expression evaluation inside an isolated AST sandbox.
* **extract_web**: Sanitized server-side text extraction from public web pages.
* **repair_json**: Syntax repair for broken, malformed, or unclosed JSON strings produced by LLMs.
* **validate_schema**: Strict key-level schema validation for agent input/output payloads.

---

## Public Endpoints

* **Base URL**: https://bristleconelogic.com
* **MCP Transport (SSE)**: https://bristleconelogic.com/mcp
* **Agentic Discovery Catalog**: https://bristleconelogic.com/.well-known/ai-catalog.json
* **Resource Manifest**: https://bristleconelogic.com/.well-known/ai-resources.json
* **API Documentation**: https://bristleconelogic.com/docs

---

## Connecting to Claude Desktop / MCP Clients

Add the following to your claude_desktop_config.json:

{
  "mcpServers": {
    "bristlecone-guard": {
      "url": "https://bristleconelogic.com/mcp"
    }
  }
}

For authenticated or metered tenant access:

{
  "mcpServers": {
    "bristlecone-guard": {
      "url": "https://bristleconelogic.com/mcp",
      "headers": {
        "Authorization": "Bearer bl_live_YOUR_API_KEY"
      }
    }
  }
}

---

## Autonomous M2M Settlement

* **Protocol**: x402 (HTTP 402 Payment Required)
* **Network**: Base L2 (eip155:8453)
* **Asset**: USDC
* **Payee Contract / Treasury**: 0xa17c8c3005698bc4ea6406a00387445e1d30c35f

---

## License

Apache-2.0
