import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import get_current_user, get_db
from app.models.domain import SystemLog

logger = logging.getLogger("bristlecone.agent")
router = APIRouter(prefix="/agent", tags=["agent"])

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
    start_time = time.time()

    if isinstance(current_user, dict):
        auth_type = current_user.get("auth_type", "jwt")
        tenant_id = current_user.get("tenant_id")
        key_id = current_user.get("key_id")
        user_id = current_user.get("user_id")
        email = current_user.get("email", "unknown")
        full_name = current_user.get("full_name")
        org_id = current_user.get("organization_id", "org_default")
    else:
        auth_type = "jwt"
        tenant_id = getattr(current_user, "tenant_id", None)
        key_id = None
        user_id = getattr(current_user, "id", None)
        email = getattr(current_user, "email", "unknown")
        full_name = getattr(current_user, "full_name", None)
        org_id = getattr(current_user, "organization_id", "org_default")

    tenant_ctx = {
        "auth_type": auth_type,
        "tenant_id": tenant_id,
        "key_id": key_id,
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

        latency_ms = int((time.time() - start_time) * 1000)

        worker_res = result.get("worker_result", {})
        exec_meta = worker_res.get("execution_metadata", {})
        est_tokens = exec_meta.get("estimated_tokens", 100)

        input_tokens = int(est_tokens * 0.4)
        output_tokens = int(est_tokens * 0.6)
        total_tokens = input_tokens + output_tokens

        raw_cost = round(total_tokens * 0.0000015, 6)
        billed_cost = round(total_tokens * 0.0000020, 6)

        if tenant_id:
            ledger_stmt = text("""
                INSERT INTO llm_usage_ledger (
                    tenant_id, api_key_id, model_requested, provider, is_byok,
                    input_tokens, output_tokens, total_tokens,
                    raw_cost_usd, billed_cost_usd, latency_ms, status_code
                ) VALUES (
                    :tenant_id, :api_key_id, :model, :provider, :is_byok,
                    :in_tok, :out_tok, :tot_tok,
                    :raw_cost, :billed_cost, :latency, 200
                )
            """)
            await db.execute(ledger_stmt, {
                "tenant_id": tenant_id,
                "api_key_id": key_id,
                "model": "bristlecone-orchestrator-v1",
                "provider": "internal",
                "is_byok": False,
                "in_tok": input_tokens,
                "out_tok": output_tokens,
                "tot_tok": total_tokens,
                "raw_cost": raw_cost,
                "billed_cost": billed_cost,
                "latency": latency_ms
            })

            deduct_stmt = text("""
                UPDATE tenants 
                SET credit_balance_usd = credit_balance_usd - :cost 
                WHERE id = :tenant_id
            """)
            await db.execute(deduct_stmt, {
                "cost": billed_cost,
                "tenant_id": tenant_id
            })

        log_payload = {
            "intent": run_request.intent,
            "tenant_context": tenant_ctx,
            "category": result.get("category"),
            "status": result.get("status"),
            "pipeline_stage": result.get("pipeline_stage"),
            "response_summary": worker_res
        }
        
        audit_log = SystemLog(
            level="INFO",
            message=f"Agent workflow executed successfully for tenant_id={tenant_id or 'N/A'}",
            payload=log_payload
        )
        db.add(audit_log)
        await db.commit()

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Agent execution failed: {error_msg}")
        latency_ms = int((time.time() - start_time) * 1000)

        if tenant_id:
            try:
                ledger_stmt = text("""
                    INSERT INTO llm_usage_ledger (
                        tenant_id, api_key_id, model_requested, provider, is_byok,
                        input_tokens, output_tokens, total_tokens,
                        raw_cost_usd, billed_cost_usd, latency_ms, status_code
                    ) VALUES (
                        :tenant_id, :api_key_id, :model, :provider, :is_byok,
                        0, 0, 0, 0.0, 0.0, :latency, 500
                    )
                """)
                await db.execute(ledger_stmt, {
                    "tenant_id": tenant_id,
                    "api_key_id": key_id,
                    "model": "bristlecone-orchestrator-v1",
                    "provider": "internal",
                    "is_byok": False,
                    "latency": latency_ms
                })
                await db.commit()
            except Exception as db_err:
                logger.error(f"Failed to record error in usage ledger: {db_err}")

        log_payload = {
            "intent": run_request.intent,
            "tenant_context": tenant_ctx,
            "error": error_msg
        }
        audit_log = SystemLog(
            level="ERROR",
            message=f"Agent workflow execution failed for tenant_id={tenant_id or 'N/A'}: {error_msg}",
            payload=log_payload
        )
        db.add(audit_log)
        await db.commit()

        raise HTTPException(status_code=500, detail=f"Agent execution failed: {error_msg}")
