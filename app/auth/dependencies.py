from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.auth import ApiKey, UsageLog

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_org_id(
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> int:
    """
    Validates X-API-Key header, resolves tenant organization_id, 
    and asynchronously records usage metering.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header."
        )

    stmt = select(ApiKey).where(ApiKey.key == api_key, ApiKey.is_active == True)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()

    if not key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key."
        )

    # Metering: Log API request event
    usage = UsageLog(
        organization_id=key_obj.organization_id,
        endpoint="/api/v1/dag"
    )
    db.add(usage)
    await db.commit()

    return key_obj.organization_id
