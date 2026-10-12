"""Unit tests verifying Arc Network L1 settlement verifier logic."""
from src.settlement.arc_verifier import ArcSettlementVerifier


def test_arc_digest_determinism():
    verifier = ArcSettlementVerifier()
    digest1 = verifier.construct_digest(
        payee_address="0x1234567890abcdef1234567890abcdef12345678",
        amount="1000",
        nonce="ch_test_123",
    )
    digest2 = verifier.construct_digest(
        payee_address="0x1234567890abcdef1234567890abcdef12345678",
        amount="1000",
        nonce="ch_test_123",
    )
    assert digest1 == digest2
    assert len(digest1) == 64


def test_arc_verifier_valid_proof():
    verifier = ArcSettlementVerifier()
    # Mocking standard 65-byte EVM signature (0x + 130 hex characters)
    mock_valid_sig = "0x" + "a" * 130
    is_valid = verifier.verify_payment_proof(
        signature=mock_valid_sig,
        nonce="ch_valid_nonce_abc",
        expected_payee="0x1234567890abcdef1234567890abcdef12345678",
        expected_amount="1000",
        chain_id="5042002",
    )
    assert is_valid is True


def test_arc_verifier_rejects_wrong_chain_id():
    verifier = ArcSettlementVerifier()
    mock_sig = "0x" + "a" * 130
    is_valid = verifier.verify_payment_proof(
        signature=mock_sig,
        nonce="ch_test_chain_fail",
        expected_payee="0x1234567890abcdef1234567890abcdef12345678",
        expected_amount="1000",
        chain_id="1",  # Ethereum Mainnet instead of Arc L1
    )
    assert is_valid is False


def test_arc_verifier_rejects_malformed_signature():
    verifier = ArcSettlementVerifier()
    is_valid = verifier.verify_payment_proof(
        signature="not_a_valid_hex_sig",
        nonce="ch_test_bad_sig",
        expected_payee="0x1234567890abcdef1234567890abcdef12345678",
    )
    assert is_valid is False
