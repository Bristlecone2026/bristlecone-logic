"""
Bristlecone Logic Cookbook: Deterministic Agent Resilience
Demonstrates auto-recovering from malformed or truncated LLM output using repair_json.
"""
import json
import urllib.request
import urllib.error

ENDPOINT = "https://bristleconelogic.com/mcp"

def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "bristlecone-cookbook/1.0"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    # Simulated malformed payload from an LLM that ran out of tokens or dropped closing syntax
    broken_agent_output = '{"status": "executing", "actions": [{"tool": "database_query", "params": {"id": 1024'

    print("--- Simulating Agent Pipeline Failure ---")
    print(f"Raw Output: {broken_agent_output}\n")

    # Native parse attempt
    try:
        json.loads(broken_agent_output)
        print("Standard json.loads: SUCCESS")
    except json.JSONDecodeError as exc:
        print(f"Standard json.loads: FAILED ({exc})")

    # Autonomous self-healing via Bristlecone repair_json
    print("\n--- Routing to Bristlecone Guard (repair_json) ---")
    mcp_response = call_mcp_tool("repair_json", {"raw_json": broken_agent_output})
    
    # Extract repaired result
    repaired_content = mcp_response.get("result", {}).get("content", [{}])[0].get("text", "")
    print(f"Repaired Output: {repaired_content}")
    
    parsed = json.loads(repaired_content)
    print(f"Parsed Object Keys: {list(parsed.keys())}")
    print(f"Reconstructed Action: {parsed['actions'][0]['tool']}")

if __name__ == "__main__":
    main()
