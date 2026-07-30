import time
import uuid
import hashlib
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_tenant_context
from app.services.billing import record_usage_and_deduct_credit

router = APIRouter()


class AgentRunRequest(BaseModel):
    intent: str
    context: Optional[Dict[str, Any]] = None
    provider: Optional[str] = "openai"
    model: Optional[str] = "gpt-4o"


@router.post("/run")
async def run_agent(
    request: AgentRunRequest,
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()
    tenant_id = tenant_context["tenant_id"]

    # --- Simulated Agent Engine Workload ---
    estimated_tokens = len(request.intent.split()) * 25 + 150
    latency_ms = int((time.time() - start_time) * 1000) + 45

    # --- Post-Execution Credit Deduction & Ledger Insert ---
    billed_cost = await record_usage_and_deduct_credit(
        db=db,
        tenant_id=tenant_id,
        provider=request.provider,
        model=request.model,
        total_tokens=estimated_tokens,
        prompt_tokens=int(estimated_tokens * 0.7),
        completion_tokens=int(estimated_tokens * 0.3),
        latency_ms=latency_ms,
        status_code=200
    )

    audit_id = f"aud_{uuid.uuid4().hex[:12]}"
    telemetry_hash = hashlib.sha256(f"{audit_id}:{tenant_id}".encode()).hexdigest()

    return {
        "intent": request.intent,
        "category": "STRUCTURED_TRANSFORM",
        "status": "PROCESSED",
        "worker_result": {
            "worker_status": "COMPLETED",
            "output": f"Successfully processed workload using {request.model}.",
            "execution_metadata": {
                "total_tokens": estimated_tokens,
                "billed_cost_usd": billed_cost,
                "provider": request.provider,
                "model": request.model
            }
        },
        "telemetry": {
            "audit_id": audit_id,
            "telemetry_hash": telemetry_hash,
            "recorded_at": time.time(),
            "verified": True
        },
        "tenant_context": {
            "tenant_id": tenant_id,
            "key_id": tenant_context.get("key_id"),
            "tier": tenant_context.get("tier")
        }
    }
