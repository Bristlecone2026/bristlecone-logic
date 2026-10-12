"""
Bristlecone Logic - Server-Side Tollbooth Gateway
Intercepts incoming agent egress requests, issues HTTP 402 challenges,
validates cryptographic settlement proofs, and enforces anti-replay policies.
"""
import inspect
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from src.gateway.nonce_store import NonceStore
from src.settlement.arc_verifier import ArcSettlementVerifier
from src.settlement.xrpl_verifier import XRPLSettlementVerifier

logger = logging.getLogger("bristlecone.tollbooth")


class TollboothGateway:
    """
    Server-side settlement gatekeeper.
    Evaluates requests against pricing policies, generates single-use 402 challenges,
    and validates payment signatures across Arc L1 and XRPL rails.
    """

    def __init__(
        self,
        payee_address: str,
        price_base_units: str = "1000",
        asset_id: str = "USDC",
        network_id: str = "5042002",
        rail: str = "arc",
        nonce_store: Optional[NonceStore] = None,
        arc_verifier: Optional[Callable[..., bool]] = None,
        xrpl_verifier: Optional[Callable[..., bool]] = None,
    ):
        self.payee_address = payee_address
        self.price_base_units = price_base_units
        self.asset_id = asset_id
        self.network_id = network_id
        self.rail = rail.lower()
        self.nonce_store = nonce_store or NonceStore()

        # Default to native verification engines if custom callables not supplied
        self.arc_verifier = arc_verifier or ArcSettlementVerifier().verify_payment_proof
        self.xrpl_verifier = xrpl_verifier or XRPLSettlementVerifier().verify_channel_claim

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

    def _call_verifier(self, verifier: Callable[..., bool], *args: Any) -> bool:
        """
        Invokes verifier matching positional parameter length.
        """
        sig = inspect.signature(verifier)
        accepted_count = len(sig.parameters)
        return bool(verifier(*args[:accepted_count]))

    def evaluate_request(
        self, headers: Dict[str, str]
    ) -> Tuple[bool, int, Dict[str, Any]]:
        """
        Evaluates whether an incoming agent request provides valid payment proof.
        Returns: (is_authorized, status_code, payload_or_headers)
        """
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
        if self.rail == "arc":
            is_valid = self._call_verifier(
                self.arc_verifier,
                signature,
                nonce,
                self.payee_address,
                self.price_base_units,
                self.network_id,
            )
        elif self.rail == "xrpl":
            is_valid = self._call_verifier(
                self.xrpl_verifier,
                signature,
                nonce,
                self.payee_address,
                self.price_base_units,
            )

        if not is_valid:
            logger.warning(f"Rejected request: Cryptographic verification failed for rail {self.rail}")
            return False, 403, {"error": "Cryptographic payment proof verification failed."}

        # 4. Authorized Access
        return True, 200, {"status": "authorized"}
