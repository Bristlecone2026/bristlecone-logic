import time
import logging
from fastapi import HTTPException, status
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

class RedisRateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60

    async def check_rate_limit(self, identifier: str) -> dict:
        """
        Sliding-window rate limiter using Redis sorted sets (ZSET).
        Key format: rate_limit:{identifier}
        """
        key = f"rate_limit:{identifier}"
        now = time.time()
        window_start = now - self.window_seconds

        async with redis_client.pipeline(transaction=True) as pipe:
            # 1. Clear old timestamps outside current window
            pipe.zremrangebyscore(key, 0, window_start)
            # 2. Count requests in current window
            pipe.zcard(key)
            # 3. Add current request timestamp
            pipe.zadd(key, {str(now): now})
            # 4. Set TTL on the key to automatically clean up inactive keys
            pipe.expire(key, self.window_seconds + 1)
            
            results = await pipe.execute()

        request_count = results[1]

        if request_count >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for identifier: {identifier}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute allowed.",
                headers={"Retry-After": str(self.window_seconds)}
            )

        remaining = max(0, self.requests_per_minute - request_count - 1)
        return {
            "limit": self.requests_per_minute,
            "remaining": remaining
        }
