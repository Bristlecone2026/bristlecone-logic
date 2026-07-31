import time
import logging
from collections import defaultdict, deque
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("bristlecone.rate_limiter")

REQUEST_HISTORY = defaultdict(deque)

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if (
            not path.startswith("/api/v1/") 
            or path.startswith("/api/v1/admin/")
            or path in ["/health", "/api/v1/health", "/metrics", "/api/v1/metrics", "/docs", "/openapi.json"]
        ):
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID") or getattr(request.state, "tenant_id", None) or request.client.host
        rate_limit_rpm = getattr(request.state, "rate_limit_rpm", 60)

        now = time.time()
        window_start = now - 60.0
        history = REQUEST_HISTORY[tenant_id]

        while history and history[0] < window_start:
            history.popleft()

        if len(history) >= rate_limit_rpm:
            retry_after = int(60 - (now - history0[0]))  if history else 60
            logger.warning(f"Rate limit exceeded for tenant {tenant_id} ({len(history)}/{rate_limit_rpm} RPM)")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "tenant_id": tenant_id,
                    "limit_rpm": rate_limit_rpm,
                    "message": f"Rate limit of {rate_limit_rpm} requests per minute exceeded. Try again in {retry_after} seconds."
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rate_limit_rpm),
                    "X-RateLimit-Remaining": "0"
                }
            )

        history.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limit_rpm)
        response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit_rpm - len(history)))
        return response
