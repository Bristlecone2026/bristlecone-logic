import logging
from fastapi import FastAPI, HTTPException
from app.layer5_api.schemas import TaskRequest, TaskResponse, HealthResponse
from app.layer2_agent.agent_engine import AgentEngine

logger = logging.getLogger("bristlecone.layer5")

app = FastAPI(
    title="Bristlecone Logic - Zero Trust Production API",
    description="Layer 5 REST API gateway wrapping Erasmus and Zero Trust security controls.",
    version="1.0.0"
)

# Initialize Agent Engine (Erasmus)
agent_engine = AgentEngine()

@app.get("/health", response_model=HealthResponse)
def health_check():
    """System health endpoint."""
    return HealthResponse(
        status="ONLINE",
        system="Bristlecone Logic Core",
        agent=agent_engine.agent_name
    )

@app.post("/api/v1/task", response_model=TaskResponse)
def process_task(task: TaskRequest):
    """
    Primary API gateway route.
    Dispatches incoming request through Erasmus, Layer 3 gating, and Layer 4 signing.
    """
    try:
        result = agent_engine.execute_task(task.user_request)
        return TaskResponse(**result)
    except Exception as e:
        logger.error(f"API processing error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal processing error")
