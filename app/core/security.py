from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
import jwt

SECRET_KEY = "bristlecone-secret-key-change-in-production"
ALGORITHM = "HS256"

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)
except ImportError:
    try:
        import bcrypt
        def verify_password(plain_password: str, hashed_password: str) -> bool:
            hashed_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_bytes)
        def get_password_hash(password: str) -> str:
            return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    except ImportError:
        import hashlib
        def verify_password(plain_password: str, hashed_password: str) -> bool:
            return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
        def get_password_hash(password: str) -> str:
            return hashlib.sha256(password.encode()).hexdigest()


def create_access_token(
    subject: Union[str, Any],
    organization_id: Optional[int] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60 * 24)

    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "org_id": organization_id
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
