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
    current_user: Any = Depends(get_current_user)
):
    try:
        try:
            from app.layer3_orchestration.orchestrator import Layer3Orchestrator
        except ImportError:
            from src.orchestrator import Layer3Orchestrator

        # Extract attributes safely from the User ORM/Pydantic instance
        user_id = getattr(current_user, "id", None)
        username = getattr(current_user, "username", "unknown")
        org_id = getattr(current_user, "organization_id", "default_org")

        # Enrich context with authenticated tenant metadata
        context = request.context or {}
        context["user_id"] = user_id
        context["username"] = username
        context["organization_id"] = org_id

        orchestrator = Layer3Orchestrator()
        result = await orchestrator.process_intent(request.intent, context)
        
        # Attach tenant verification to API response
        result["tenant_context"] = {
            "user_id": user_id,
            "username": username,
            "organization_id": org_id
        }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
