from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.api.deps import get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])

class AgentRunRequest(BaseModel):
    intent: str
    context: Optional[Dict[str, Any]] = None

@router.post("/run")
async def run_agent_workflow(
    request: AgentRunRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    try:
        try:
            from app.layer3_orchestration.orchestrator import Layer3Orchestrator
        except ImportError:
            from src.orchestrator import Layer3Orchestrator

        orchestrator = Layer3Orchestrator()
        result = await orchestrator.process_intent(request.intent, request.context or {})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
