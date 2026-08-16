import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request
import redis.asyncio as aioredis

from app.api.v1.router import api_router

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
    yield
    await app.state.redis.close()

app = FastAPI(
    title="Bristlecone Logic M2M API",
    description="Agentic Tooling & High-Throughput Micropayment Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Mount core v1 router
app.include_router(api_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "bristlecone_api"}
