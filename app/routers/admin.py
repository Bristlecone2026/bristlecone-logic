import secrets
from typing import List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models.auth import APIKey
from app.models.usage import UsageLog

router = APIRouter(prefix="/api/v1/admin", tags=["Admin & Usage"])

class KeyCreateRequest(BaseModel):
    organization_id: int
    name: str

class KeyCreateResponse(BaseModel):
    id: int
    name: str
    organization_id: int
    api_key: str
    created_at: datetime

class KeyInfo(BaseModel):
    id: int
    name: str
    organization_id: int
    prefix: str
    is_active: bool
    created_at: datetime

class UsageSummary(BaseModel):
    organization_id: int
    total_requests: int
    endpoints: Dict[str, int]

@router.post("/keys", response_model=KeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(body: KeyCreateRequest, db: AsyncSession = Depends(get_db)):
    raw_key = f"bc_live_{secrets.token_hex(16)}"
    prefix = raw_key[:12]
    
    new_key = APIKey(
        organization_id=body.organization_id,
        name=body.name,
        key=raw_key,
        prefix=prefix,
        is_active=True
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    return KeyCreateResponse(
        id=new_key.id,
        name=new_key.name,
        organization_id=new_key.organization_id,
        api_key=raw_key,
        created_at=new_key.created_at
    )

@router.get("/keys", response_model=List[KeyInfo])
async def list_api_keys(organization_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(APIKey).where(APIKey.organization_id == organization_id, APIKey.is_active == True)
    result = await db.execute(stmt)
    keys = result.scalars().all()
    
    return [
        KeyInfo(
            id=k.id,
            name=k.name,
            organization_id=k.organization_id,
            prefix=getattr(k, "prefix", k.key[:12] if hasattr(k, "key") else "bc_live_****"),
            is_active=k.is_active,
            created_at=k.created_at
        ) for k in keys
    ]

@router.delete("/keys/{key_id}")
async def revoke_api_key(key_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(APIKey).where(APIKey.id == key_id)
    result = await db.execute(stmt)
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(status_code=404, detail="API key not found")
    
    key_obj.is_active = False
    await db.commit()
    return {"status": "success", "message": f"API key {key_id} revoked successfully"}

@router.get("/usage", response_model=UsageSummary)
async def get_usage_metrics(organization_id: int, db: AsyncSession = Depends(get_db)):
    count_stmt = select(func.count(UsageLog.id)).where(UsageLog.organization_id == organization_id)
    total_res = await db.execute(count_stmt)
    total_requests = total_res.scalar() or 0
    
    ep_stmt = (
        select(UsageLog.endpoint, func.count(UsageLog.id))
        .where(UsageLog.organization_id == organization_id)
        .group_by(UsageLog.endpoint)
    )
    ep_res = await db.execute(ep_stmt)
    endpoints = {row[0]: row[1] for row in ep_res.all()}
    
    return UsageSummary(
        organization_id=organization_id,
        total_requests=total_requests,
        endpoints=endpoints
    )
