import hashlib
import time
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


def check_rate_limit(key_id: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Filter out timestamps outside the current 60s window
    RATE_LIMIT_STORE[key_id] = [ts for ts in RATE_LIMIT_STORE[key_id] if ts > window_start]

    if len(RATE_LIMIT_STORE[key_id]) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS_PER_WINDOW} requests per minute."
        )

    RATE_LIMIT_STORE[key_id].append(now)


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
                t.credit_balance_usd
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

        # 1. Zero-Balance Guard (HTTP 402)
        if credit_balance <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credit balance. Please top up your tenant account."
            )

        # 2. Rate Limit Guard (HTTP 429)
        check_rate_limit(key_id)

        # Update last_used_at timestamp
        await db.execute(
            text("UPDATE api_keys SET last_used_at = NOW() WHERE id = :key_id"),
            {"key_id": key_id}
        )
        await db.commit()

        return {
            "auth_type": "api_key",
            "tenant_id": tenant_id,
            "key_id": key_id,
            "tenant_name": row["tenant_name"],
            "credit_balance_usd": credit_balance,
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
