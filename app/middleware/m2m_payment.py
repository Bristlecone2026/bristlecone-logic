import os
from decimal import Decimal
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.metering import redis_client

BASE_TREASURY_ADDRESS = os.getenv("BASE_TREASURY_ADDRESS", "0xa17c8c3005698bc4ea6406a00387445e1d30c35f").lower()
BASE_USDC_CONTRACT = os.getenv("BASE_USDC_CONTRACT_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

# Cost in USD per invocation ($0.002 = 2,000 atomic units of 6-decimal USDC)
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

        # 1. Bearer API key authentication
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split("Bearer ", 1)[1].strip()
            credits = await redis_client.hget(f"tenant:{api_key}", "credits")
            if credits and int(credits) > 0:
                return await call_next(request)

        # 2. Programmatic transaction verification for autonomous agents
        tx_hash = request.headers.get("X-Payment-TxHash") or request.headers.get("X-Base-TxHash")
        if tx_hash:
            is_confirmed = await redis_client.get(f"tx_confirmed:{tx_hash.lower()}")
            if is_confirmed:
                return await call_next(request)

        # 3. Issue RFC-compliant x402 Challenge
        price_usd = TOOL_PRICING_USD.get(path, Decimal("0.002"))
        atomic_units = str(int(price_usd * Decimal("1000000")))

        x402_payload = {
            "status": 402,
            "error": "Payment Required",
            "protocol": "x402",
            "x402": {
                "version": "1.0",
                "scheme": "exact",
                "network": "eip155:8453",
                "asset": BASE_USDC_CONTRACT,
                "payee": BASE_TREASURY_ADDRESS,
                "amount": atomic_units,
                "amount_usd": str(price_usd),
                "currency": "USDC"
            },
            "instructions": {
                "autonomous": "Submit transfer on Base L2, then resend request with header 'X-Payment-TxHash: <tx_hash>'.",
                "developer": "Acquire API key at https://bristleconelogic.com and supply header 'Authorization: Bearer <key>'."
            }
        }

        response = JSONResponse(status_code=402, content=x402_payload)
        response.headers["PAYMENT-REQUIRED"] = f'exact; network="eip155:8453"; asset="{BASE_USDC_CONTRACT}"; payee="{BASE_TREASURY_ADDRESS}"; amount="{atomic_units}"'
        response.headers["X-Payment-Protocol"] = "x402"
        return response
