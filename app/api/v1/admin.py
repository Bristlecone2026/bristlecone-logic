import hashlib
import secrets
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

from app.core.security import verify_admin_key
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_key)])

# --- Schemas ---

class CreateKeyRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Production Integration Key"})

class KeyCreatedResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    key_prefix: str
    api_key: str  # Plaintext key returned ONCE
    is_active: bool
    created_at: str

class KeyListItem(BaseModel):
    id: str
    tenant_id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: str

class TopUpCreditRequest(BaseModel):
    amount_usd: Decimal = Field(..., gt=0, json_schema_extra={"example": 50.00}, description="Amount in USD to add to balance")
    reason: Optional[str] = Field(None, json_schema_extra={"example": "Manual administrative allocation"})

class CreditBalanceResponse(BaseModel):
    tenant_id: str
    previous_balance_usd: float
    added_amount_usd: float
    new_balance_usd: float

# --- Endpoints ---

@router.post("/tenants/{tenant_id}/keys", response_model=KeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant_api_key(
    tenant_id: UUID,
    payload: CreateKeyRequest,
    db: AsyncSession = Depends(get_db)
):
    tenant_check = await db.execute(
        text("SELECT id FROM tenants WHERE id = :tid"),
        {"tid": str(tenant_id)}
    )
    if not tenant_check.scalars().first():
        raise HTTPException(status_code=404, detail="Tenant not found")

    raw_secret = secrets.token_hex(16)
    raw_key = f"bcl_{raw_secret}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = raw_key[:12]

    query = text("""
        INSERT INTO api_keys (tenant_id, name, key_hash, key_prefix, is_active)
        VALUES (:tenant_id, :name, :key_hash, :key_prefix, true)
        RETURNING id, tenant_id, name, key_prefix, is_active, created_at
    """)

    result = await db.execute(query, {
        "tenant_id": str(tenant_id),
        "name": payload.name,
        "key_hash": key_hash,
        "key_prefix": key_prefix
    })
    row = result.mappings().first()
    await db.commit()

    return KeyCreatedResponse(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        name=row["name"],
        key_prefix=row["key_prefix"],
        api_key=raw_key,
        is_active=row["is_active"],
        created_at=row["created_at"].isoformat()
    )


@router.get("/tenants/{tenant_id}/keys", response_model=List[KeyListItem])
async def list_tenant_api_keys(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT id, tenant_id, name, key_prefix, is_active, last_used_at, created_at
        FROM api_keys
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
    """)
    result = await db.execute(query, {"tenant_id": str(tenant_id)})
    rows = result.mappings().all()

    return [
        KeyListItem(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            name=row["name"],
            key_prefix=row["key_prefix"],
            is_active=row["is_active"],
            last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
            created_at=row["created_at"].isoformat()
        )
        for row in rows
    ]


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        UPDATE api_keys 
        SET is_active = false 
        WHERE id = :key_id
        RETURNING id, name, key_prefix, is_active
    """)
    result = await db.execute(query, {"key_id": str(key_id)})
    row = result.mappings().first()
    
    if not row:
        raise HTTPException(status_code=404, detail="API Key not found")

    await db.commit()
    return {
        "status": "revoked",
        "key_id": str(row["id"]),
        "name": row["name"],
        "key_prefix": row["key_prefix"],
        "is_active": row["is_active"]
    }


@router.post("/tenants/{tenant_id}/credits", response_model=CreditBalanceResponse)
async def top_up_tenant_credits(
    tenant_id: UUID,
    payload: TopUpCreditRequest,
    db: AsyncSession = Depends(get_db)
):
    tenant_check = await db.execute(
        text("SELECT id, credit_balance_usd FROM tenants WHERE id = :tid"),
        {"tid": str(tenant_id)}
    )
    row = tenant_check.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")

    previous_balance = float(row["credit_balance_usd"])
    added_amount = float(payload.amount_usd)

    update_query = text("""
        UPDATE tenants
        SET credit_balance_usd = credit_balance_usd + :amount
        WHERE id = :tid
        RETURNING credit_balance_usd
    """)
    result = await db.execute(update_query, {
        "amount": added_amount,
        "tid": str(tenant_id)
    })
    updated_row = result.mappings().first()
    await db.commit()

    return CreditBalanceResponse(
        tenant_id=str(tenant_id),
        previous_balance_usd=previous_balance,
        added_amount_usd=added_amount,
        new_balance_usd=float(updated_row["credit_balance_usd"])
    )

# --- Webhook & Notification Admin Endpoints ---

class WebhookConfigRequest(BaseModel):
    webhook_url: str = Field(..., json_schema_extra={"example": "https://hooks.example.com/alerts"})

@router.post("/tenants/{tenant_id}/webhook")
async def configure_tenant_webhook(
    tenant_id: UUID,
    payload: WebhookConfigRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.services.notifications import set_tenant_webhook
    await set_tenant_webhook(str(tenant_id), payload.webhook_url, db)
    return {"status": "configured", "tenant_id": str(tenant_id), "webhook_url": payload.webhook_url}

@router.post("/sweep-low-balances")
async def trigger_low_balance_sweep(
    db: AsyncSession = Depends(get_db)
):
    from app.services.notifications import scan_all_tenants_low_balance
    tenants_flagged = await scan_all_tenants_low_balance(db)
    return {"status": "completed", "tenants_checked_below_threshold": tenants_flagged}
