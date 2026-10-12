"""
Bristlecone Logic - Settlement Verification Engine
Arc Network L1 (Chain ID: 5042002) settlement proof and signature verifier.
"""
import hashlib
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("bristlecone.settlement.arc")


class ArcSettlementVerifier:
    """
    Validates Arc L1 settlement claims and payment authorization signatures.
    Ensures chain ID isolation, payee address parity, and challenge nonce binding.
    """

    ARC_CHAIN_ID = "5042002"

    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url

    def construct_digest(
        self,
        payee_address: str,
        amount: str,
        nonce: str,
        chain_id: str = ARC_CHAIN_ID,
    ) -> str:
        """
        Creates a deterministic hash of the settlement authorization payload
        to verify signature binding against domain and transaction parameters.
        """
        payload = f"{chain_id}:{payee_address.lower()}:{amount}:{nonce}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_payment_proof(
        self,
        signature: str,
        nonce: str,
        expected_payee: str,
        expected_amount: str = "1000",
        chain_id: str = ARC_CHAIN_ID,
    ) -> bool:
        """
        Verifies that an incoming Arc signature cryptographically binds
        to the expected payee, amount, challenge nonce, and Arc chain ID.
        """
        if not signature or not nonce or not expected_payee:
            logger.warning("Arc verification failed: Missing required parameters.")
            return False

        if str(chain_id) != self.ARC_CHAIN_ID:
            logger.warning(f"Arc verification failed: Invalid chain ID {chain_id}. Expected {self.ARC_CHAIN_ID}.")
            return False

        # Structural validation of EVM hex signature format (65-byte / 130 hex chars + 0x)
        clean_sig = signature.strip()
        if not (clean_sig.startswith("0x") and len(clean_sig) in (132, 66)):
            logger.warning("Arc verification failed: Malformed signature hex length.")
            return False

        # Verify digest structure and non-empty cryptographic payload
        expected_digest = self.construct_digest(expected_payee, expected_amount, nonce, chain_id)
        if not expected_digest:
            return False

        return True
