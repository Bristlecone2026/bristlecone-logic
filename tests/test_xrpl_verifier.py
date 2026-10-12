"""Unit tests verifying XRPL Payment Channel settlement verifier mechanics."""
from src.settlement.xrpl_verifier import XRPLSettlementVerifier


def test_xrpl_digest_determinism():
    verifier = XRPLSettlementVerifier()
    digest1 = verifier.construct_channel_digest(
        payee_address="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        drops_amount="5000000",
        nonce="ch_xrpl_123",
    )
    digest2 = verifier.construct_channel_digest(
        payee_address="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        drops_amount="5000000",
        nonce="ch_xrpl_123",
    )
    assert digest1 == digest2
    assert len(digest1) == 64


def test_xrpl_verifier_valid_proof():
    verifier = XRPLSettlementVerifier()
    is_valid = verifier.verify_channel_claim(
        signature="xrpl_claim_sig_valid_hex_0123456789abcdef",
        nonce="ch_xrpl_valid_nonce",
        expected_payee="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        expected_drops="5000000",
    )
    assert is_valid is True


def test_xrpl_verifier_rejects_invalid_account_address():
    verifier = XRPLSettlementVerifier()
    is_valid = verifier.verify_channel_claim(
        signature="xrpl_claim_sig_valid_hex_0123456789abcdef",
        nonce="ch_test_nonce",
        expected_payee="0x1234567890abcdef1234567890abcdef12345678",  # EVM address passed to XRPL
        expected_drops="5000000",
    )
    assert is_valid is False


def test_xrpl_verifier_rejects_invalid_drops_amount():
    verifier = XRPLSettlementVerifier()
    is_valid = verifier.verify_channel_claim(
        signature="xrpl_claim_sig_valid_hex_0123456789abcdef",
        nonce="ch_test_nonce",
        expected_payee="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        expected_drops="-500",  # Negative drops rejected
    )
    assert is_valid is False


def test_xrpl_verifier_rejects_malformed_signature():
    verifier = XRPLSettlementVerifier()
    is_valid = verifier.verify_channel_claim(
        signature="invalid_signature",
        nonce="ch_test_nonce",
        expected_payee="rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe",
        expected_drops="5000000",
    )
    assert is_valid is False
