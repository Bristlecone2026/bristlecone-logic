import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Union, Any
from fastapi import Header, HTTPException, Depends, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.database import get_db
from app.models.auth import ApiKey, UsageLog
from app.core.config import SECRET_KEY, ADMIN_SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

class TenantContext(BaseModel):
    tenant_id: str
    key_id: str
    rate_limit_rpm: int = 60

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

    # Fetch tenant's configured rate limit
    tenant_res = await db.execute(
        text("SELECT rate_limit_rpm FROM tenants WHERE id = :tid"),
        {"tid": api_key_record.tenant_id}
    )
    rpm_val = tenant_res.scalar()
    rate_limit_rpm = int(rpm_val) if rpm_val is not None else 60

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
        key_id=str(api_key_record.id),
        rate_limit_rpm=rate_limit_rpm
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

import socket
import ipaddress
from urllib.parse import urlparse

HARDENED_CIDRS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Localhost alias (RFC 1122)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback (RFC 1122)
    ipaddress.ip_network("10.0.0.0/8"),         # Private Network (RFC 1918)
    ipaddress.ip_network("172.16.0.0/12"),      # Private Network (RFC 1918)
    ipaddress.ip_network("192.168.0.0/16"),     # Private Network (RFC 1918)
    ipaddress.ip_network("169.254.0.0/16"),     # Link-Local / AWS/Azure/GCP IMDS (RFC 3927)
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Space / Alibaba IMDS (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol / Oracle Cloud IMDS (RFC 6890)
    ipaddress.ip_network("198.18.0.0/15"),      # Interconnect Benchmarking (RFC 2544)
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    ipaddress.ip_network("::/128"),             # IPv6 Unspecified
    ipaddress.ip_network("::1/128"),            # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),          # IPv6 Link-Local
]

def validate_safe_url(url: str) -> str:
    """
    Validates URL scheme and resolves hostname against HARDENED_CIDRS,
    unwrapping IPv4-mapped IPv6 targets to block SSRF and loopback evasions.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target URL: missing hostname."
        )

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not resolve host: {hostname} ({str(e)})"
        )

    resolved_ips = list({item[4][0] for item in addr_info})
    if not resolved_ips:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target hostname did not resolve to any IP address."
        )

    for raw_ip in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(raw_ip)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Invalid IP format ({raw_ip})."
            )

        if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
            ip_obj = ip_obj.ipv4_mapped

        for cidr in HARDENED_CIDRS:
            if ip_obj in cidr:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Target address ({ip_obj}) is in restricted range ({cidr})."
                )

    return url
