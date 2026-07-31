import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Union, Any
from fastapi import Header, HTTPException, Depends, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.auth import ApiKey, UsageLog
from app.core.config import SECRET_KEY, ADMIN_SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
except ImportError:
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password

try:
    import jwt
    def create_access_token(subject: Union[str, Any], organization_id: Optional[int] = None, expires_delta: Optional[timedelta] = None) -> str:
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode = {"exp": expire, "sub": str(subject)}
        if organization_id is not None:
            to_encode["organization_id"] = organization_id
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
except ImportError:
    def create_access_token(subject: Union[str, Any], organization_id: Optional[int] = None, expires_delta: Optional[timedelta] = None) -> str:
        import base64, json
        header = base64.b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode()
        payload = base64.b64encode(json.dumps({"sub": str(subject), "organization_id": organization_id}).encode()).decode()
        sig = base64.b64encode(hashlib.sha256(f"{header}.{payload}".encode()).hexdigest().encode()).decode()
        return f"{header}.{payload}.{sig}"

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

async def verify_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> bool:
    provided_key = x_admin_key or x_api_key
    if not provided_key or provided_key != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "admin_access_required", "message": "Valid administrative credentials are required."}
        )
    return True
