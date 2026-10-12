"""
Bristlecone Logic - Runtime Security & Settlement Engine
Client-Side HTTP 402 (Payment Required) Protocol Handler
Supports Arc L1 (USDC Native) and XRPL (Payment Channels).
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import urllib.error
import urllib.request

logger = logging.getLogger("bristlecone.http_402")


class SettlementException(Exception):
    """Raised when an M2M settlement negotiation or signature dispatch fails."""
    pass


@dataclass
class PaymentChallenge:
    rail: str                # "arc" or "xrpl"
    network_id: str          # "5042002" (Arc) or "xrpl-mainnet"
    payee_address: str       # Destination address or channel recipient
    amount: str              # Base units (USDC atomic units or drops)
    asset_id: str            # "USDC" or "XRP"
    nonce: str               # Challenge ID / replay nonce


class HTTP402Handler:
    """
    Client middleware intercepting HTTP 402 responses and dispatching
    cryptographic micro-settlement signing for Arc L1 and XRPL rails.
    """

    def __init__(
        self,
        arc_signer: Optional[Callable[[PaymentChallenge], str]] = None,
        xrpl_signer: Optional[Callable[[PaymentChallenge], str]] = None,
    ):
        self.arc_signer = arc_signer
        self.xrpl_signer = xrpl_signer

    def parse_challenge(self, headers: Dict[str, str], body: bytes) -> PaymentChallenge:
        """
        Parses challenge parameters from Payment-Required header or JSON body.
        """
        raw_header = headers.get("Payment-Required") or headers.get("payment-required")
        if raw_header:
            try:
                data = json.loads(raw_header)
                return PaymentChallenge(
                    rail=str(data["rail"]).lower(),
                    network_id=str(data["network_id"]),
                    payee_address=str(data["payee_address"]),
                    amount=str(data["amount"]),
                    asset_id=str(data.get("asset_id", "USDC")),
                    nonce=str(data.get("nonce", "")),
                )
            except (json.JSONDecodeError, KeyError) as err:
                logger.warning(f"Malformed Payment-Required header: {err}")

        try:
            data = json.loads(body.decode("utf-8"))
            if "settlement_challenge" in data:
                c = data["settlement_challenge"]
                return PaymentChallenge(
                    rail=str(c["rail"]).lower(),
                    network_id=str(c["network_id"]),
                    payee_address=str(c["payee_address"]),
                    amount=str(c["amount"]),
                    asset_id=str(c.get("asset_id", "USDC")),
                    nonce=str(c.get("nonce", "")),
                )
        except Exception as err:
            raise SettlementException(f"Unparseable HTTP 402 payload: {err}")

        raise SettlementException("No valid settlement challenge found in 402 response.")

    def resolve_signature(self, challenge: PaymentChallenge) -> str:
        """
        Routes the payment challenge to the appropriate rail signing routine.
        """
        if challenge.rail == "arc":
            if not self.arc_signer:
                raise SettlementException("Arc L1 settlement required, but arc_signer is not configured.")
            return self.arc_signer(challenge)

        if challenge.rail == "xrpl":
            if not self.xrpl_signer:
                raise SettlementException("XRPL settlement required, but xrpl_signer is not configured.")
            return self.xrpl_signer(challenge)

        raise SettlementException(f"Unsupported settlement rail requested: {challenge.rail}")

    def execute_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Executes HTTP request, catches 402 challenges, signs settlement proof,
        and resubmits the request with Payment-Signature headers.
        """
        req_headers = headers.copy() if headers else {}
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                return {
                    "status_code": resp.status,
                    "headers": dict(resp.headers),
                    "body": resp.read(),
                }
        except urllib.error.HTTPError as err:
            if err.code != 402:
                raise err

            logger.info("Received HTTP 402 Payment Required; initiating M2M settlement handshake.")
            challenge = self.parse_challenge(dict(err.headers), err.read())
            signature = self.resolve_signature(challenge)

            req_headers["Payment-Signature"] = signature
            req_headers["Payment-Challenge-Id"] = challenge.nonce
            retry_req = urllib.request.Request(url, data=data, headers=retry_headers if 'retry_headers' in locals() else req_headers, method=method)

            with urllib.request.urlopen(retry_req) as retry_resp:
                return {
                    "status_code": retry_resp.status,
                    "headers": dict(retry_resp.headers),
                    "body": retry_resp.read(),
                }
