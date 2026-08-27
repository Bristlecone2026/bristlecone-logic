"""
Bristlecone Logic™ Blueprint: Pre-Execution Financial Guardrail
Validates order sizing via deterministic AST evaluation and strictly enforces payload schemas.
"""

from bristlecone_logic.client import BristleconeClient

client = BristleconeClient()

# 1. Target trade payload proposed by an autonomous agent
trade_payload = {
    "symbol": "ETH-USD",
    "side": "BUY",
    "allocation_pct": 0.05,
    "portfolio_value_usd": 125400.50,
}

# 2. Strict execution schema
order_schema = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "side": {"type": "string", "enum": ["BUY", "SELL"]},
        "allocation_pct": {"type": "number", "maximum": 0.10},
        "portfolio_value_usd": {"type": "number", "minimum": 0.0},
    },
    "required": ["symbol", "side", "allocation_pct", "portfolio_value_usd"],
}

# Step 1: Validate payload schema deterministically
schema_result = client.validate_schema(data=trade_payload, schema=order_schema)
if not schema_result.get("valid", False):
    raise ValueError(f"Guardrail tripped: Invalid order structure -> {schema_result.get('errors')}")

# Step 2: Compute position size deterministically outside LLM context
expression = f"{trade_payload['portfolio_value_usd']} * {trade_payload['allocation_pct']}"
eval_result = client.eval_expression(expression)

if eval_result.get("status") == "success":
    calculated_size_usd = eval_result["result"]
    print(f"[PASSED] Guardrail verified. Order size computed: ${calculated_size_usd:,.2f}")
else:
    raise RuntimeError(f"Calculation failed: {eval_result.get('error')}")
