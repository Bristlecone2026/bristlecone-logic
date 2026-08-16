from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from pydantic import BaseModel, Field
import secrets
import hashlib
import uuid

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Provisioning"])

class TenantCreateRequest(BaseModel):
    name: str = Field(..., description="Tenant organization or individual name")
    webhook_url: str | None = Field(None, description="Webhook URL for low-balance or event alerts")
    low_balance_threshold_usd: float = Field(1.0, description="USD threshold for low-balance alerts")

class APIKeyCreateRequest(BaseModel):
    name: str = Field("Default Key", description="Friendly name for the API key")

@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreateRequest):
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                INSERT INTO tenants (name, webhook_url, low_balance_threshold_usd)
                VALUES (:name, :webhook_url, :threshold)
                RETURNING id, name, xrpl_destination_tag, credit_balance_usd, created_at
            """),
            {
                "name": payload.name,
                "webhook_url": payload.webhook_url,
                "threshold": payload.low_balance_threshold_usd
            }
        )
        row = result.first()
        await session.commit()
        return {
            "status": "success",
            "tenant": {
                "id": str(row[0]),
                "name": row[1],
                "xrpl_destination_tag": row[2],
                "credit_balance_usd": float(row[3]),
                "created_at": row[4]
            }
        }

@router.post("/tenants/{tenant_id}/api-keys", status_code=status.HTTP_201_CREATED)
async def generate_api_key(tenant_id: str, payload: APIKeyCreateRequest):
    from app.database import AsyncSessionLocal
    try:
        t_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format.")

    raw_key = f"bc_live_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with AsyncSessionLocal() as session:
        t_res = await session.execute(text("SELECT id FROM tenants WHERE id = :tid"), {"tid": t_uuid})
        if not t_res.first():
            raise HTTPException(status_code=404, detail="Tenant not found.")

        res = await session.execute(
            text("""
                INSERT INTO api_keys (tenant_id, key_hash, name)
                VALUES (:tenant_id, :key_hash, :name)
                RETURNING id, created_at
            """),
            {
                "tenant_id": t_uuid,
                "key_hash": key_hash,
                "name": payload.name
            }
        )
        row = res.first()
        await session.commit()

        return {
            "status": "success",
            "api_key_id": str(row[0]),
            "raw_api_key": raw_key,
            "note": "Store this key securely. It cannot be retrieved again."
        }
