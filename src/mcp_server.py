"""
Bristlecone Logic - Radix MCP Tool Server
Exposes pre-socket hardened tools over Model Context Protocol (FastMCP)
gated by the Resin Tollbooth settlement pipeline.
"""
import json
import logging
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from src.gateway.tollbooth import TollboothGateway
from src.security.socket_guard import SocketGuard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bristlecone.radix.mcp")

mcp = FastMCP("bristlecone-logic-gateway")

# Resin Tollbooth Gatekeeper instance
resin_gateway = TollboothGateway(
    payee_address="0x1234567890abcdef1234567890abcdef12345678",
    price_base_units="1000",
    asset_id="USDC",
    network_id="5042002",
    rail="arc",
)


@mcp.tool(name="bristlecone_hardened_scrape")
def hardened_scrape(url: str, payment_signature: str = "", challenge_nonce: str = "") -> Dict[str, Any]:
    """
    Executes pre-socket DNS pinned and SSRF-hardened egress retrieval.
    Requires valid Resin Tollbooth payment challenge proof.
    """
    headers = {
        "payment-signature": payment_signature,
        "payment-challenge-id": challenge_nonce,
    }
    
    authorized, status_code, payload = resin_gateway.evaluate_request(headers)
    if not authorized:
        return {
            "status": "error",
            "code": status_code,
            "error": "Payment authorization required.",
            "challenge": payload if status_code == 402 else payload.get("error"),
        }

    # Execute hardened network egress via Bark SocketGuard
    try:
        guard = SocketGuard(url)
        content = guard.safe_fetch()
        return {
            "status": "success",
            "url": url,
            "content_bytes": len(content),
            "payload": content[:2000],  # Return initial sanitized text block
        }
    except Exception as e:
        logger.error(f"Egress failed: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    mcp.run()
