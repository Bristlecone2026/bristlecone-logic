import hashlib
from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import PyJWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.database import get_db
from app.models import User
from app.schemas import TokenData
from app.core.security import SECRET_KEY, ALGORITHM

security_bearer = HTTPBearer(auto_error=False)

async def get_current_tenant_or_user(
    db: AsyncSession = Depends(get_db),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not auth or not auth.credentials:
        raise credentials_exception

    token = auth.credentials

    # Path A: Bristlecone API Key Auth (bcl_...)
    if token.startswith("bcl_"):
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        
        query = text("""
            SELECT k.id as key_id, k.tenant_id, k.is_active as key_active,
                   t.name as tenant_name, t.credit_balance_usd, t.is_active as tenant_active
            FROM api_keys k
            JOIN tenants t ON k.tenant_id = t.id
            WHERE k.key_hash = :khash
        """)
        result = await db.execute(query, {"khash": key_hash})
        row = result.mappings().first()

        if not row or not row["key_active"] or not row["tenant_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or deactivated API Key",
            )

        # Update last_used_at on valid invocation
        await db.execute(
            text("UPDATE api_keys SET last_used_at = NOW() WHERE id = :kid"),
            {"kid": row["key_id"]}
        )
        await db.commit()

        return {
            "auth_type": "api_key",
            "tenant_id": str(row["tenant_id"]),
            "key_id": str(row["key_id"]),
            "tenant_name": row["tenant_name"],
            "credit_balance_usd": float(row["credit_balance_usd"])
        }

    # Path B: Standard JWT User Auth
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        org_id: int = payload.get("org_id")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email, org_id=org_id)
    except (PyJWTError, ValidationError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == token_data.email))
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    return {
        "auth_type": "jwt",
        "user_id": user.id,
        "email": user.email,
        "organization_id": getattr(user, "organization_id", "org_default")
    }

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    auth_ctx: Dict[str, Any] = Depends(get_current_tenant_or_user)
) -> Dict[str, Any]:
    return auth_ctx
