import os
import logging
from typing import Tuple, Optional
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models.requests import ChannelVerify
from app.core.metering import redis_client

logger = logging.getLogger("xylem.verifier")

XRPL_RPC_URL = os.getenv("XRPL_RPC_URL", "https://s1.ripple.com:51234")
xrpl_client = AsyncJsonRpcClient(XRPL_RPC_URL)


async def verify_and_consume_claim(
    channel_id: str,
    claim_drops: int,
    signature: str,
    public_key: str,
    required_drops: int
) -> Tuple[bool, Optional[str]]:
    channel_id = channel_id.upper().strip()
    redis_key = f"xrpl:channel:{channel_id}:claimed_drops"

    # 1. Delta metering check against Redis
    prev_claimed_raw = await redis_client.get(redis_key)
    prev_claimed = int(prev_claimed_raw) if prev_claimed_raw else 0

    delta = claim_drops - prev_claimed
    if delta < required_drops:
        return False, f"Insufficient claim delta. Required: {required_drops} drops, Authorized delta: {delta} drops"

    # 2. Async cryptographic verification against XRPL node
    try:
        req = ChannelVerify(
            channel_id=channel_id,
            amount=str(claim_drops),
            signature=signature,
            public_key=public_key,
        )
        response = await xrpl_client.request(req)

        if not response.is_successful():
            error_msg = response.result.get("error_message", "channel_verify RPC error")
            return False, f"XRPL verification failed: {error_msg}"

        if not response.result.get("signature_verified", False):
            return False, "Cryptographic signature mismatch for specified channel, amount, and public key"

    except Exception as e:
        logger.error(f"Error calling XRPL channel_verify: {e}")
        return False, "Failed connecting to ledger verification node"

    # 3. Commit state to Redis
    await redis_client.set(redis_key, claim_drops)
    await redis_client.hset(
        f"xrpl:channel:{channel_id}:latest_claim",
        mapping={
            "amount_drops": str(claim_drops),
            "signature": signature,
            "public_key": public_key,
        }
    )

    return True, None
