"""
Bristlecone Logic - Server-Side Tollbooth Gateway
Intercepts incoming agent egress requests, issues HTTP 402 challenges,
validates cryptographic settlement proofs, and enforces anti-replay policies.
"""
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from src.gateway.nonce_store import NonceStore

logger = logging.getLogger("bristlecone.tollbooth")


class TollboothGateway:
    """
    Server-side settlement gatekeeper.
    Evaluates requests against pricing policies, generates single-use 402 challenges,
    and validates payment signatures across Arc and XRPL rails.
    """

    def __init__(
        self,
        payee_address: str,
        price_base_units: str = "1000",
        asset_id: str = "USDC",
        network_id: str = "5042002",
        rail: str = "arc",
        nonce_store: Optional[NonceStore] = None,
        arc_verifier: Optional[Callable[[str, str, str], bool]] = None,
        xrpl_verifier: Optional[Callable[[str, str, str], bool]] = None,
    ):
        self.payee_address = payee_address
        self.price_base_units = price_base_units
        self.asset_id = asset_id
        self.network_id = network_id
        self.rail = rail.lower()
        self.nonce_store = nonce_store or NonceStore()
        self.arc_verifier = arc_verifier
        self.xrpl_verifier = xrpl_verifier

    def issue_challenge(self) -> Dict[str, Any]:
        """
        Generates a fresh single-use payment challenge.
        """
        nonce = self.nonce_store.generate_nonce()
        return {
            "rail": self.rail,
            "network_id": self.network_id,
            "payee_address": self.payee_address,
            "amount": self.price_base_units,
            "asset_id": self.asset_id,
            "nonce": nonce,
        }

    def evaluate_request(
        self, headers: Dict[str, str]
    ) -> Tuple[bool, int, Dict[str, Any]]:
        """
        Evaluates whether an incoming agent request provides valid payment proof.
        Returns: (is_authorized, status_code, payload_or_headers)
        """
        # Case-insensitive header extraction
        norm_headers = {k.lower(): v for k, v in headers.items()}
        signature = norm_headers.get("payment-signature")
        nonce = norm_headers.get("payment-challenge-id")

        # 1. Missing payment metadata -> Issue HTTP 402 Challenge
        if not signature or not nonce:
            challenge = self.issue_challenge()
            return False, 402, {
                "Payment-Required": json.dumps(challenge),
                "Content-Type": "application/json",
            }

        # 2. Replay Defense -> Validate and consume nonce atomically
        if not self.nonce_store.verify_and_consume(nonce):
            logger.warning(f"Rejected request: Invalid or replayed nonce '{nonce}'")
            return False, 403, {"error": "Payment nonce expired, invalid, or replayed."}

        # 3. Cryptographic Verification by Rail
        is_valid = False
        if self.rail == "arc" and self.arc_verifier:
            is_valid = self.arc_verifier(signature, nonce, self.payee_address)
        elif self.rail == "xrpl" and self.xrpl_verifier:
            is_valid = self.xrpl_verifier(signature, nonce, self.payee_address)
        elif not self.arc_verifier and not self.xrpl_verifier:
            # Fallback for mock environments / pass-through test signers
            is_valid = signature.startswith("0x") or signature.startswith("xrpl_")

        if not is_valid:
            logger.warning(f"Rejected request: Cryptographic verification failed for rail {self.rail}")
            return False, 403, {"error": "Cryptographic payment proof verification failed."}

        # 4. Authorized Access
        return True, 200, {"status": "authorized"}
