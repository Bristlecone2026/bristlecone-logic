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

       HEAD
app.include_router(api_router)

app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["auth"]
)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()

@app.get("/")
async def root():
    return {
        "system": "Bristlecone Logic API",
        "status": "online",
        "endpoints": ["/health", "/docs"]
    }

@app.get("/api/v1/protected-task", dependencies=[Depends(verify_api_key), Depends(limiter)])
async def protected_task():
    return {"status": "authenticated", "access": "granted"}

@app.post("/api/v1/agent/run", response_model=AgentState, dependencies=[Depends(verify_api_key), Depends(limiter)])
async def run_agent_workflow(goal: str):
    return await AgentGraphOrchestrator.run(user_goal=goal)
        a61cf4b (fix: standardize api router prefixes to /api/v1)
