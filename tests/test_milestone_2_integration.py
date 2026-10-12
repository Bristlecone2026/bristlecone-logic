"""Integration tests verifying full Milestone 2 dual-rail tollbooth execution."""
import json
from src.gateway.tollbooth import TollboothGateway


def test_milestone_2_arc_end_to_end_lifecycle():
    # Production Arc Tollbooth Gateway setup
    gateway = TollboothGateway(
        payee_address="0x1234567890abcdef1234567890abcdef12345678",
        price_base_units="1000",
        asset_id="USDC",
        network_id="5042002",
        rail="arc",
    )

    # 1. Unauthenticated request triggers 402 challenge
    auth, code, headers = gateway.evaluate_request({})
    assert auth is False
    assert code == 402
    challenge = json.loads(headers["Payment-Required"])
    nonce = challenge["nonce"]
    assert challenge["rail"] == "arc"
    assert challenge["network_id"] == "5042002"

    # 2. Submit valid Arc 65-byte EVM signature proof
    valid_sig = "0x" + "c" * 130
    req_headers = {
        "Payment-Signature": valid_sig,
        "Payment-Challenge-Id": nonce,
    }
    auth, code, payload = gateway.evaluate_request(req_headers)
    assert auth is True
    assert code == 200
    assert payload["status"] == "authorized"

    # 3. Nonce consumed: Replay of same authorization must be rejected with 403
    auth_replay, code_replay, payload_replay = gateway.evaluate_request(req_headers)
    assert auth_replay is False
    assert code_replay == 403
    assert "replayed" in payload_replay["error"]


def test_milestone_2_xrpl_end_to_end_lifecycle():
    # Production XRPL Tollbooth Gateway setup
    gateway = TollboothGateway(
        payee_address="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        price_base_units="5000000",
        asset_id="XRP",
        network_id="xrpl-mainnet",
        rail="xrpl",
    )

    # 1. Unauthenticated request triggers 402 challenge
    auth, code, headers = gateway.evaluate_request({})
    assert auth is False
    assert code == 402
    challenge = json.loads(headers["Payment-Required"])
    nonce = challenge["nonce"]
    assert challenge["rail"] == "xrpl"

    # 2. Submit valid XRPL payment channel claim proof
    valid_claim = "xrpl_claim_sig_valid_hex_0123456789abcdef"
    req_headers = {
        "Payment-Signature": valid_claim,
        "Payment-Challenge-Id": nonce,
    }
    auth, code, payload = gateway.evaluate_request(req_headers)
    assert auth is True
    assert code == 200
    assert payload["status"] == "authorized"

    # 3. Nonce consumed: Replay of same XRPL claim must be rejected with 403
    auth_replay, code_replay, payload_replay = gateway.evaluate_request(req_headers)
    assert auth_replay is False
    assert code_replay == 403
    assert "replayed" in payload_replay["error"]
