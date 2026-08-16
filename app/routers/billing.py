import json
import uuid
from decimal import Decimal
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, verify_api_key
from app.database import get_db

logger = logging.getLogger("api.billing")
router = APIRouter(prefix="/api/v1/billing", tags=["Billing & Deposits"])

class DepositSubmitRequest(BaseModel):
    tx_hash: str = Field(..., description="Base L2 transaction hash for USDC transfer")
    amount_usdc: Decimal = Field(..., description="Amount of USDC transferred")
    from_address: str = Field(default="0x0000000000000000000000000000000000000000")

@router.post("/deposit")
async def submit_deposit(
    payload: DepositSubmitRequest,
    request: Request,
    tenant: TenantContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    redis_conn = request.app.state.redis
    tenant_id = tenant.tenant_id

    # 1. Push directly to deposit queue for asynchronous atomic processing
    deposit_event = {
        "tenant_id": tenant_id,
        "tx_hash": payload.tx_hash.lower(),
        "block_number": 19482000,
        "from_address": payload.from_address.lower(),
        "amount_usdc": str(payload.amount_usdc)
    }
    await redis_conn.rpush("base_deposit_queue", json.dumps(deposit_event))

    return {
        "status": "queued",
        "message": f"Deposit of {payload.amount_usdc} USDC submitted for Base L2 verification and crediting.",
        "tx_hash": payload.tx_hash,
        "tenant_id": tenant_id
    }

@router.get("/balance")
async def get_balance(
    request: Request,
    tenant: TenantContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    redis_conn = request.app.state.redis
    balance_key = f"balance:{tenant.tenant_id}"
    redis_bal = await redis_conn.get(balance_key)
    
    res = await db.execute(
        text("SELECT credit_balance_usd, low_balance_threshold_usd FROM tenants WHERE id = :tid"),
        {"tid": uuid.UUID(tenant.tenant_id)}
    )
    row = res.first()
    db_bal = float(row[0]) if row else 0.0
    threshold = float(row[1]) if row else 1.0

    return {
        "tenant_id": tenant.tenant_id,
        "cached_redis_balance_usd": float(redis_bal) if redis_bal else db_bal,
        "persisted_db_balance_usd": db_bal,
        "low_balance_threshold_usd": threshold,
        "deposit_network": "Base L2",
        "accepted_token": "USDC",
        "receiver_address": "0x1B4309CFdbCEee7618a7fBDc5b145691F9246D67"
    }
