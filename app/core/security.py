import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Header, HTTPException, Depends, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.auth import ApiKey, UsageLog

class TenantContext(BaseModel):
    tenant_id: str
    key_id: str

async def verify_api_key(
    request: Request,
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
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True
        )
    )
    api_key_record = result.scalars().first()

    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_api_key", "message": "Provided X-API-Key is invalid or revoked."}
        )

    # Update key usage timestamp and persist audit record
    now = datetime.now(timezone.utc)
    api_key_record.last_used_at = now

    usage_entry = UsageLog(
        id=uuid.uuid4(),
        tenant_id=api_key_record.tenant_id,
        endpoint=request.url.path,
        timestamp=now
    )
    db.add(usage_entry)
    await db.commit()

    return TenantContext(
        tenant_id=str(api_key_record.tenant_id),
        key_id=str(api_key_record.id)
    )
