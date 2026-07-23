import hmac
import hashlib
import config

SIGNING_SECRET = config.HMAC_SECRET_KEY.encode("utf-8")

def sign_payload(payload: str) -> str:
    """Generates an HMAC-SHA256 signature for a given payload string."""
    return hmac.new(SIGNING_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()

def verify_signature(payload: str, signature: str) -> bool:
    """Verifies an HMAC-SHA256 signature against a payload string."""
    expected_signature = sign_payload(payload)
    return hmac.compare_digest(expected_signature, signature)
