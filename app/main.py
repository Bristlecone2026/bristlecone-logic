from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.layer1_schemas.base import SystemHealthResponse
from app.layer2_microservices.router import router as task_router
from app.layer3_orchestration.graph import AgentGraphOrchestrator
from app.layer3_orchestration.state import AgentState
from app.core.security import verify_api_key
from app.core.rate_limiter import limiter
from app.core.payload_limiter import LimitPayloadSizeMiddleware

load_dotenv()

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

# Security Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)
app.add_middleware(LimitPayloadSizeMiddleware, max_upload_size=1_048_576)

# Router Mounting
app.include_router(
    task_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(limiter)]
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
