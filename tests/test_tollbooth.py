"""Unit tests verifying TollboothGateway challenge flow and access controls."""
import json
from src.gateway.tollbooth import TollboothGateway
from src.gateway.nonce_store import NonceStore


def test_tollbooth_issues_402_on_unauthenticated_request():
    gateway = TollboothGateway(
        payee_address="0x1234567890abcdef1234567890abcdef12345678",
        price_base_units="1000",
        rail="arc",
    )
    authorized, status_code, headers = gateway.evaluate_request({})

    assert authorized is False
    assert status_code == 402
    assert "Payment-Required" in headers

    challenge = json.loads(headers["Payment-Required"])
    assert challenge["rail"] == "arc"
    assert challenge["amount"] == "1000"
    assert challenge["nonce"].startswith("ch_")


def test_tollbooth_authorizes_valid_signature_flow():
    store = NonceStore()
    gateway = TollboothGateway(
        payee_address="0x1234567890abcdef1234567890abcdef12345678",
        nonce_store=store,
        arc_verifier=lambda sig, nonce, addr: sig == "0xvalid_arc_sig",
    )

    # 1. Request without headers triggers 402 challenge
    _, code, challenge_headers = gateway.evaluate_request({})
    assert code == 402
    challenge = json.loads(challenge_headers["Payment-Required"])
    valid_nonce = challenge["nonce"]

    # 2. Resubmit with valid signature and nonce -> 200 Authorized
    auth_headers = {
        "Payment-Signature": "0xvalid_arc_sig",
        "Payment-Challenge-Id": valid_nonce,
    }
    authorized, status_code, payload = gateway.evaluate_request(auth_headers)
    assert authorized is True
    assert status_code == 200
    assert payload["status"] == "authorized"

    # 3. Attempt replay of identical signature and nonce -> 403 Forbidden
    replayed, replay_code, replay_payload = gateway.evaluate_request(auth_headers)
    assert replayed is False
    assert replay_code == 403
    assert "replayed" in replay_payload["error"]


def test_tollbooth_rejects_invalid_cryptographic_signature():
    gateway = TollboothGateway(
        payee_address="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        rail="xrpl",
        xrpl_verifier=lambda sig, nonce, addr: sig == "xrpl_valid_claim",
    )
    # Generate valid challenge
    _, _, challenge_headers = gateway.evaluate_request({})
    nonce = json.loads(challenge_headers["Payment-Required"])["nonce"]

    # Submit invalid signature
    bad_headers = {
        "Payment-Signature": "xrpl_forged_claim",
        "Payment-Challenge-Id": nonce,
    }
    authorized, status_code, payload = gateway.evaluate_request(bad_headers)
    assert authorized is False
    assert status_code == 403
    assert "verification failed" in payload["error"]
