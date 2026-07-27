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

        user_id = getattr(current_user, "id", None)
        email = getattr(current_user, "email", "unknown")
        full_name = getattr(current_user, "full_name", None)
        raw_org_id = getattr(current_user, "organization_id", None)
        org_id = raw_org_id if raw_org_id is not None else "org_default"

        context = request.context or {}
        context["user_id"] = user_id
        context["email"] = email
        context["full_name"] = full_name
        context["organization_id"] = org_id

        orchestrator = Layer3Orchestrator()
        result = await orchestrator.process_intent(request.intent, context)
        
        result["tenant_context"] = {
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "organization_id": org_id
        }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
