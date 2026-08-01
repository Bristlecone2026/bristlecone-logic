import hashlib
import logging
from decimal import Decimal
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.auth import ApiKey
from app.models.billing import TenantBalance, ApiUsageLog
from app.core.rate_limiter import RedisRateLimiter

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
rate_limiter = RedisRateLimiter(requests_per_minute=60)

def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

class MeteredAuth:
    def __init__(self, unit_cost: float = 0.01, units: int = 1):
        self.unit_cost = Decimal(str(unit_cost))
        self.units = units

    async def __call__(
        self,
        api_key: Optional[str] = Security(api_key_header),
        db: AsyncSession = Depends(get_db)
    ) -> ApiKey:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header"
            )

        # 1. Quick key hash for identifier
        key_hash = hash_api_key(api_key)

        # 2. Redis Rate Limit Check BEFORE hitting Postgres DB
        await rate_limiter.check_rate_limit(key_hash)

        # 3. Verify API Key in DB
        key_record = await self._verify_key_by_hash(key_hash, db)
        if not key_record or not getattr(key_record, "is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key"
            )

        tenant_id_str = str(key_record.tenant_id)

        # 4. Balance Deduction Check in DB
        balance_stmt = select(TenantBalance).where(
            TenantBalance.tenant_id == tenant_id_str
        )
        result = await db.execute(balance_stmt)
        tenant_balance = result.scalars().first()

        total_cost = self.unit_cost * Decimal(self.units)

        if not tenant_balance or tenant_balance.balance_usd < total_cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient tenant credit balance for M2M invocation"
            )

        tenant_balance.balance_usd -= total_cost
        
        usage_entry = ApiUsageLog(
            tenant_id=tenant_id_str,
            api_key_id=key_record.id,
            endpoint="m2m_request",
            units_consumed=self.units,
            cost=total_cost
        )
        
        db.add(usage_entry)
        await db.commit()

        return key_record

    async def _verify_key_by_hash(self, key_hash: str, db: AsyncSession) -> Optional[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        res = await db.execute(stmt)
        return res.scalars().first()
