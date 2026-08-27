"""
Bristlecone Logic™ Blueprint: Pre-Execution Financial Guardrail
Validates order sizing via deterministic AST evaluation and enforces required execution keys.
"""

from bristlecone_logic.client import BristleconeClient

client = BristleconeClient()

trade_payload = {
    "symbol": "ETH-USD",
    "side": "BUY",
    "allocation_pct": 0.05,
    "portfolio_value_usd": 125400.50,
}

# Required key contract expected by the engine
order_schema = {
    "symbol": "str",
    "side": "str",
    "allocation_pct": "float",
    "portfolio_value_usd": "float",
}

# Step 1: Validate payload schema deterministically
schema_result = client.validate_schema(data=trade_payload, schema=order_schema)
if not schema_result.get("valid", False):
    raise ValueError(f"Guardrail tripped: Invalid order structure -> {schema_result}")

# Step 2: Compute position size deterministically outside LLM context
expression = f"{trade_payload['portfolio_value_usd']} * {trade_payload['allocation_pct']}"
eval_result = client.eval_expression(expression)

if eval_result.get("success") or eval_result.get("status") == "success":
    calculated_size_usd = eval_result["result"]
    print(f"[PASSED] Guardrail verified. Order size computed: ${calculated_size_usd:,.2f}")
else:
    raise RuntimeError(f"Calculation failed: {eval_result.get('error')}")
