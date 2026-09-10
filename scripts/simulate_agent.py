import secrets
import json
import httpx
from xrpl.wallet import Wallet
from xrpl.core.keypairs import sign

import os
API_HOST = os.getenv("API_HOST", "api")
API_URL = f"http://{API_HOST}:8000/tools/repair-json"
HOST_HEADER = "xrp.bristleconelogic.com"
TEST_CHANNEL_ID = secrets.token_hex(32).upper()

def create_claim_signature(channel_id_hex: str, drops: int, private_key: str) -> str:
    """Builds the canonical 44-byte XRPL PaymentChannel claim signature."""
    prefix = b"CLM\0"
    channel_bytes = bytes.fromhex(channel_id_hex)
    drops_bytes = drops.to_bytes(8, byteorder="big", signed=False)
    message = prefix + channel_bytes + drops_bytes
    return sign(message, private_key)

def main():
    agent_wallet = Wallet.create()
    print(f"[1] Agent initialized. Classic Address: {agent_wallet.classic_address}")
    print(f"    Public Key: {agent_wallet.public_key}")

    test_payload = {"raw_json": '{"service": "bristlecone", "status": "active",'}

    # 1. Probe endpoint without headers (Expect 402)
    print("\n[2] Probing endpoint without payment headers...")
    with httpx.Client(timeout=10.0) as client:
        initial_resp = client.post(
            API_URL,
            headers={"Host": HOST_HEADER, "Content-Type": "application/json"},
            json=test_payload
        )

    print(f"    Status: {initial_resp.status_code}")
    challenge = initial_resp.json()
    cost_drops = int(challenge.get("x402", {}).get("cost_drops", 1000))
    print(f"    Received 402 Challenge: Cost = {cost_drops} drops to {challenge.get('x402', {}).get('payee')}")

    # 2. Generate claim signature
    print(f"\n[3] Generating claim signature for {cost_drops} drops on channel...")
    signature = create_claim_signature(TEST_CHANNEL_ID, cost_drops, agent_wallet.private_key)
    print(f"    Signature: {signature}")

    # 3. Dispatch authenticated request
    claim_headers = {
        "Host": HOST_HEADER,
        "Content-Type": "application/json",
        "X-XRPL-Channel-ID": TEST_CHANNEL_ID,
        "X-XRPL-Claim-Drops": str(cost_drops),
        "X-XRPL-Claim-Sig": signature,
        "X-XRPL-Public-Key": agent_wallet.public_key,
    }

    print("\n[4] Submitting request with payment claim headers...")
    with httpx.Client(timeout=10.0) as client:
        paid_resp = client.post(API_URL, headers=claim_headers, json=test_payload)

    print(f"    Status: {paid_resp.status_code}")
    print(f"    Response Body: {json.dumps(paid_resp.json(), indent=2)}")

if __name__ == "__main__":
    main()
