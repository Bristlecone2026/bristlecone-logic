import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from app.routers import health, billing, llm, admin, tools
from app.middleware.m2m_payment import M2MPaymentMiddleware

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize shared Redis connection pool on app.state
    app.state.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield
    await app.state.redis.aclose()

app = FastAPI(
    title="Bristlecone Logic M2M Gateway",
    description="Autonomous Agent Settlement & High-Frequency Developer Tool Engine",
    version="1.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Autonomous M2M 402 Handshake Middleware
app.add_middleware(M2MPaymentMiddleware)

# API Routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing"])
app.include_router(llm.router, tags=["LLM Gateway"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(tools.router)

@app.get("/")
async def root():
    return {
        "service": "Bristlecone Logic Gateway",
        "settlement_rails": ["XRPL", "Base L2"],
        "openapi_spec": "/openapi.json",
        "status": "operational"
    }
