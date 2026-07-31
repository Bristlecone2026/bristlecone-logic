import hashlib
from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.auth import ApiKey

class TenantContext(BaseModel):
    tenant_id: str
    key_id: str
    is_active: bool = True

async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> TenantContext:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_api_key", "message": "X-API-Key header is required."}
        )

    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    api_key_record = result.scalars().first()

    if not api_key_record or not api_key_record.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_api_key", "message": "Provided X-API-Key is invalid or revoked."}
        )

    return TenantContext(
        tenant_id=str(api_key_record.tenant_id) if api_key_record.tenant_id else "load-test-tenant",
        key_id=str(api_key_record.id),
        is_active=api_key_record.is_active
    )
