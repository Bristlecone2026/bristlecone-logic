import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request
import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Corrected Atomic Lua script using INCRBYFLOAT for floating point subtraction
METER_LUA = """
local rate_key = KEYS[1]
local balance_key = KEYS[2]
local cost = tonumber(ARGV[1])
local max_rate = tonumber(ARGV[2])

local current_reqs = redis.call('INCR', rate_key)
if current_reqs == 1 then
    redis.call('EXPIRE', rate_key, 1)
end
if current_reqs > max_rate then
    return {429, tostring(current_reqs)}
end

local current_bal = tonumber(redis.call('GET', balance_key) or "0")
if current_bal < cost then
    return {402, tostring(current_bal)}
end

-- INCRBYFLOAT with negative cost performs atomic floating point subtraction
local new_bal = redis.call('INCRBYFLOAT', balance_key, -cost)
return {200, tostring(new_bal)}
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(
        REDIS_URL, 
        decode_responses=True,
        max_connections=100
    )
    yield
    await app.state.redis.close()

app = FastAPI(title="Bristlecone M2M API", lifespan=lifespan)

@app.api_route("/api/v1/keys/test-metered", methods=["GET", "POST"])
async def metered_endpoint(request: Request, x_api_key: str = Header(default="bl_test_key_12345")):
    tenant_id = "4c9219ad-db71-4bb2-96ca-c1c109c781eb"
    api_key_id = "85b379c8-6b70-4123-af8f-4c04ab4e3d16"

    rate_key = f"rate:{tenant_id}"
    balance_key = f"balance:{tenant_id}"

    redis_conn = request.app.state.redis

    try:
        res = await redis_conn.eval(METER_LUA, 2, rate_key, balance_key, "0.01", "60")
        status_code = int(res[0])
        val = float(res[1])

        if status_code == 429:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        elif status_code == 402:
            raise HTTPException(status_code=402, detail="Insufficient balance")

        await redis_conn.xadd(
            "api_usage_stream",
            {
                "tenant_id": tenant_id,
                "api_key_id": api_key_id,
                "endpoint": "/api/v1/keys/test-metered",
                "units_consumed": "1",
                "cost": "0.010000",
                "new_balance": str(val)
            }
        )

        return {"status": "success", "tenant_id": tenant_id, "remaining_balance": val}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
