import hmac
import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

# Extract header 'X-API-Key' from incoming requests
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Master key loaded from environment variable, falling back to local dev secret
SECRET_API_KEY = os.getenv("BRISTLECONE_API_KEY", "bristlecone_dev_secret_key_change_in_prod")

async def verify_api_key(api_key_header: str = Security(API_KEY_HEADER)) -> str:
    """
    Validates incoming request API key against configured environment key.
    Uses hmac.compare_digest for constant-time comparison to eliminate timing attacks.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failure: Missing 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Constant-time comparison prevents byte-by-byte side-channel timing attacks
    is_valid = hmac.compare_digest(
        api_key_header.encode("utf-8"), 
        SECRET_API_KEY.encode("utf-8")
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication failure: Invalid API key credentials.",
        )
        
    return api_key_header
