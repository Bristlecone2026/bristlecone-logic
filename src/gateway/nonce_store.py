"""
Bristlecone Logic - Server Gateway Replay Defense
In-memory sliding-window TTL nonce store for M2M settlement challenges.
"""
import secrets
import time
import threading
from typing import Dict, Optional


class NonceStore:
    """
    Thread-safe, sliding-window nonce tracker preventing double-spend
    and replay attacks against HTTP 402 payment challenge receipts.
    """

    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl = default_ttl_seconds
        self._store: Dict[str, float] = {}  # nonce -> expiration timestamp
        self._lock = threading.Lock()

    def generate_nonce(self, ttl_seconds: Optional[int] = None) -> str:
        """
        Generates a high-entropy hex nonce bound to an absolute expiration timestamp.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        nonce = f"ch_{secrets.token_hex(16)}"
        expires_at = time.time() + ttl

        with self._lock:
            self._store[nonce] = expires_at

        return nonce

    def verify_and_consume(self, nonce: str) -> bool:
        """
        Atomically validates and consumes a challenge nonce.
        Returns True if valid and unexpired; False if nonexistent, expired, or already consumed.
        """
        if not nonce:
            return False

        current_time = time.time()
        with self._lock:
            expires_at = self._store.get(nonce)
            if expires_at is None:
                return False

            # Delete immediately to guarantee single-use consumption
            del self._store[nonce]

            if current_time > expires_at:
                return False

            return True

    def purge_expired(self) -> int:
        """
        Prunes expired nonces from memory to prevent unbounded heap growth.
        Returns the number of purged nonces.
        """
        current_time = time.time()
        with self._lock:
            expired_keys = [k for k, exp in self._store.items() if current_time > exp]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)

    def active_count(self) -> int:
        """Returns the number of unconsumed nonces currently tracked."""
        with self._lock:
            return len(self._store)
