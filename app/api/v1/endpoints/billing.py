from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_tenant_context

router = APIRouter()

TIER_QUOTAS = {
    "free": {"daily": 100_000, "monthly": 1_000_000},
    "pro": {"daily": 2_000_000, "monthly": 20_000_000},
    "enterprise": {"daily": 50_000_000, "monthly": 500_000_000}
}


@router.get("/balance")
async def get_balance(
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve current credit balance and tier assignment."""
    tenant_id = tenant_context["tenant_id"]
    query = text("SELECT credit_balance_usd, tier, name FROM tenants WHERE id = :tenant_id")
    result = await db.execute(query, {"tenant_id": tenant_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {
        "tenant_id": tenant_id,
        "tenant_name": row.name,
        "credit_balance_usd": float(row.credit_balance_usd),
        "tier": row.tier
    }


@router.get("/usage")
async def get_usage(
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve daily/monthly token consumption, costs, and remaining tier limits."""
    tenant_id = tenant_context["tenant_id"]
    tier = tenant_context.get("tier", "free").lower()
    limits = TIER_QUOTAS.get(tier, TIER_QUOTAS["free"])

    query = text("""
        SELECT 
            COALESCE(SUM(CASE WHEN created_at >= DATE_TRUNC('day', NOW()) THEN total_tokens ELSE 0 END), 0) AS daily_tokens,
            COALESCE(SUM(CASE WHEN created_at >= DATE_TRUNC('month', NOW()) THEN total_tokens ELSE 0 END), 0) AS monthly_tokens,
            COALESCE(SUM(CASE WHEN created_at >= DATE_TRUNC('day', NOW()) THEN billed_cost_usd ELSE 0 END), 0) AS daily_cost_usd,
            COALESCE(SUM(CASE WHEN created_at >= DATE_TRUNC('month', NOW()) THEN billed_cost_usd ELSE 0 END), 0) AS monthly_cost_usd
        FROM llm_usage_ledger
        WHERE tenant_id = :tenant_id
    """)
    result = await db.execute(query, {"tenant_id": tenant_id})
    row = result.fetchone()

    daily_used = int(row.daily_tokens) if row else 0
    monthly_used = int(row.monthly_tokens) if row else 0
    daily_cost = float(row.daily_cost_usd) if row else 0.0
    monthly_cost = float(row.monthly_cost_usd) if row else 0.0

    return {
        "tenant_id": tenant_id,
        "tier": tier,
        "usage": {
            "daily": {
                "tokens_used": daily_used,
                "token_limit": limits["daily"],
                "tokens_remaining": max(0, limits["daily"] - daily_used),
                "cost_usd": round(daily_cost, 6)
            },
            "monthly": {
                "tokens_used": monthly_used,
                "token_limit": limits["monthly"],
                "tokens_remaining": max(0, limits["monthly"] - monthly_used),
                "cost_usd": round(monthly_cost, 6)
            }
        }
    }


@router.get("/history")
async def get_usage_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve paginated usage history log."""
    tenant_id = tenant_context["tenant_id"]

    count_query = text("SELECT COUNT(*) FROM llm_usage_ledger WHERE tenant_id = :tenant_id")
    total_records = (await db.execute(count_query, {"tenant_id": tenant_id})).scalar() or 0

    history_query = text("""
        SELECT id, provider, model_requested, total_tokens, latency_ms, billed_cost_usd, created_at
        FROM llm_usage_ledger
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(history_query, {
        "tenant_id": tenant_id,
        "limit": limit,
        "offset": offset
    })
    rows = result.fetchall()

    items = [
        {
            "id": str(row.id),
            "provider": row.provider,
            "model_requested": row.model_requested,
            "total_tokens": row.total_tokens,
            "latency_ms": row.latency_ms,
            "billed_cost_usd": float(row.billed_cost_usd),
            "created_at": row.created_at.isoformat() if row.created_at else None
        }
        for row in rows
    ]

    return {
        "tenant_id": tenant_id,
        "total": total_records,
        "limit": limit,
        "offset": offset,
        "items": items
    }
