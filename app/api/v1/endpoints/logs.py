from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import SystemLog
from app.schemas import SystemLogCreate, SystemLogResponse
from app.core.security import verify_api_key

router = APIRouter(prefix="/logs", tags=["System Logs"])

@router.post("", response_model=SystemLogResponse, status_code=status.HTTP_201_CREATED)
async def create_log(
    payload: SystemLogCreate,
    db: AsyncSession = Depends(get_db),
    tenant_context: dict = Depends(verify_api_key)
):
    new_log = SystemLog(
        level=payload.level,
        message=payload.message,
        payload=payload.payload
    )
    db.add(new_log)
    await db.flush()
    await db.refresh(new_log)
    return new_log

@router.get("", response_model=List[SystemLogResponse])
async def list_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    tenant_context: dict = Depends(verify_api_key)
):
    result = await db.execute(select(SystemLog).order_by(SystemLog.id.desc()).limit(limit))
    return result.scalars().all()
