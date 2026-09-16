import os
from decimal import Decimal
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.metering import redis_client
from app.services.xrpl_verifier import verify_xrpl_tx, get_required_xrp_drops

BASE_TREASURY_ADDRESS = os.getenv("BASE_TREASURY_ADDRESS", "0xa17c8c3005698bc4ea6406a00387445e1d30c35f").lower()
BASE_USDC_CONTRACT = os.getenv("BASE_USDC_CONTRACT_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
XRPL_TREASURY_ADDRESS = os.getenv("XRPL_TREASURY_ADDRESS", "rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD")

# Cost in USD per invocation
TOOL_PRICING_USD = {
    "/tools/extract-web": Decimal("0.005"),
    "/tools/repair-json": Decimal("0.002"),
    "/tools/eval-expression": Decimal("0.002"),
    "/tools/audit-dns": Decimal("0.002"),
    "/tools/chunk-text": Decimal("0.002"),
    "/tools/validate-schema": Decimal("0.002"),
}


class M2MPaymentMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only gate operational tool execution routes
        if not path.startswith("/tools/"):
            return await call_next(request)

        price_usd = TOOL_PRICING_USD.get(path, Decimal("0.002"))

        # 1. Bearer API key authentication
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split("Bearer ", 1)[1].strip()
            credits = await redis_client.hget(f"tenant:{api_key}", "credits")
            if credits and int(credits) > 0:
                await redis_client.hincrby(f"tenant:{api_key}", "credits", -1)
                return await call_next(request)

        # 2. Native XRPL On-Chain Payment Verification
        xrpl_tx_hash = request.headers.get("X-XRPL-Tx-Hash") or request.headers.get("X-XRPL-TxHash")
        if xrpl_tx_hash:
            is_valid, reason = await verify_xrpl_tx(redis_client, xrpl_tx_hash, price_usd)
            if is_valid:
                return await call_next(request)
            return JSONResponse(
                status_code=402,
                content={
                    "status": 402,
                    "error": "XRPL Payment Verification Failed",
                    "reason": reason,
                    "tx_hash": xrpl_tx_hash
                }
            )

        # 3. Base L2 EVM Transaction Verification
        base_tx_hash = request.headers.get("X-Payment-TxHash") or request.headers.get("X-Base-TxHash")
        if base_tx_hash:
            is_confirmed = await redis_client.get(f"tx_confirmed:{base_tx_hash.lower()}")
            if is_confirmed:
                return await call_next(request)

        # 4. Issue Dual-Rail RFC-compliant x402 Challenge
        usdc_atomic_units = str(int(price_usd * Decimal("1000000")))
        xrp_drops = str(get_required_xrp_drops(price_usd))

        x402_payload = {
            "status": 402,
            "error": "Payment Required",
            "protocol": "x402",
            "pricing_usd": str(price_usd),
            "rails": {
                "xrpl": {
                    "network": "xrpl:mainnet",
                    "asset": "XRP",
                    "payee": XRPL_TREASURY_ADDRESS,
                    "drops": xrp_drops,
                    "header_format": "X-XRPL-Tx-Hash: <64_char_hex_hash>"
                },
                "base_l2": {
                    "network": "eip155:8453",
                    "asset": BASE_USDC_CONTRACT,
                    "payee": BASE_TREASURY_ADDRESS,
                    "amount": usdc_atomic_units,
                    "currency": "USDC",
                    "header_format": "X-Payment-TxHash: <0x_hex_hash>"
                }
            },
            "instructions": {
                "xrpl_autonomous": f"Send {xrp_drops} drops to {XRPL_TREASURY_ADDRESS} on XRPL, then resend request with header 'X-XRPL-Tx-Hash: <tx_hash>'.",
                "base_autonomous": f"Send {usdc_atomic_units} atomic units USDC to {BASE_TREASURY_ADDRESS} on Base, then resend request with header 'X-Payment-TxHash: <tx_hash>'.",
                "developer": "Acquire API key at https://bristleconelogic.com and supply header 'Authorization: Bearer <key>'."
            }
        }

        response = JSONResponse(status_code=402, content=x402_payload)
        response.headers["PAYMENT-REQUIRED"] = (
            f'exact; network="xrpl:mainnet"; asset="XRP"; payee="{XRPL_TREASURY_ADDRESS}"; amount="{xrp_drops}", '
            f'exact; network="eip155:8453"; asset="{BASE_USDC_CONTRACT}"; payee="{BASE_TREASURY_ADDRESS}"; amount="{usdc_atomic_units}"'
        )
        response.headers["X-Payment-Protocol"] = "x402"
        return response
