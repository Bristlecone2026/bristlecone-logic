import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as aioredis

from app.api.v1.router import api_router
from app.routers.llm import router as llm_router
from app.routers.billing import router as billing_router
from app.routers.health import router as health_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=100
    )
    logger.info("API lifespan: Redis connection pool established.")
    yield
    await app.state.redis.close()
    logger.info("API lifespan: Redis connection pool closed.")

app = FastAPI(
    title="Bristlecone Logic M2M API",
    description="Agentic Tooling & High-Throughput Micropayment Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Route registrations
app.include_router(api_router, prefix="/api/v1")
app.include_router(llm_router)
app.include_router(billing_router)
app.include_router(health_router)
