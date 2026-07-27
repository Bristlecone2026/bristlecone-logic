from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.api.v1.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="Bristlecone Logic API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router)
