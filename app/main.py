import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

try:
    from app.api.v1.router import api_router
except ImportError:
    from app.api.v1.router import router as api_router

logger = logging.getLogger("bristlecone.api")

limiter = Limiter(key_func=get_remote_address)


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": f"Rate limit exceeded: {exc.detail}"},
        headers={
            "Retry-After": "60",
            "X-RateLimit-Limit": str(exc.detail),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "60",
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Bristlecone Logic API...")
    yield
    logger.info("Shutting down Bristlecone Logic API...")


API_V1_STR = "/api/v1"
PROJECT_NAME = "Bristlecone Logic API"

app = FastAPI(
    title=PROJECT_NAME,
    openapi_url=f"{API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)

cors_origins = os.getenv("BACKEND_CORS_ORIGINS", "")
if cors_origins:
    origins = [origin.strip("/") for origin in cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


app.include_router(api_router, prefix=API_V1_STR)
