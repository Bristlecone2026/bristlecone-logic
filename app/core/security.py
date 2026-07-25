import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

SECRET_API_KEY = os.getenv("API_KEY", "bristlecone-dev-key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key and api_key == SECRET_API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: Invalid or missing API Key"
    )
