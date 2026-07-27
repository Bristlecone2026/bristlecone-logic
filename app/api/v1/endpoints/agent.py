import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import get_current_user, get_db
from app.models.domain import SystemLog

logger = logging.getLogger("bristlecone.agent")
router = APIRouter(prefix="/agent", tags=["agent"])

# Define limiter for the router
limiter = Limiter(key_func=get_remote_address)

class AgentRunRequest(BaseModel):
    intent: str
    context: Optional[Dict[str, Any]] = None

@router.post("/run")
@limiter.limit("10/minute")
async def run_agent_workflow(
    request: Request,
    run_request: AgentRunRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Extract user & tenant metadata safely
    user_id = getattr(current_user, "id", None)
    email = getattr(current_user, "email", "unknown")
    full_name = getattr(current_user, "full_name", None)
    raw_org_id = getattr(current_user, "organization_id", None)
    org_id = raw_org_id if raw_org_id is not None else "org_default"

    tenant_ctx = {
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "organization_id": org_id
    }

    try:
        try:
            from app.layer3_orchestration.orchestrator import Layer3Orchestrator
        except ImportError:
            from src.orchestrator import Layer3Orchestrator

        context = run_request.context or {}
        context.update(tenant_ctx)

        orchestrator = Layer3Orchestrator()
        result = await orchestrator.process_intent(run_request.intent, context)
        
        result["tenant_context"] = tenant_ctx

        # Record successful execution telemetry to PostgreSQL
        log_payload = {
            "intent": run_request.intent,
            "tenant_context": tenant_ctx,
            "category": result.get("category"),
            "status": result.get("status"),
            "pipeline_stage": result.get("pipeline_stage"),
            "response_summary": result.get("worker_result")
        }
        
        audit_log = SystemLog(
            level="INFO",
            message=f"Agent workflow executed successfully for user_id={user_id}",
            payload=log_payload
        )
        db.add(audit_log)
        await db.commit()

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Agent execution failed: {error_msg}")

        # Record failed execution attempt to PostgreSQL for auditing
        log_payload = {
            "intent": run_request.intent,
            "tenant_context": tenant_ctx,
            "error": error_msg
        }
        audit_log = SystemLog(
            level="ERROR",
            message=f"Agent workflow execution failed for user_id={user_id}: {error_msg}",
            payload=log_payload
        )
        db.add(audit_log)
        await db.commit()

        raise HTTPException(status_code=500, detail=f"Agent execution failed: {error_msg}")
