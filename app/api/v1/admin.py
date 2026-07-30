import hashlib
import secrets
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

# --- Schemas ---

class CreateKeyRequest(BaseModel):
    name: str = Field(..., example="Production Integration Key")

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

# --- Endpoints ---

@router.post("/tenants/{tenant_id}/keys", response_model=KeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant_api_key(
    tenant_id: UUID,
    payload: CreateKeyRequest,
    db: AsyncSession = Depends(get_db)
):
    # Verify tenant exists
    tenant_check = await db.execute(
        text("SELECT id FROM tenants WHERE id = :tid"),
        {"tid": str(tenant_id)}
    )
    if not tenant_check.scalars().first():
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Generate secure bcl_ key and SHA-256 hash
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
