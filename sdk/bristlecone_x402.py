"""
Bristlecone Logic - XRPL x402 Native Python Client
Enables zero-friction, pay-per-call microservice execution over XRPL Payment Channels.
"""

import httpx
from xrpl.wallet import Wallet
from xrpl.core.keypairs import sign
from typing import Dict, Any, Optional

PAYEE_TREASURY = "rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD"
DEFAULT_GATEWAY = "https://xrp.bristleconelogic.com"


class BristleconeX402Client:
    def __init__(
        self,
        wallet: Wallet,
        channel_id: str,
        gateway_url: str = DEFAULT_GATEWAY,
        initial_drops_spent: int = 0,
        timeout: float = 15.0
    ):
        """
        Initialize the autonomous x402 execution client.
        
        :param wallet: Funded xrpl.wallet.Wallet instance used to sign payment claims
        :param channel_id: 64-character hex PaymentChannel ID established to PAYEE_TREASURY
        :param gateway_url: Target gateway base URL (defaults to https://xrp.bristleconelogic.com)
        :param initial_drops_spent: Cumulative drops previously signed on this channel ID
        """
        self.wallet = wallet
        self.channel_id = channel_id.strip().upper()
        self.gateway_url = gateway_url.rstrip("/")
        self.cumulative_drops = initial_drops_spent
        self.client = httpx.Client(timeout=timeout)

    def _generate_signature(self, total_drops: int) -> str:
        """Constructs and signs the standard XRPL payment channel claim message."""
        prefix = b"CLM\0"
        channel_bytes = bytes.fromhex(self.channel_id)
        drops_bytes = total_drops.to_bytes(8, byteorder="big", signed=False)
        return sign(prefix + channel_bytes + drops_bytes, self.wallet.private_key)

    def call(self, endpoint_path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a request against Bristlecone. Automatically handles x402 challenges,
        increments cumulative drops, signs the claim, and returns the parsed response.
        """
        clean_path = "/" + endpoint_path.strip("/")
        url = f"{self.gateway_url}{clean_path}"

        # 1. Probe or initial unauthenticated call to retrieve cost challenge
        resp = self.client.post(url, json=payload)
        
        if resp.status_code == 200:
            return resp.json()

        if resp.status_code != 402:
            resp.raise_for_status()

        # 2. Parse required drops from challenge body
        challenge = resp.json()
        cost_drops = int(challenge.get("x402", {}).get("cost_drops", 1000))
        
        # 3. Advance cumulative drops counter
        self.cumulative_drops += cost_drops

        # 4. Sign off-chain voucher
        sig = self._generate_signature(self.cumulative_drops)

        headers = {
            "Content-Type": "application/json",
            "X-XRPL-Channel-ID": self.channel_id,
            "X-XRPL-Claim-Drops": str(self.cumulative_drops),
            "X-XRPL-Claim-Sig": sig,
            "X-XRPL-Public-Key": self.wallet.public_key,
        }

        # 5. Resubmit request with payment headers
        paid_resp = self.client.post(url, headers=headers, json=payload)
        paid_resp.raise_for_status()
        return paid_resp.json()

    def close(self):
        self.client.close()
