import os
import hashlib
import hmac
import json
from typing import Any, Dict

# Secrets should be loaded from environment variables in production
SIGNING_SECRET = os.getenv("LAYER4_SIGNING_SECRET", "bristlecone_layer4_signing_secret_key").encode("utf-8")


class PayloadSigner:
    """Provides canonical JSON hashing and HMAC-SHA256 signature generation/verification."""

    @staticmethod
    def serialize_canonical(payload: Dict[str, Any]) -> bytes:
        """Deterministically serializes JSON dictionaries (sorted keys, no spaces)."""
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def generate_hash(cls, payload: Dict[str, Any]) -> str:
        """Generates a SHA-256 digest of the canonical payload."""
        canonical_bytes = cls.serialize_canonical(payload)
        return hashlib.sha256(canonical_bytes).hexdigest()

    @classmethod
    def sign_payload(cls, payload: Dict[str, Any]) -> str:
        """Generates an HMAC-SHA256 signature for an approved payload."""
        canonical_bytes = cls.serialize_canonical(payload)
        return hmac.new(SIGNING_SECRET, canonical_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, payload: Dict[str, Any], signature: str) -> bool:
        """Constant-time verification of payload signature integrity."""
        expected_sig = cls.sign_payload(payload)
        return hmac.compare_digest(expected_sig, signature)
