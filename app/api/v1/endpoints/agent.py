import time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import verify_api_key
from app.services.billing import process_execution_billing
from app.metrics import LLM_TOKENS_TOTAL, LLM_BILLED_USD_TOTAL

router = APIRouter()

class AgentRunRequest(BaseModel):
    intent: str = Field(..., description="Prompt or intent for the autonomous worker")
    provider: str = Field(default="openai", description="Model provider (e.g. openai, internal)")
    model: str = Field(default="gpt-4o", description="Target model identifier")

@router.post("/run")
async def run_agent(
    payload: AgentRunRequest,
    tenant_context: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()
    tenant_id = tenant_context["tenant_id"]

    simulated_tokens = 350
    
    billing_result = await process_execution_billing(
        db=db,
        tenant_id=tenant_id,
        provider=payload.provider,
        model=payload.model,
        total_tokens=simulated_tokens
    )

    if not billing_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=billing_result["error"]
        )

    LLM_TOKENS_TOTAL.labels(provider=payload.provider, model=payload.model).inc(simulated_tokens)
    LLM_BILLED_USD_TOTAL.labels(provider=payload.provider, model=payload.model).inc(billing_result["billed_cost_usd"])

    latency_ms = int((time.time() - start_time) * 1000)

    return {
        "intent": payload.intent,
        "category": "STRUCTURED_TRANSFORM",
        "status": "PROCESSED",
        "worker_result": {
            "worker_status": "COMPLETED",
            "output": f"Successfully processed workload using {payload.model}.",
            "execution_metadata": {
                "total_tokens": simulated_tokens,
                "billed_cost_usd": billing_result["billed_cost_usd"],
                "provider": payload.provider,
                "model": payload.model,
                "latency_ms": latency_ms
            }
        },
        "telemetry": {
            "audit_id": f"aud_{int(time.time())}",
            "verified": True
        },
        "tenant_context": {
            "tenant_id": tenant_id,
            "tier": tenant_context.get("tier", "pro")
        }
    }
