from fastapi import FastAPI
from app.layer1_schemas.base import SystemHealthResponse
from app.layer2_microservices.router import router as task_router

app = FastAPI(title="Bristlecone Logic Core Engine", version="0.1.0")

app.include_router(task_router)

@app.get("/health", response_model=SystemHealthResponse)
async def health_check():
    return SystemHealthResponse()
