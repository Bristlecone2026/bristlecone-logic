"""
Bristlecone Logic™ Blueprint: Autonomous JSON Recovery Loop
Prevents agent crash loops caused by unescaped quotes or truncated JSON structures.
"""

import json
from bristlecone_logic.client import BristleconeClient

client = BristleconeClient()

raw_agent_response = """
{
    "task": "summarize_findings",
    "status": "completed",
    "findings": ["Market liquidity steady", "Spread tightened
"""

def safe_parse_agent_output(raw_text: str) -> dict:
    try:
        return json.loads(raw_text)
    except Exception:
        print("[WARN] Standard JSON parser failed. Routing to Bristlecone Logic™ repair endpoint...")
        repair_result = client.repair_json(raw_text)
        if repair_result.get("repaired") or repair_result.get("success"):
            return repair_result.get("data") or repair_result.get("parsed") or repair_result
        raise RuntimeError(f"Payload irreparable: {repair_result}")

data = safe_parse_agent_output(raw_agent_response)
print("[PASSED] Payload successfully recovered:", data)
