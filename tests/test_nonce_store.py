"""Unit tests verifying NonceStore replay prevention and lifecycle mechanics."""
import time
from src.gateway.nonce_store import NonceStore


def test_nonce_generation_and_consumption():
    store = NonceStore(default_ttl_seconds=60)
    nonce = store.generate_nonce()

    assert nonce.startswith("ch_")
    assert store.active_count() == 1

    # First consumption succeeds
    assert store.verify_and_consume(nonce) is True
    assert store.active_count() == 0


def test_nonce_replay_prevention():
    store = NonceStore(default_ttl_seconds=60)
    nonce = store.generate_nonce()

    # First consumption succeeds
    assert store.verify_and_consume(nonce) is True

    # Immediate second consumption must fail (double-spend / replay prevention)
    assert store.verify_and_consume(nonce) is False


def test_nonce_expiration():
    # Generate nonce with 1-second TTL
    store = NonceStore(default_ttl_seconds=1)
    nonce = store.generate_nonce(ttl_seconds=1)

    time.sleep(1.1)

    # Consumption after expiration must fail
    assert store.verify_and_consume(nonce) is False
    assert store.active_count() == 0


def test_nonce_purge():
    store = NonceStore(default_ttl_seconds=1)
    store.generate_nonce(ttl_seconds=1)
    store.generate_nonce(ttl_seconds=1)
    store.generate_nonce(ttl_seconds=60)  # active

    time.sleep(1.1)
    purged = store.purge_expired()

    assert purged == 2
    assert store.active_count() == 1
