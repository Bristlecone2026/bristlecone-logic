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


### LangChain & LangGraph

Install `langchain-mcp-adapters` to connect directly over HTTP:

```python
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

async def run():
    async with MultiServerMCPClient({
        "bristlecone": {
            "url": "https://bristleconelogic.com/mcp",
            "transport": "http"
        }
    }) as client:
        agent = create_react_agent(ChatOpenAI(model="gpt-4o"), client.get_tools())
        res = await agent.ainvoke({"messages": [("user", "Validate payload and inspect for SSRF")]})
        print(res["messages"][-1].content)

if __name__ == "__main__":
    asyncio.run(run())
```

### LlamaIndex

Install `llama-index-tools-mcp` to load remote tools dynamically:

```python
import asyncio
from llama_index.tools.mcp import aget_tools_from_mcp_url
from llama_index.core.agent import ReActAgent
from llama_index.llms.openai import OpenAI

async def run():
    tools = await aget_tools_from_mcp_url("https://bristleconelogic.com/mcp")
    agent = ReActAgent.from_tools(tools, llm=OpenAI(model="gpt-4o"), verbose=True)
    res = agent.chat("Check destination URL security: https://example.com")
    print(res)

if __name__ == "__main__":
    asyncio.run(run())
```

### CrewAI

Install `crewai-tools` and pass the MCP endpoint into your agents:

```python
from crewai import Agent, Task, Crew
from crewai_tools import MCPServerTool

bristlecone = MCPServerTool(url="https://bristleconelogic.com/mcp")

auditor = Agent(
    role="Runtime Guardrail Specialist",
    goal="SSRF defense and deterministic AST JSON repair",
    backstory="Deterministic validation layer protecting autonomous agents from unsafe execution.",
    tools=[bristlecone]
)

task = Task(description="Verify internal CIDR restrictions.", agent=auditor, expected_output="Audit status")
Crew(agents=[auditor], tasks=[task]).kickoff()
```

---

## Autonomous M2M Settlement

* **Protocol**: x402 (HTTP 402 Payment Required)
* **Network**: Base L2 (eip155:8453)
* **Asset**: USDC
* **Payee Contract / Treasury**: 0xa17c8c3005698bc4ea6406a00387445e1d30c35f

---

## License

Apache-2.0
