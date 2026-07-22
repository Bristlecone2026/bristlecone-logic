import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends
from app.layer1_schemas.base import SystemHealthResponse
from app.layer2_microservices.router import router as task_router
from app.core.security import verify_api_key

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

# Mount Layer 2 router behind the perimeter security gate
app.include_router(
    task_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)]
)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()

@app.get("/")
def read_root():
    return {
        "system": "Bristlecone Logic API",
        "status": "online",
        "endpoints": ["/health", "/docs"]
    }

# Dedicated test endpoint for Priority 1 verification
@app.get("/api/v1/protected-task", dependencies=[Depends(verify_api_key)])
async def protected_task():
    return {"status": "authenticated", "access": "granted"}
from fastapi import FastAPI, Depends
from app.layer1_schemas.base import SystemHealthResponse
from app.layer2_microservices.router import router as task_router
from app.core.security import verify_api_key
from app.core.rate_limiter import limiter

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

# Mount Layer 2 router behind both API Key Auth AND Rate Limiting
app.include_router(
    task_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(limiter)]
)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()

@app.get("/")
def read_root():
    return {
        "system": "Bristlecone Logic API",
        "status": "online",
        "endpoints": ["/health", "/docs"]
    }

# Dedicated test endpoint for verification
@app.get("/api/v1/protected-task", dependencies=[Depends(verify_api_key), Depends(limiter)])
async def protected_task():
    return {"status": "authenticated", "access": "granted"}
from fastapi import FastAPI, Depends
from app.layer1_schemas.base import SystemHealthResponse
from app.layer2_microservices.router import router as task_router
from app.core.security import verify_api_key
from app.core.rate_limiter import limiter
from app.core.payload_limiter import LimitPayloadSizeMiddleware

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

# Register global payload size enforcement (1 MB cap)
app.add_middleware(LimitPayloadSizeMiddleware, max_upload_size=1_048_576)

# Mount Layer 2 router behind API Key Auth AND Rate Limiting
app.include_router(
    task_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(limiter)]
)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()

@app.get("/")
def read_root():
    return {
        "system": "Bristlecone Logic API",
        "status": "online",
        "endpoints": ["/health", "/docs"]
    }

@app.get("/api/v1/protected-task", dependencies=[Depends(verify_api_key), Depends(limiter)])
async def protected_task():
    return {"status": "authenticated", "access": "granted"}
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.layer1_schemas.base import SystemHealthResponse
from app.layer2_microservices.router import router as task_router
from app.core.security import verify_api_key
from app.core.rate_limiter import limiter
from app.core.payload_limiter import LimitPayloadSizeMiddleware

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

# Priority 4: Host Header Validation (Rejects spoofed or external host headers)
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["127.0.0.1", "localhost"]
)

# Priority 4: Strict Cross-Origin Isolation (Restricts unauthorized origin domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
)

# Priority 3: Payload Size Enforcement (1 MB cap)
app.add_middleware(LimitPayloadSizeMiddleware, max_upload_size=1_048_576)

# Mount Layer 2 router behind API Key Auth AND Rate Limiting
app.include_router(
    task_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(limiter)]
)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()

@app.get("/")
def read_root():
    return {
        "system": "Bristlecone Logic API",
        "status": "online",
        "endpoints": ["/health", "/docs"]
    }

@app.get("/api/v1/protected-task", dependencies=[Depends(verify_api_key), Depends(limiter)])
async def protected_task():
    return {"status": "authenticated", "access": "granted"}
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

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["127.0.0.1", "localhost"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
)

app.add_middleware(LimitPayloadSizeMiddleware, max_upload_size=1_048_576)

app.include_router(
    task_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(limiter)]
)

@app.post("/api/v1/agent/run", response_model=AgentState, dependencies=[Depends(verify_api_key), Depends(limiter)])
async def run_agent_workflow(goal: str):
    return await AgentGraphOrchestrator.run(user_goal=goal)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()
