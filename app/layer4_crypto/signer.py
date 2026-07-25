import hmac
import hashlib
from typing import Any
from app.config import settings

SIGNING_SECRET = getattr(settings, "HMAC_SECRET", "bristlecone-zero-trust-secret-key").encode("utf-8")

def sign_payload(payload: Any) -> str:
    if not isinstance(payload, str):
        payload = str(payload)
    return hmac.new(SIGNING_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()

def verify_signature(payload: Any, signature: str) -> bool:
    expected = sign_payload(payload)
    return hmac.compare_digest(expected, signature)

class PayloadSigner:
    @staticmethod
    def sign_payload(payload: Any) -> str:
        return sign_payload(payload)

    @staticmethod
    def verify_signature(payload: Any, signature: str) -> bool:
        return verify_signature(payload, signature)
