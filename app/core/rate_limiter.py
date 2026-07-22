import time
from collections import defaultdict
from fastapi import HTTPException, Request, status

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        # Key: client_id/IP, Value: list of timestamps
        self.requests = defaultdict(list)

    async def __call__(self, request: Request):
        # Identify caller by X-API-Key header or fall back to client IP
        client_id = request.headers.get("X-API-Key") or request.client.host
        now = time.time()
        window_start = now - 60  # 60-second sliding window

        # Filter out timestamps older than 60 seconds
        self.requests[client_id] = [
            ts for ts in self.requests[client_id] if ts > window_start
        ]

        if len(self.requests[client_id]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: Maximum {self.requests_per_minute} requests per minute allowed.",
            )

        # Record current request timestamp
        self.requests[client_id].append(now)

# Default global rate limiter instance (e.g., 60 requests/minute)
limiter = RateLimiter(requests_per_minute=60)
