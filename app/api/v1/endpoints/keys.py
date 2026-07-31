import hashlib
import secrets
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.models import ApiKey
from app.api.v1.endpoints.agent import get_tenant_context, TenantContext

router = APIRouter()


# --- Pydantic Schemas ---

class ApiKeyCreateRequest(BaseModel):
    name: str = "default_key"


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    raw_key: str  # Displayed ONLY upon creation
    created_at: datetime
    is_active: bool


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    is_active: bool
    last_used_at: Optional[datetime] = None


# --- Helper Functions ---

def generate_raw_api_key() -> str:
    """Generates a secure raw key prefixed with 'bl_' (Bristlecone Logic)."""
    return f"bl_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """Computes SHA-256 hash of the raw API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# --- Endpoints ---

@router.post("/", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Generates a new API key for the authenticated tenant."""
    raw_key = generate_raw_api_key()
    hashed_key = hash_api_key(raw_key)

    new_key = ApiKey(
        id=uuid.uuid4(),
        tenant_id=tenant_context.tenant_id,
        hashed_key=hashed_key,
        name=payload.name,
        is_active=True,
    )

    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return ApiKeyCreateResponse(
        id=new_key.id,
        name=new_key.name,
        raw_key=raw_key,
        created_at=new_key.created_at,
        is_active=new_key.is_active,
    )


@router.get("/", response_model=List[ApiKeyResponse])
async def list_api_keys(
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Lists key metadata associated with the authenticated tenant."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.tenant_id == tenant_context.tenant_id)
    )
    keys = result.scalars().all()

    return [
        ApiKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=f"bl_...{key.hashed_key[:6]}",
            created_at=key.created_at,
            is_active=key.is_active,
            last_used_at=getattr(key, "last_used_at", None),
        )
        for key in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Revokes (deactivates) an API key for the authenticated tenant."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.tenant_id == tenant_context.tenant_id,
        )
    )
    key = result.scalars().first()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key not found or does not belong to tenant.",
        )

    key.is_active = False
    await db.commit()
    return None
