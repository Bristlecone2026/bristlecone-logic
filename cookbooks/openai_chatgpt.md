# OpenAI (ChatGPT / Responses API) Integration Guide

Integrate Bristlecone Logic runtime security, pre-flight DNS auditing, and AST arithmetic evaluation into OpenAI Python SDK workflows (`gpt-4o`, `gpt-4o-mini`, `o1`).

### 1. Installation
Install the official OpenAI client and HTTPX:

```bash
pip install openai httpx
```

### 2. Implementation: Guarded Tool Calling
Define Bristlecone defensive tools in the OpenAI function-calling format and route model execution requests through the live sandbox endpoints.

```python
import json
import httpx
from openai import OpenAI

client = OpenAI()

# Define Bristlecone tool schema
tools = [
    {
        "type": "function",
        "function": {
            "name": "bristlecone_dns_audit",
            "description": "Pre-flight SSRF and private CIDR defense. Validates domain reachability and blocks private/metadata IP space.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "The destination hostname or IP to validate."
                    }
                },
                "required": ["domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bristlecone_eval_math",
            "description": "Deterministic, sandboxed AST arithmetic evaluation to prevent model calculation hallucination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to safely compute (e.g., '((1500 * 12) / 4) + 250.75')."
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

def execute_bristlecone_tool(name: str, arguments: dict) -> dict:
    base_url = "[https://api.bristleconelogic.com/v1/sandbox](https://api.bristleconelogic.com/v1/sandbox)"
    
    if name == "bristlecone_dns_audit":
        resp = httpx.post(f"{base_url}/audit-dns", json={"domain": arguments["domain"]}, timeout=5.0)
        return resp.json()
    elif name == "bristlecone_eval_math":
        resp = httpx.post(f"{base_url}/eval-expression", json={"expression": arguments["expression"]}, timeout=5.0)
        return resp.json()
    else:
        raise ValueError(f"Unknown tool: {name}")

# Example Agent Execution Loop
messages = [
    {"role": "system", "content": "You are an autonomous assistant protected by Bristlecone Logic runtime defenses."},
    {"role": "user", "content": "Verify if 169.254.169.254 is safe to fetch, and calculate ((1500 * 12) / 4) + 250.75."}
]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

response_message = response.choices[0].message
messages.append(response_message)

if response_message.tool_calls:
    for tool_call in response_message.tool_calls:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        tool_result = execute_bristlecone_tool(tool_name, tool_args)
        
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_name,
            "content": json.dumps(tool_result)
        })

    final_response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    print("Final Model Response:\n", final_response.choices[0].message.content)
```

### 3. Execution Verification
Running the script executes the tools against the zero-auth sandbox (`5 req/min/IP`). The DNS audit confirms CIDR blocking of `169.254.169.254`, and the AST evaluation returns `4750.75`.
