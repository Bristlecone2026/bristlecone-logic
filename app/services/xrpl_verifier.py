"""
Bristlecone Logic - Native XRPL On-Chain Settlement Verifier
Validates tx finality, destination match, and unspent status against XRPL JSON-RPC.
"""

import os
import logging
from decimal import Decimal
from typing import Tuple, Optional
import httpx

logger = logging.getLogger("bristlecone.xrpl_verifier")

XRPL_JSON_RPC_URL = os.getenv("XRPL_JSON_RPC_URL", "https://xrplcluster.com")
XRPL_TREASURY_ADDRESS = os.getenv("XRPL_TREASURY_ADDRESS", "rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD")
XRP_USD_PRICE = Decimal(os.getenv("XRP_USD_PRICE", "0.60"))


def get_required_xrp_drops(price_usd: Decimal) -> int:
    """Calculates required XRP drops based on current USD tool pricing."""
    xrp_needed = price_usd / XRP_USD_PRICE
    return int((xrp_needed * Decimal("1000000")).quantize(Decimal("1")))


async def verify_xrpl_tx(
    redis_client,
    tx_hash: str,
    required_usd: Decimal
) -> Tuple[bool, Optional[str]]:
    """
    Validates that an XRPL transaction:
    1. Has not already been consumed (replay / double-spend prevention).
    2. Is validated on ledger with tesSUCCESS.
    3. Paid at least the required drops/RLUSD to XRPL_TREASURY_ADDRESS.
    """
    clean_hash = tx_hash.strip().upper()
    if len(clean_hash) != 64:
        return False, "Invalid XRPL transaction hash length"

    spent_key = f"xrpl_spent:{clean_hash}"

    # 1. Double-spend check via Redis
    already_spent = await redis_client.get(spent_key)
    if already_spent:
        return False, "Transaction already redeemed"

    # 2. Query XRPL JSON-RPC for transaction metadata
    payload = {
        "method": "tx",
        "params": [
            {
                "transaction": clean_hash,
                "binary": False
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(XRPL_JSON_RPC_URL, json=payload)
            if resp.status_code != 200:
                return False, f"XRPL RPC error ({resp.status_code})"
            data = resp.json()
    except Exception as exc:
        logger.error(f"XRPL RPC connection failed: {exc}")
        return False, "XRPL RPC unreachable"

    result = data.get("result", {})
    if result.get("status") != "success" or not result.get("validated", False):
        return False, "Transaction not validated on ledger"

    meta = result.get("meta") or result.get("metaData", {})
    if meta.get("TransactionResult") != "tesSUCCESS":
        return False, f"Transaction failed on-chain: {meta.get('TransactionResult')}"

    # Handle both API v1 and v2 object shapes
    tx_data = result.get("tx_json") if "tx_json" in result else result
    if tx_data.get("TransactionType") != "Payment":
        return False, "Transaction is not a Payment"

    if tx_data.get("Destination") != XRPL_TREASURY_ADDRESS:
        return False, f"Destination does not match treasury ({tx_data.get('Destination')})"

    # 3. Value check: evaluate delivered_amount or Amount
    delivered = meta.get("delivered_amount") or tx_data.get("Amount")
    required_drops = get_required_xrp_drops(required_usd)

    if isinstance(delivered, str):  # Native XRP in drops
        drops_paid = int(delivered)
        if drops_paid < required_drops:
            return False, f"Insufficient XRP: received {drops_paid} drops, required {required_drops}"
    elif isinstance(delivered, dict):  # Issued Currency (RLUSD, USD, USDC)
        currency = delivered.get("currency")
        val = Decimal(str(delivered.get("value", "0")))
        if currency in ["RLUSD", "USD", "USDC"]:
            if val < required_usd:
                return False, f"Insufficient {currency}: received {val}, required {required_usd}"
        else:
            return False, f"Unsupported issued currency: {currency}"
    else:
        return False, "Unrecognized transaction amount format"

    # 4. Mark transaction as spent with a 30-day TTL in Redis
    await redis_client.set(spent_key, "1", ex=2592000)
    logger.info(f"XRPL payment verified: {clean_hash} for {required_usd} USD")
    return True, None
