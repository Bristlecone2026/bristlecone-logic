"""Unit test suite for Bristlecone HTTP 402 client mechanics."""
import json
import pytest
from src.adapters.http_402_handler import HTTP402Handler, PaymentChallenge, SettlementException


def mock_arc_signer(challenge: PaymentChallenge) -> str:
    assert challenge.rail == "arc"
    assert challenge.network_id == "5042002"
    assert challenge.amount == "1000"
    return "0xmocked_arc_signature_proof_abc123"


def mock_xrpl_signer(challenge: PaymentChallenge) -> str:
    assert challenge.rail == "xrpl"
    assert challenge.network_id == "xrpl-mainnet"
    assert challenge.amount == "5000000"
    return "xrpl_channel_claim_proof_xyz789"


def test_parse_header_challenge_arc():
    handler = HTTP402Handler(arc_signer=mock_arc_signer)
    header_data = {
        "Payment-Required": json.dumps({
            "rail": "arc",
            "network_id": "5042002",
            "payee_address": "0x1234567890abcdef1234567890abcdef12345678",
            "amount": "1000",
            "asset_id": "USDC",
            "nonce": "ch_arc_test_01"
        })
    }
    challenge = handler.parse_challenge(header_data, b"")
    assert challenge.rail == "arc"
    assert challenge.amount == "1000"
    sig = handler.resolve_signature(challenge)
    assert sig == "0xmocked_arc_signature_proof_abc123"


def test_parse_body_challenge_xrpl():
    handler = HTTP402Handler(xrpl_signer=mock_xrpl_signer)
    body_data = json.dumps({
        "error": "Payment Required",
        "settlement_challenge": {
            "rail": "xrpl",
            "network_id": "xrpl-mainnet",
            "payee_address": "rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
            "amount": "5000000",
            "asset_id": "XRP",
            "nonce": "ch_xrpl_test_02"
        }
    }).encode("utf-8")
    challenge = handler.parse_challenge({}, body_data)
    assert challenge.rail == "xrpl"
    assert challenge.amount == "5000000"
    sig = handler.resolve_signature(challenge)
    assert sig == "xrpl_channel_claim_proof_xyz789"


def test_unsupported_rail_rejection():
    handler = HTTP402Handler()
    challenge = PaymentChallenge(
        rail="solana",
        network_id="101",
        payee_address="unsupported_addr",
        amount="500",
        asset_id="SOL",
        nonce="ch_bad_001"
    )
    with pytest.raises(SettlementException):
        handler.resolve_signature(challenge)
