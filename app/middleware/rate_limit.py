import time
import hashlib
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.window = 60.0
        self.tenant_buckets = defaultdict(deque)
        self.bypassed_paths = {"/health", "/api/v1/health", "/metrics", "/api/v1/metrics", "/docs", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Check path bypasses
        if path in self.bypassed_paths or path.startswith("/api/v1/admin/"):
            return await call_next(request)

        # Extract tenant key: X-API-Key > X-Tenant-ID > Client IP
        api_key = request.headers.get("X-API-Key")
        raw_tenant = request.headers.get("X-Tenant-ID")

        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
            tenant_id = f"key_{key_hash}"
        elif raw_tenant:
            tenant_id = raw_tenant
        else:
            tenant_id = request.client.host if request.client else "anonymous"

        now = time.time()
        bucket = self.tenant_buckets[tenant_id]

        # Purge timestamps outside sliding 60-second window
        while bucket and bucket[0] <= now - self.window:
            bucket.popleft()

        # Check rate limit
        if len(bucket) >= self.rpm:
            oldest = bucket[0]
            retry_after = max(1, int(self.window - (now - oldest)))
            
            headers = {
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(self.rpm),
                "X-RateLimit-Remaining": "0"
            }
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "tenant_id": tenant_id,
                    "limit_rpm": self.rpm,
                    "message": f"Rate limit of {self.rpm} requests per minute exceeded. Try again in {retry_after} seconds."
                },
                headers=headers
            )

        # Record current request timestamp
        bucket.append(now)
        remaining = max(0, self.rpm - len(bucket))

        # Process request
        response = await call_next(request)

        # Attach rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
