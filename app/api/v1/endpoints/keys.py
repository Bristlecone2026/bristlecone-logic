import secrets
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import verify_api_key, TenantContext
from app.models.auth import ApiKey

router = APIRouter()

class CreateKeyRequest(BaseModel):
    name: Optional[str] = "Standard API Key"

class KeyResponse(BaseModel):
    id: str
    name: Optional[str]
    key_prefix: Optional[str]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]

class CreateKeyResponse(BaseModel):
    id: str
    name: Optional[str]
    key_prefix: str
    key: str  # Only exposed once upon generation
    created_at: datetime

@router.get("", response_model=dict)
async def list_keys(
    tenant: TenantContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """List all active API keys for the calling tenant."""
    tenant_uuid = uuid.UUID(tenant.tenant_id)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.tenant_id == tenant_uuid,
            ApiKey.is_active == True
        )
    )
    keys = result.scalars().all()
    
    key_data = [
        KeyResponse(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            created_at=k.created_at,
            last_used_at=k.last_used_at
        ).model_dump(mode="json")
        for k in keys
    ]

    return {
        "status": "success",
        "tenant_id": tenant.tenant_id,
        "authenticated_key_id": tenant.key_id,
        "data": key_data
    }

@router.post("", response_model=CreateKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: CreateKeyRequest,
    tenant: TenantContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Generate and store a new SHA-256 hashed API key for the tenant."""
    raw_key_secret = f"bc_live_{secrets.token_hex(16)}"
    key_prefix = raw_key_secret[:7]
    key_hash = hashlib.sha256(raw_key_secret.encode()).hexdigest()

    tenant_uuid = uuid.UUID(tenant.tenant_id)
    new_api_key = ApiKey(
        id=uuid.uuid4(),
        tenant_id=tenant_uuid,
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )

    db.add(new_api_key)
    await db.commit()
    await db.refresh(new_api_key)

    return CreateKeyResponse(
        id=str(new_api_key.id),
        name=new_api_key.name,
        key_prefix=new_api_key.key_prefix,
        key=raw_key_secret,
        created_at=new_api_key.created_at
    )

@router.delete("/{key_id}")
async def revoke_key(
    key_id: str,
    tenant: TenantContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Revoke an existing API key by setting is_active to False."""
    try:
        target_uuid = uuid.UUID(key_id)
        tenant_uuid = uuid.UUID(tenant.tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_id", "message": "Provided key_id is not a valid UUID."}
        )

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == target_uuid,
            ApiKey.tenant_id == tenant_uuid
        )
    )
    api_key_record = result.scalars().first()

    if not api_key_record or not api_key_record.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "key_not_found", "message": "API key not found or already revoked."}
        )

    api_key_record.is_active = False
    api_key_record.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "success",
        "message": f"API key {key_id} successfully revoked.",
        "key_id": key_id
    }
