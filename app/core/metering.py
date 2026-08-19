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

async def verify_metering(api_key: str = Security(API_KEY_HEADER)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Pass 'X-API-Key' header or register at /api/v1/auth/register."
        )

    key_record = await redis_client.hgetall(f"apikey:{api_key}")
    if not key_record or key_record.get("active") != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or suspended API key."
        )

    current_credits = int(key_record.get("credits", 0))
    if current_credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient balance. Fund your API account with USDC on Base."
        )

    await redis_client.hincrby(f"apikey:{api_key}", "credits", -1)
    return key_record
