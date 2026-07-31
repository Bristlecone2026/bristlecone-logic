from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException, status
from app.services.notifications import check_and_notify_low_balance

async def ensure_billing_schema(db: AsyncSession):
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS tenant_balances (
            tenant_id VARCHAR(255) PRIMARY KEY,
            balance_usd NUMERIC(12, 6) NOT NULL DEFAULT 100.000000,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS billing_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(255) NOT NULL,
            amount_usd NUMERIC(12, 6) NOT NULL,
            description VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await db.commit()

async def deduct_tenant_credits(tenant_id: str, cost_usd: float, description: str, db: AsyncSession) -> float:
    await ensure_billing_schema(db)

    # Seed balance if new tenant
    await db.execute(text("""
        INSERT INTO tenant_balances (tenant_id, balance_usd)
        VALUES (:tenant_id, 100.0)
        ON CONFLICT (tenant_id) DO NOTHING
    """), {"tenant_id": tenant_id})

    # Deduct cost atomically
    update_res = await db.execute(text("""
        UPDATE tenant_balances
        SET balance_usd = balance_usd - :cost, updated_at = CURRENT_TIMESTAMP
        WHERE tenant_id = :tenant_id AND balance_usd >= :cost
        RETURNING balance_usd
    """), {"tenant_id": tenant_id, "cost": cost_usd})

    row = update_res.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient balance to execute request."
        )

    new_balance = float(row.balance_usd)

    # Record ledger entry
    await db.execute(text("""
        INSERT INTO billing_ledger (tenant_id, amount_usd, description)
        VALUES (:tenant_id, :amount, :description)
    """), {"tenant_id": tenant_id, "amount": -cost_usd, "description": description})

    await db.commit()

    # Trigger automated low-balance check
    await check_and_notify_low_balance(tenant_id, new_balance, db)

    return new_balance

async def process_execution_billing(
    tenant_id: str,
    cost_usd: float = 0.001659,
    description: str = "Agent workload execution",
    db: AsyncSession = None,
    **kwargs
) -> dict:
    if "cost" in kwargs:
        cost_usd = kwargs["cost"]
    elif "billed_cost_usd" in kwargs:
        cost_usd = kwargs["billed_cost_usd"]

    new_balance = await deduct_tenant_credits(tenant_id, cost_usd, description, db)

    return {
        "success": True,
        "new_balance": new_balance,
        "cost_usd": cost_usd,
        "billed_cost_usd": cost_usd
    }
