from fastapi import FastAPI, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db, engine, Base
from app.models import SystemLog
from app.schemas import SystemLogCreate, SystemLogResponse

app = FastAPI(
    title="Bristlecone Logic API",
    version="1.0.0"
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "online", "service": "Bristlecone API"}

@app.post("/logs", response_model=SystemLogResponse, status_code=status.HTTP_201_CREATED)
async def create_log(payload: SystemLogCreate, db: AsyncSession = Depends(get_db)):
    new_log = SystemLog(event_type=payload.event_type, message=payload.message)
    db.add(new_log)
    await db.flush()
    await db.refresh(new_log)
    return new_log

@app.get("/logs", response_model=List[SystemLogResponse])
async def list_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemLog).order_by(SystemLog.id.desc()).limit(limit))
    return result.scalars().all()
