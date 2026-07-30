import hashlib
import time
import asyncio
from collections import defaultdict
from typing import Optional, Dict, List
from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

# --- In-Memory Rate Limiter (Sliding Window) ---
RATE_LIMIT_STORE: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 60

# --- Quota Definitions (Tokens) ---
TIER_QUOTAS = {
    "free": {"daily": 100_000, "monthly": 1_000_000},
    "pro": {"daily": 2_000_000, "monthly": 20_000_000},
    "enterprise": {"daily": None, "monthly": None}
}


def check_rate_limit(key_id: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    RATE_LIMIT_STORE[key_id] = [ts for ts in RATE_LIMIT_STORE[key_id] if ts > window_start]

    if len(RATE_LIMIT_STORE[key_id]) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS_PER_WINDOW} requests per minute."
        )

    RATE_LIMIT_STORE[key_id].append(now)


async def check_quota_limits(tenant_id: str, tier: str, db: AsyncSession) -> None:
    limits = TIER_QUOTAS.get(tier, TIER_QUOTAS["free"])
    
    # Unlimited tier bypass
    if limits["daily"] is None and limits["monthly"] is None:
        return

    query = text("""
        SELECT 
            COALESCE(SUM(CASE WHEN created_at >= CURRENT_DATE THEN total_tokens ELSE 0 END), 0) AS daily_tokens,
            COALESCE(SUM(total_tokens), 0) AS monthly_tokens
        FROM llm_usage_ledger
        WHERE tenant_id = :tenant_id
          AND created_at >= date_trunc('month', CURRENT_DATE)
    """)

    result = await db.execute(query, {"tenant_id": tenant_id})
    row = result.mappings().first()

    if row:
        daily_used = int(row["daily_tokens"])
        monthly_used = int(row["monthly_tokens"])

        if limits["daily"] and daily_used >= limits["daily"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily token quota exceeded for tier '{tier}'. Limit: {limits['daily']:,}, Used: {daily_used:,}"
            )

        if limits["monthly"] and monthly_used >= limits["monthly"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly token quota exceeded for tier '{tier}'. Limit: {limits['monthly']:,}, Used: {monthly_used:,}"
            )


async def get_tenant_context(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    token = parts[1]

    if token.startswith("bcl_"):
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        query = text("""
            SELECT 
                k.id AS key_id,
                k.tenant_id,
                k.is_active AS key_active,
                t.name AS tenant_name,
                t.credit_balance_usd,
                COALESCE(t.tier, 'free') AS tier
            FROM api_keys k
            JOIN tenants t ON k.tenant_id = t.id
            WHERE k.key_hash = :key_hash
        """)

        result = await db.execute(query, {"key_hash": key_hash})
        row = result.mappings().first()

        if not row or not row["key_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or deactivated API Key"
            )

        key_id = str(row["key_id"])
        tenant_id = str(row["tenant_id"])
        credit_balance = float(row["credit_balance_usd"])
        tier = str(row["tier"])

        # 1. Zero-Balance Guard (HTTP 402)
        if credit_balance <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credit balance. Please top up your tenant account."
            )

        # 2. Rate Limit Guard (HTTP 429)
        check_rate_limit(key_id)

        # 3. Quota Enforcement Guard (HTTP 429)
        await check_quota_limits(tenant_id, tier, db)

        # Non-blocking timestamp update
        asyncio.create_task(
            db.execute(
                text("UPDATE api_keys SET last_used_at = NOW() WHERE id = :key_id"),
                {"key_id": key_id}
            )
        )

        return {
            "auth_type": "api_key",
            "tenant_id": tenant_id,
            "key_id": key_id,
            "tenant_name": row["tenant_name"],
            "credit_balance_usd": credit_balance,
            "tier": tier,
            "user_id": None,
            "email": "unknown",
            "full_name": None,
            "organization_id": "org_default"
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unsupported or invalid token type"
    )


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[1].startswith("bcl_"):
            return await get_tenant_context(authorization, db)

    return {
        "id": "usr_default_admin",
        "email": "admin@bristleconelogic.com",
        "full_name": "Admin User",
        "is_active": True,
        "organization_id": "org_default"
    }


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    if not current_user.get("is_active"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
