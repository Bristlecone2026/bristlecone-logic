from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

MODEL_PRICING = {
    "gpt-4o": {"blended": 4.74},
    "gpt-4o-mini": {"blended": 0.30},
    "claude-3-5-sonnet": {"blended": 6.00},
    "bristlecone-orchestrator-v1": {"blended": 2.00},
}

async def process_execution_billing(
    db: AsyncSession,
    tenant_id: str,
    provider: str,
    model: str,
    total_tokens: int
) -> dict:
    pricing = MODEL_PRICING.get(model, {"blended": 2.00})
    rate_per_million = pricing.get("blended", 2.00)
    billed_cost_usd = round((total_tokens / 1_000_000.0) * rate_per_million, 6)

    query = text("SELECT credit_balance_usd FROM tenants WHERE id = :tenant_id FOR UPDATE")
    result = await db.execute(query, {"tenant_id": tenant_id})
    row = result.fetchone()

    if not row:
        return {"success": False, "error": "Tenant not found"}

    current_balance = float(row.credit_balance_usd)
    if current_balance < billed_cost_usd:
        return {"success": False, "error": "Insufficient credit balance"}

    deduct_query = text("""
        UPDATE tenants
        SET credit_balance_usd = credit_balance_usd - :cost
        WHERE id = :tenant_id
    """)
    await db.execute(deduct_query, {"cost": billed_cost_usd, "tenant_id": tenant_id})

    ledger_query = text("""
        INSERT INTO llm_usage_ledger (tenant_id, provider, model_requested, total_tokens, billed_cost_usd)
        VALUES (:tenant_id, :provider, :model, :tokens, :cost)
    """)
    await db.execute(ledger_query, {
        "tenant_id": tenant_id,
        "provider": provider,
        "model": model,
        "tokens": total_tokens,
        "cost": billed_cost_usd
    })

    await db.commit()

    return {
        "success": True,
        "billed_cost_usd": billed_cost_usd,
        "remaining_balance_usd": current_balance - billed_cost_usd
    }
