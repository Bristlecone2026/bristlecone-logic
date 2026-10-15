# Bristlecone Logic™ Developer Cookbooks

Pre-built recipes, code snippets, and configuration manifests to connect Bristlecone Logic runtime defenses, zero-auth sandboxes, and sovereign ledger settlement tools to any agent stack or development workflow.

---

### Quick Reference & Recipes

| Client / Framework | Guide / Source | Protocol / Transport | Primary Use Case | Zero-Auth Sandbox |
| :--- | :--- | :--- | :--- | :--- |
| **Terminal (curl)** | [cli_curl.md](./cli_curl.md) | HTTP REST | Instant 5-second smoke test from any shell | Yes (5 req/min) |
| **Claude Desktop** | [claude_desktop.md](./claude_desktop.md) | MCP (stdio) | Native desktop tool use via Model Context Protocol | Yes |
| **Cursor IDE** | [cursor_ide.md](./cursor_ide.md) | MCP (stdio) & Rules | Defend agent scraping and repair malformed JSON in Composer | Yes |
| **OpenAI (ChatGPT)** | [openai_chatgpt.md](./openai_chatgpt.md) | Python SDK Tool Calling | Pre-flight SSRF filters and AST math for GPT-4o agents | Yes |
| **xAI (Grok)** | [xai_grok.md](./xai_grok.md) | OpenAI-Compatible API | Query real-time validated XRPL ledger state in Grok | Yes |
| **Meta (Llama 3 / Muse)**| [meta_muse.md](./meta_muse.md) | Python REST / Tool Use | Pre-flight DNS validation and deterministic JSON repair | Yes |
| **LangChain & CrewAI** | [langchain_crewai.py](./langchain_crewai.py) | Python `@tool` Decorators | Standalone agent decorators with Pydantic input schemas | Yes |
| **XRPL Tools Engine** | [xrpl_ledger_tools.md](./xrpl_ledger_tools.md)| XRPL / Xylem Claims | DEX liquidity, AMM arbitrage, and ticket allocation | PaymentChannel |
| **Circle Arc & Base** | [circle_arc_usdc.md](./circle_arc_usdc.md) | HTTP 402 Paywall | Machine-to-machine USDC tool settlement | Arc L1 / Base L2 |

---

### Sandbox vs. Production Authentication

1. **Zero-Auth Sandbox (`https://api.bristleconelogic.com/v1/sandbox/*`):**
   * Rate limited to **5 requests per minute per IP address**.
   * Requires no API keys, tokens, or payment channels.
   * Ideal for integration testing, CI smoke checks, and quick experiments.

2. **Guarded Tools Gateway (`https://api.bristleconelogic.com/tools/*`):**
   * Enforces pre-flight SSRF checks, deterministic AST parsing, and payment validation.
   * Supports Bearer token authorization and HTTP 402 multi-rail stablecoin settlement.

3. **Sovereign XRPL Gateway (`https://xrp.bristleconelogic.com/tools/xrpl/*`):**
   * Governed by cryptographic off-chain Payment Channel claims via the Xylem engine.
   * Sub-millisecond verification with zero gas fees per micro-transaction.
