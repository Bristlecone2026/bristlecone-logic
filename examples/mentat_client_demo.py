"""
Bristlecone Logic - External Consumer Agent Demo
Agent: Mentat-Drago-Roget
Cluster: Grove-Longaeva
Orchestrator: Erasmus

Demonstrates an external autonomous agent negotiating an HTTP 402 challenge,
dispatching an Arc L1 settlement signature, and retrieving pre-socket secured
egress data from the Resin Tollbooth Gateway.
"""
import json
import logging
import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gateway.tollbooth import TollboothGateway
from src.security.socket_guard import SocketGuard

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bristlecone.client.drago_roget")


class DragoRogetClient:
    """
    Client agent runtime for Mentat-Drago-Roget.
    Handles automated 402 payment challenge parsing and response construction.
    """

    def __init__(self, agent_id: str = "Mentat-Drago-Roget"):
        self.agent_id = agent_id
        # Connect to local Tollbooth Gateway instance
        self.gateway = TollboothGateway(
            payee_address="0x1234567890abcdef1234567890abcdef12345678",
            price_base_units="1000",
            asset_id="USDC",
            network_id="5042002",
            rail="arc",
        )

    def execute_request(self, target_url: str):
        logger.info(f"[{self.agent_id}] Initiating egress extraction request for: {target_url}")

        # Step 1: Unauthenticated request (Egress negotiation)
        initial_headers = {
            "x-bristlecone-agent": self.agent_id,
            "x-bristlecone-grove": "Grove-Longaeva",
            "x-bristlecone-orchestrator": "Erasmus",
        }
        authorized, status_code, response_data = self.gateway.evaluate_request(initial_headers)

        if status_code != 402:
            logger.error(f"Unexpected initial response: {status_code}")
            return

        challenge = json.loads(response_data["Payment-Required"])
        nonce = challenge["nonce"]
        rail = challenge["rail"]
        price = challenge["amount"]
        logger.info(
            f"[{self.agent_id}] HTTP 402 Challenge received. "
            f"Rail: {rail} | Nonce: {nonce} | Price: {price} base units"
        )

        # Step 2: Sign settlement proof (Simulating local keystore / agent wallet)
        signature = "0x" + "b" * 130
        logger.info(f"[{self.agent_id}] Settlement authorization signed for Arc L1 (Chain ID: 5042002).")

        # Step 3: Present payment proof
        auth_headers = {
            "x-bristlecone-agent": self.agent_id,
            "x-bristlecone-grove": "Grove-Longaeva",
            "x-bristlecone-orchestrator": "Erasmus",
            "Payment-Signature": signature,
            "Payment-Challenge-Id": nonce,
        }
        authorized, status_code, auth_response = self.gateway.evaluate_request(auth_headers)

        if not authorized or status_code != 200:
            logger.error(f"[{self.agent_id}] Payment verification failed: {auth_response}")
            return

        logger.info(f"[{self.agent_id}] HTTP 200 Authorized. Execution clearance granted by Resin Tollbooth.")

        # Step 4: Secure Tool Execution via SocketGuard
        logger.info(f"[{self.agent_id}] Executing safe fetch through Bark SocketGuard...")
        try:
            guard = SocketGuard(target_url)
            result = guard.safe_fetch()
            logger.info(f"[{self.agent_id}] Retrieval complete. Received {len(result)} bytes safely.")
            print("\n--- EXTRACTED PAYLOAD SAMPLE ---")
            print(result[:300] + ("..." if len(result) > 300 else ""))
            print("--------------------------------\n")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Bark SocketGuard halted execution: {e}")


if __name__ == "__main__":
    demo_client = DragoRogetClient()
    # Execute against a safe public target
    demo_client.execute_request("https://httpbin.org/get")
