import os
import secrets
import hashlib
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.models.auth import Tenant, ApiKey

router = APIRouter(prefix="/api/v1/auth", tags=["Autonomous M2M Auth"])

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
INITIAL_FREE_CREDITS = 50

# On-chain Settlement Configuration
RECEIVER_ADDRESS = "0x1B4309CFdbCEee7618a7fBDc5b145691F9246D67"
USDC_BASE_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

class AgentRegisterRequest(BaseModel):
    agent_name: str = Field(..., min_length=2, max_length=64, description="Name or identifier of the autonomous agent.")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional agent metadata.")

class DepositInstructions(BaseModel):
    network: str = "Base (Coinbase L2)"
    asset: str = "USDC"
    contract_address: str = USDC_BASE_CONTRACT
    receiver_address: str = RECEIVER_ADDRESS
    deposit_memo_identifier: str = Field(..., description="Pass this Tenant ID or match your sender address.")
    minimum_deposit_usd: float = 1.00
    confirmation_time_avg: str = "~2-5 seconds"

class AgentRegisterResponse(BaseModel):
    status: str = "success"
    tenant_id: str
    agent_name: str
    api_key: str = Field(..., description="Copy this API key now. It cannot be retrieved again.")
    credit_balance_usd: float = 0.10  # 50 free credits valued at $0.002/ea
    credits_available: int = INITIAL_FREE_CREDITS
    deposit_instructions: DepositInstructions

@router.post("/agent-register", response_model=AgentRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_autonomous_agent(
    payload: AgentRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Autonomous registration endpoint for M2M AI agents.
    Instantly provisions a tenant in Postgres, creates an API key hash,
    and initializes Redis metering hashes for instant API execution.
    """
    tenant_id = uuid.uuid4()
    tenant_name = payload.agent_name.strip()

    # 1. Create Tenant in PostgreSQL
    new_tenant = Tenant(
        id=tenant_id,
        name=tenant_name
    )
    db.add(new_tenant)

    # 2. Generate Cryptographic API Key: bl_live_<32_random_bytes_hex>
    raw_secret = secrets.token_hex(24)
    raw_api_key = f"bl_live_{raw_secret}"
    key_prefix = raw_api_key[:10]
    key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()

    new_api_key = ApiKey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=f"{tenant_name}-default-key",
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True
    )
    db.add(new_api_key)

    await db.commit()

    # 3. Populate Redis Hash for instant gateway metering
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        key_data = {
            "tenant": tenant_name,
            "tenant_id": str(tenant_id),
            "credits": str(INITIAL_FREE_CREDITS),
            "active": "1"
        }
        # Set raw API key hash for verify_metering middleware
        await redis_client.hset(f"apikey:{raw_api_key}", mapping=key_data)
        # Set tenant balance tracking for on-chain deposit worker
        await redis_client.set(f"balance:{tenant_id}", "0.100000")
        await redis_client.aclose()
    except Exception:
        pass

    deposit_info = DepositInstructions(
        deposit_memo_identifier=str(tenant_id)
    )

    return AgentRegisterResponse(
        tenant_id=str(tenant_id),
        agent_name=tenant_name,
        api_key=raw_api_key,
        credit_balance_usd=0.10,
        credits_available=INITIAL_FREE_CREDITS,
        deposit_instructions=deposit_info
    )
