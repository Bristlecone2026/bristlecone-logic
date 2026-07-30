import os
import hmac
import hashlib
import time
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request, Header, status
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


def verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify standard Stripe webhook signature using HMAC-SHA256."""
    if not sig_header or not secret:
        return False
    try:
        pairs = dict(item.split("=", 1) for item in sig_header.split(","))
        timestamp = pairs.get("t")
        signature = pairs.get("v1")
        if not timestamp or not signature:
            return False

        # Reject events older than 5 minutes to prevent replay attacks
        if abs(time.time() - int(timestamp)) > 300:
            return False

        signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode('utf-8')
        expected_sig = hmac.new(secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)
    except Exception:
        return False


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


@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db)
):
    """Webhook endpoint to process Stripe payment events and top up tenant credit balances."""
    raw_payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    # Validate signature if webhook secret is configured
    if webhook_secret and webhook_secret != "disabled":
        if not stripe_signature or not verify_stripe_signature(raw_payload, stripe_signature, webhook_secret):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature")

    try:
        event = json.loads(raw_payload)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    event_type = event.get("type")

    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata", {})
        tenant_id = metadata.get("tenant_id")

        # Determine top-up amount from explicit credit metadata or checkout amount_total (cents to USD)
        if "credit_amount_usd" in metadata:
            amount_usd = float(metadata["credit_amount_usd"])
        else:
            amount_usd = float(session.get("amount_total", 0)) / 100.0

        if not tenant_id or amount_usd <= 0:
            return {"status": "ignored", "reason": "Missing tenant_id or invalid amount"}

        # Atomically update tenant balance
        update_query = text("""
            UPDATE tenants
            SET credit_balance_usd = credit_balance_usd + :amount_usd
            WHERE id = :tenant_id
            RETURNING id, credit_balance_usd
        """)
        result = await db.execute(update_query, {"amount_usd": amount_usd, "tenant_id": tenant_id})
        row = result.fetchone()
        await db.commit()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found for top-up")

        return {
            "status": "success",
            "event": event_type,
            "tenant_id": tenant_id,
            "credited_usd": amount_usd,
            "new_balance_usd": float(row.credit_balance_usd)
        }

    return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}
