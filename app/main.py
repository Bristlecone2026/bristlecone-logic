import hashlib
import os
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Depends, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
import redis.asyncio as aioredis

# DB & Redis Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/bristlecone_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

Base = declarative_base()

# Models
class TenantBalance(Base):
    __tablename__ = "tenant_balances"
    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    balance_usd: Mapped[Decimal] = mapped_column()

class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column()
    key_hash: Mapped[str] = mapped_column()

class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column()
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    endpoint: Mapped[str] = mapped_column()
    units_consumed: Mapped[int] = mapped_column(default=1)
    cost: Mapped[Decimal] = mapped_column()

app = FastAPI(title="Bristlecone Logic M2M Swarm")

async def get_db():
    async with async_session_factory() as session:
        yield session

# Isolated Background Worker for Audit Logging
async def log_usage_background(tenant_id: str, key_id: str, endpoint: str, cost: Decimal):
    async with async_session_factory() as session:
        async with session.begin():
            log_entry = ApiUsageLog(
                tenant_id=tenant_id,
                api_key_id=uuid.UUID(key_id) if key_id else None,
                endpoint=endpoint,
                units_consumed=1,
                cost=cost
            )
            session.add(log_entry)

# Rate Limiter Helper
async def check_rate_limit(key_id: str, limit: int = 60, window: int = 60) -> tuple[bool, int]:
    redis_key = f"rate_limit:{key_id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(redis_key)
        pipe.ttl(redis_key)
        results = await pipe.execute()
    
    current_requests = results[0]
    ttl = results[1]

    if ttl == -1:
        await redis_client.expire(redis_key, window)
    
    remaining = max(0, limit - current_requests)
    allowed = current_requests <= limit
    return allowed, remaining

# Metered Route
@app.post("/api/v1/keys/test-metered")
async def test_metered_endpoint(
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API Key")

    # 1. SHA-256 Hash & API Key Lookup
    hashed_key = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    key_stmt = select(ApiKey).where(ApiKey.key_hash == hashed_key)
    key_result = await db.execute(key_stmt)
    api_key_obj = key_result.scalar_one_or_none()

    if not api_key_obj:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")

    # 2. Redis Rate Limit Enforcement
    allowed, remaining = await check_rate_limit(str(api_key_obj.id))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "0"}
        )

    # 3. Metering Deduction with Pessimistic Lock
    cost = Decimal("0.000100")
    bal_stmt = (
        select(TenantBalance)
        .where(TenantBalance.tenant_id == str(api_key_obj.tenant_id))
        .with_for_update()
    )
    bal_result = await db.execute(bal_stmt)
    tenant_bal = bal_result.scalar_one_or_none()

    if not tenant_bal or tenant_bal.balance_usd < cost:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient balance")

    tenant_bal.balance_usd -= cost
    await db.commit()

    # 4. Offload Audit Write to Background Task
    background_tasks.add_task(
        log_usage_background,
        tenant_id=str(api_key_obj.tenant_id),
        key_id=str(api_key_obj.id),
        endpoint="/api/v1/keys/test-metered",
        cost=cost
    )

    return {
        "status": "success",
        "message": "Request metered and processed",
        "tenant_id": str(api_key_obj.tenant_id),
        "key_id": str(api_key_obj.id)
    }
