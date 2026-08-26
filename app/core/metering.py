import secrets
import redis.asyncio as aioredis
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
redis_client = aioredis.from_url("redis://redis:6379/0", decode_responses=True)

DEFAULT_INITIAL_CREDITS = 50

async def create_api_key(tenant_name: str) -> dict:
    key_secret = f"bl_live_{secrets.token_hex(16)}"
    key_data = {
        "tenant": tenant_name,
        "credits": str(DEFAULT_INITIAL_CREDITS),
        "active": "1"
    }
    await redis_client.hset(f"apikey:{key_secret}", mapping=key_data)
    return {"api_key": key_secret, "tenant": tenant_name, "credits": DEFAULT_INITIAL_CREDITS}

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> dict:
    """
    Read-only credential verification.
    Validates API key authenticity without decrementing credit balances.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Pass 'X-API-Key' header or register at /api/v1/auth/agent-register."
        )

    key_record = await redis_client.hgetall(f"apikey:{api_key}")
    if not key_record or key_record.get("active") != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or suspended API key."
        )

    return key_record

async def verify_metering(api_key: str = Security(API_KEY_HEADER)) -> dict:
    """
    Metered verification for billable endpoints.
    Validates key, checks credit availability, and decrements 1 credit.
    """
    key_record = await verify_api_key(api_key)

    current_credits = int(key_record.get("credits", 0))
    if current_credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient balance. Fund your API account with USDC on Base."
        )

    # Decrement 1 credit atomically
    new_credits = await redis_client.hincrby(f"apikey:{api_key}", "credits", -1)
    key_record["credits"] = str(new_credits)
    return key_record

# Redis connection & credit ledger helpers
import os
import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

async def deduct_credit(tenant_id: str, amount: int = 1) -> bool:
    """Deducts request credits from tenant Redis ledger."""
    if not tenant_id:
        return True
    try:
        remaining = await redis_client.hincrby(f"tenant:{tenant_id}", "credits", -amount)
        return remaining >= 0
    except Exception:
        return True

async def get_tenant_balance(tenant_id: str) -> int:
    """Fetches remaining credit balance for tenant."""
    if not tenant_id:
        return 1000
    try:
        bal = await redis_client.hget(f"tenant:{tenant_id}", "credits")
        return int(bal) if bal is not None else 1000
    except Exception:
        return 1000
