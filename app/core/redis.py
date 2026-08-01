import os
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

redis_client = redis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True
)

async def get_redis():
    return redis_client
