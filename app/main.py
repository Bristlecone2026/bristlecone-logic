from app.middleware.rate_limiter import RateLimitMiddleware
import time
from fastapi import FastAPI, Request
from app.api.v1.router import api_router
from app.api.v1 import admin
from app.metrics import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS, metrics_response

app = FastAPI(title="Bristlecone v2.0 API")
app.add_middleware(RateLimitMiddleware)

@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    path = request.url.path
    
    HTTP_REQUESTS_TOTAL.labels(
        method=request.method,
        endpoint=path,
        status_code=str(response.status_code)
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=request.method,
        endpoint=path
    ).observe(duration)

    return response

app.include_router(api_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/v1/metrics")
async def get_metrics():
    return metrics_response()
