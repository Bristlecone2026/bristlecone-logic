# xAI (Grok) Integration Guide

Integrate Bristlecone Logic runtime defense tools and live XRPL mainnet state into xAI Grok models (`grok-2`, `grok-3`, `grok-beta`) using the OpenAI-compatible SDK endpoint.

### 1. Installation
Install the required HTTP and client libraries:

```bash
pip install openai httpx
```

### 2. Implementation: Function Calling with Grok
Point the standard OpenAI client at xAI's API base (`https://api.x.ai/v1`) and register Bristlecone tools for sovereign ledger reads and runtime defense.

```python
import os
import json
import httpx
from openai import OpenAI

# Initialize client against xAI base endpoint
client = OpenAI(
    api_key=os.environ.get("XAI_API_KEY", "YOUR_XAI_API_KEY"),
    base_url="[https://api.x.ai/v1](https://api.x.ai/v1)"
)

# Define Bristlecone tools for Grok
tools = [
    {
        "type": "function",
        "function": {
            "name": "bristlecone_xrpl_ledger",
            "description": "Retrieves real-time validated ledger state, index, and close timestamp from the XRPL Mainnet.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bristlecone_dns_audit",
            "description": "Pre-flight SSRF protection and private CIDR blocking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Hostname or IP address to audit"
                    }
                },
                "required": ["domain"]
            }
        }
    }
]

def execute_bristlecone_sandbox(tool_name: str, args: dict) -> dict:
    base_url = "[https://api.bristleconelogic.com/v1/sandbox](https://api.bristleconelogic.com/v1/sandbox)"
    
    if tool_name == "bristlecone_xrpl_ledger":
        resp = httpx.get(f"{base_url}/xrpl-ledger", timeout=5.0)
        return resp.json()
    elif tool_name == "bristlecone_dns_audit":
        resp = httpx.post(f"{base_url}/audit-dns", json={"domain": args["domain"]}, timeout=5.0)
        return resp.json()
    raise ValueError(f"Unknown tool: {tool_name}")

# Run agent prompt through Grok
messages = [
    {"role": "system", "content": "You are a financial and infrastructure agent leveraging Bristlecone Logic tools."},
    {"role": "user", "content": "What is the latest validated XRPL ledger index and timestamp?"}
]

response = client.chat.completions.create(
    model="grok-beta",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

message = response.choices[0].message
messages.append(message)

if message.tool_calls:
    for tool_call in message.tool_calls:
        fn_name = tool_call.function.name
        fn_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
        output = execute_bristlecone_sandbox(fn_name, fn_args)
        
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": fn_name,
            "content": json.dumps(output)
        })

    final_resp = client.chat.completions.create(
        model="grok-beta",
        messages=messages
    )
    print("Grok Response:\n", final_resp.choices[0].message.content)
```

### 3. Execution Verification
The script polls the zero-auth sandbox (`https://api.bristleconelogic.com/v1/sandbox/xrpl-ledger`), parses the current mainnet ledger sequence, and feeds the validated payload into Grok's execution context.
