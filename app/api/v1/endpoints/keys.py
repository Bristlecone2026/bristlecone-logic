import secrets
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_tenant_context

router = APIRouter()

def generate_api_key() -> str:
    return f"bcl_{secrets.token_hex(16)}"

class CreateKeyRequest(BaseModel):
    name: str = Field(default="default_key", description="Label for the API key")

class RevokeKeyRequest(BaseModel):
    key_id: str = Field(..., description="ID of the API key to revoke")

async def ensure_schema(db: AsyncSession):
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(255) NOT NULL,
            name VARCHAR(100) NOT NULL,
            key_hash VARCHAR(255) NOT NULL UNIQUE,
            key_prefix VARCHAR(50) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            revoked_at TIMESTAMP WITH TIME ZONE NULL
        )
    """))
    # Migration fallbacks for pre-existing tables
    await db.execute(text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_prefix VARCHAR(50);"))
    await db.execute(text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
    await db.execute(text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP WITH TIME ZONE NULL;"))
    await db.commit()

@router.post("/generate")
async def create_api_key(
    payload: CreateKeyRequest,
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    await ensure_schema(db)
    tenant_id = tenant_context["tenant_id"]
    raw_key = generate_api_key()
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8] + "..."

    query = text("""
        INSERT INTO api_keys (tenant_id, name, key_hash, key_prefix)
        VALUES (:tenant_id, :name, :key_hash, :key_prefix)
        RETURNING id, created_at
    """)
    result = await db.execute(query, {
        "tenant_id": tenant_id,
        "name": payload.name,
        "key_hash": key_hash,
        "key_prefix": key_prefix
    })
    row = result.fetchone()
    await db.commit()

    return {
        "key_id": str(row.id),
        "name": payload.name,
        "api_key": raw_key,
        "key_prefix": key_prefix,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "warning": "Store this key securely. It will not be displayed again."
    }

@router.get("")
async def list_api_keys(
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    await ensure_schema(db)
    tenant_id = tenant_context["tenant_id"]

    query = text("""
        SELECT id, name, COALESCE(key_prefix, '') as key_prefix, COALESCE(is_active, TRUE) as is_active, created_at, revoked_at
        FROM api_keys
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
    """)
    result = await db.execute(query, {"tenant_id": tenant_id})
    rows = result.fetchall()

    keys = [
        {
            "key_id": str(r.id),
            "name": r.name,
            "key_prefix": r.key_prefix,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None
        }
        for r in rows
    ]

    return {"keys": keys}

@router.post("/rotate")
async def rotate_api_key(
    payload: CreateKeyRequest,
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    await ensure_schema(db)
    tenant_id = tenant_context["tenant_id"]

    # Revoke all current active keys
    revoke_query = text("""
        UPDATE api_keys
        SET is_active = FALSE, revoked_at = CURRENT_TIMESTAMP
        WHERE tenant_id = :tenant_id AND (is_active = TRUE OR is_active IS NULL)
    """)
    await db.execute(revoke_query, {"tenant_id": tenant_id})

    # Issue new key
    raw_key = generate_api_key()
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8] + "..."

    insert_query = text("""
        INSERT INTO api_keys (tenant_id, name, key_hash, key_prefix)
        VALUES (:tenant_id, :name, :key_hash, :key_prefix)
        RETURNING id, created_at
    """)
    result = await db.execute(insert_query, {
        "tenant_id": tenant_id,
        "name": payload.name,
        "key_hash": key_hash,
        "key_prefix": key_prefix
    })
    row = result.fetchone()
    await db.commit()

    return {
        "status": "ROTATED",
        "key_id": str(row.id),
        "name": payload.name,
        "api_key": raw_key,
        "key_prefix": key_prefix,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "warning": "All prior active API keys for this tenant have been revoked."
    }

@router.post("/revoke")
async def revoke_api_key(
    payload: RevokeKeyRequest,
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    await ensure_schema(db)
    tenant_id = tenant_context["tenant_id"]

    query = text("""
        UPDATE api_keys
        SET is_active = FALSE, revoked_at = CURRENT_TIMESTAMP
        WHERE id::text = :key_id AND tenant_id = :tenant_id AND (is_active = TRUE OR is_active IS NULL)
        RETURNING id
    """)
    result = await db.execute(query, {"key_id": payload.key_id, "tenant_id": tenant_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active API key not found or already revoked."
        )

    await db.commit()

    return {
        "status": "REVOKED",
        "key_id": str(row.id)
    }
