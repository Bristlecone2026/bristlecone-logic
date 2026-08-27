"""
Bristlecone Logic™ Blueprint: Autonomous JSON Recovery Loop
Prevents agent crash loops caused by unescaped quotes or truncated JSON structures.
"""

import json
from bristlecone_logic.client import BristleconeClient

client = BristleconeClient()

# Simulated malformed output from an LLM (unclosed quote and trailing bracket)
raw_agent_response = """
{
    "task": "summarize_findings",
    "status": "completed",
    "findings": ["Market liquidity steady", "Spread tightened
"""

def safe_parse_agent_output(raw_text: str) -> dict:
    try:
        # Attempt standard parse first
        return json.loads(raw_text)
    except Exception:
        print("[WARN] Standard JSON parser failed. Routing to Bristlecone Logic™ repair endpoint...")
        repair_result = client.repair_json(raw_text)
        if repair_result.get("repaired"):
            return repair_result["data"]
        raise RuntimeError("Payload irreparable.")

data = safe_parse_agent_output(raw_agent_response)
print("[PASSED] Payload successfully recovered:", data)
