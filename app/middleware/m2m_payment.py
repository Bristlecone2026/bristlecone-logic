from app.core.metering import bypass_metering_var
import os
from decimal import Decimal
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.metering import redis_client

BASE_TREASURY_ADDRESS = os.getenv("BASE_TREASURY_ADDRESS", "0x1B4309CFdbCEee7618a7fBDc5b145691F9246D67").lower()
ARC_TREASURY_ADDRESS = os.getenv("ARC_TREASURY_ADDRESS", BASE_TREASURY_ADDRESS).lower()
BASE_USDC_CONTRACT = os.getenv("BASE_USDC_CONTRACT_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

# Invocation pricing in USD
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

        # Bypass EVM checks if already verified via Xylem (XRPL claim)
        if getattr(request.state, "payment_verified", False):
            return await call_next(request)

        # 1. Bearer API key authentication
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split("Bearer ", 1)[1].strip()
            credits = await redis_client.hget(f"tenant:{api_key}", "credits")
            if credits and int(credits) > 0:
                return await call_next(request)

        # 2. Multi-rail programmatic transaction verification
        tx_hash = (
            request.headers.get("X-Payment-TxHash")
            or request.headers.get("X-Arc-TxHash")
            or request.headers.get("X-Base-TxHash")
        )
        if tx_hash:
            tx_clean = tx_hash.strip().lower()
            is_confirmed = await redis_client.get(f"tx_confirmed:{tx_clean}")
            if is_confirmed:
                bypass_metering_var.set(True)
                return await call_next(request)

        # 3. Calculate atomic units for both settlement rails
        price_usd = TOOL_PRICING_USD.get(path, Decimal("0.002"))
        base_atomic = str(int(price_usd * Decimal("1000000")))              # 6 decimals (Base ERC-20)
        arc_atomic = str(int(price_usd * Decimal("1000000000000000000")))   # 18 decimals (Arc Native Gas)

        # 4. Construct Dual-Rail x402 Challenge Payload
        x402_payload = {
            "status": 402,
            "error": "Payment Required",
            "protocol": "x402",
            "accepts": [
                {
                    "network": "eip155:5042",
                    "scheme": "exact",
                    "asset": "native",
                    "payTo": ARC_TREASURY_ADDRESS,
                    "amount": arc_atomic,
                    "decimals": 18,
                    "currency": "USDC"
                },
                {
                    "network": "eip155:8453",
                    "scheme": "exact",
                    "asset": BASE_USDC_CONTRACT,
                    "payTo": BASE_TREASURY_ADDRESS,
                    "amount": base_atomic,
                    "decimals": 6,
                    "currency": "USDC"
                }
            ],
            # Legacy backward-compatibility block for single-rail v1 agents
            "x402": {
                "version": "1.0",
                "scheme": "exact",
                "network": "eip155:8453",
                "asset": BASE_USDC_CONTRACT,
                "payee": BASE_TREASURY_ADDRESS,
                "amount": base_atomic,
                "amount_usd": str(price_usd),
                "currency": "USDC"
            },
            "metadata": {
                "provider": {"name": "Bristlecone Logic", "description": "Deterministic sovereign agent tooling"},
                "description": f"Deterministic execution of {path}",
                "path": path,
                "method": "POST"
            },
            "instructions": {
                "autonomous": "Submit transfer on Arc L1 (eip155:5042) or Base L2 (eip155:8453), then resend request with header 'X-Payment-TxHash: <tx_hash>'.",
                "developer": "Acquire API key at https://bristleconelogic.com and supply header 'Authorization: Bearer <key>'."
            }
        }

        # 5. Issue HTTP 402 Response with Dual Headers
        response = JSONResponse(status_code=402, content=x402_payload)
        response.headers["WWW-Authenticate"] = 'x402 realm="bristlecone-tollbooth"'
        response.headers["X-Payment-Protocol"] = "x402"
        response.headers["PAYMENT-REQUIRED"] = (
            f'exact; network="eip155:5042"; asset="native"; payee="{ARC_TREASURY_ADDRESS}"; amount="{arc_atomic}", '
            f'exact; network="eip155:8453"; asset="{BASE_USDC_CONTRACT}"; payee="{BASE_TREASURY_ADDRESS}"; amount="{base_atomic}"'
        )
        return response
