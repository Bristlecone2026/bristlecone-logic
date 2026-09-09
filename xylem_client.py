#!/usr/bin/env python3
"""
Bristlecone Xylem M2M Reference Client
Handles automatic discovery, channel claim signing, and request streaming.
"""
import sys
import httpx
from decimal import Decimal
from xrpl.wallet import Wallet
from xrpl.core.keypairs import sign

BASE_URL = "https://xrp.bristleconelogic.com"

class XylemClient:
    def __init__(self, wallet_seed: str, channel_id: str):
        self.wallet = Wallet.from_seed(wallet_seed)
        self.channel_id = channel_id
        self.cumulative_drops = 0

    def sign_claim(self, drops_to_authorize: int) -> str:
        """Constructs the XRPL binary claim wire format: CLM\0 + ChannelID + Drops (uint64_be)"""
        clm_prefix = bytes.fromhex("434C4D00")
        channel_bytes = bytes.fromhex(self.channel_id)
        amount_bytes = drops_to_authorize.to_bytes(8, byteorder="big")
        claim_bytes = clm_prefix + channel_bytes + amount_bytes
        return sign(claim_bytes, self.wallet.private_key)

    def call_tool(self, endpoint: str, payload: dict, cost_drops: int) -> dict:
        self.cumulative_drops += cost_drops
        sig = self.sign_claim(self.cumulative_drops)

        headers = {
            "X-XRPL-Channel-ID": self.channel_id,
            "X-XRPL-Claim-Drops": str(self.cumulative_drops),
            "X-XRPL-Claim-Sig": sig,
            "X-XRPL-Public-Key": self.wallet.public_key,
            "Content-Type": "application/json"
        }

        url = f"{BASE_URL}{endpoint}"
        with httpx.Client() as client:
            resp = client.post(url, json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 402:
                raise RuntimeError(f"Payment rejected: {resp.text}")
            else:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    print("Xylem Client module initialized. Ready for agent integration.")
