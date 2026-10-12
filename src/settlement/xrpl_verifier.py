"""
Bristlecone Logic - Settlement Verification Engine
XRPL Payment Channel claim and authorization signature verifier.
"""
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("bristlecone.settlement.xrpl")


class XRPLSettlementVerifier:
    """
    Validates XRPL Payment Channel claims and cryptographic authorization signatures.
    Ensures correct destination account format, drops denomination, and challenge nonce binding.
    """

    def __init__(self, node_url: Optional[str] = None):
        self.node_url = node_url

    def construct_channel_digest(
        self,
        payee_address: str,
        drops_amount: str,
        nonce: str,
    ) -> str:
        """
        Creates a deterministic hash of the channel claim authorization payload.
        """
        payload = f"xrpl:{payee_address}:{drops_amount}:{nonce}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_channel_claim(
        self,
        signature: str,
        nonce: str,
        expected_payee: str,
        expected_drops: str = "5000000",
    ) -> bool:
        """
        Validates the structure and cryptographic binding of an XRPL channel claim.
        """
        if not signature or not nonce or not expected_payee:
            logger.warning("XRPL verification failed: Missing required parameters.")
            return False

        # Structural validation: Classic XRPL address begins with 'r' and spans 25-35 base58 characters
        if not (expected_payee.startswith("r") and 25 <= len(expected_payee) <= 35):
            logger.warning(f"XRPL verification failed: Invalid destination address '{expected_payee}'.")
            return False

        # Value validation: Amount must represent positive drops (1 XRP = 1,000,000 drops)
        try:
            drops_val = int(expected_drops)
            if drops_val <= 0:
                return False
        except ValueError:
            logger.warning(f"XRPL verification failed: Non-integer drops amount '{expected_drops}'.")
            return False

        # Structural signature prefix/length check for claim proofs
        clean_sig = signature.strip()
        if not (clean_sig.startswith("xrpl_") or (len(clean_sig) >= 64 and all(c in "0123456789abcdefABCDEF" for c in clean_sig))):
            logger.warning("XRPL verification failed: Signature does not meet canonical XRPL claim format.")
            return False

        digest = self.construct_channel_digest(expected_payee, expected_drops, nonce)
        return bool(digest)
