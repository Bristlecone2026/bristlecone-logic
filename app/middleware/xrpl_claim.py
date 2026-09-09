import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.layer4_ledgers.xylem_verifier import verify_and_consume_claim
from app.core.metering import bypass_metering_var

XRPL_TREASURY_ADDRESS = os.getenv("XRPL_TREASURY_ADDRESS", "rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD")

TOOL_PRICING_DROPS = {
    "/tools/repair-json": 1000,
    "/tools/xrpl/orderbook-depth": 2000,
    "/tools/xrpl/amm-arb-quote": 5000,
    "/tools/xrpl/ticket-pool": 1000,
}


class XRPLClaimMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not path.startswith("/tools/"):
            return await call_next(request)

        channel_id = request.headers.get("X-XRPL-Channel-ID")
        claim_drops_raw = request.headers.get("X-XRPL-Claim-Drops")
        signature = request.headers.get("X-XRPL-Claim-Sig")
        public_key = request.headers.get("X-XRPL-Public-Key")

        # Process Xylem payment channel claim if headers are present
        if channel_id and claim_drops_raw and signature and public_key:
            try:
                claim_drops = int(claim_drops_raw)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "X-XRPL-Claim-Drops header must be an integer"}
                )

            required_drops = TOOL_PRICING_DROPS.get(path, 2000)
            valid, err = await verify_and_consume_claim(
                channel_id=channel_id,
                claim_drops=claim_drops,
                signature=signature,
                public_key=public_key,
                required_drops=required_drops
            )

            if valid:
                # 1. Flag request state for downstream middlewares (Heartwood)
                request.state.payment_verified = True
                request.state.payment_rail = "xylem"

                # 2. Bypass route-level trial credit deduction
                bypass_metering_var.set(True)

                # 3. Inject tenant identity into ASGI scope for logging & telemetry
                scoped_channel = channel_id[:16]
                headers = list(request.scope.get("headers", []))
                headers = [(k, v) for k, v in headers if k.lower() != b"x-tenant-id"]
                headers.append((b"x-tenant-id", f"xylem_{scoped_channel}".encode()))
                request.scope["headers"] = headers

                return await call_next(request)
            else:
                return JSONResponse(status_code=402, content={"error": "Payment Required", "detail": err})

        # Whitelist discovery, openapi, and documentation endpoints
        if path.startswith("/.well-known") or path in ["/docs", "/openapi.json", "/redoc", "/api/v1/health"]:
            return await call_next(request)

        # Check if caller is hitting Xylem domain or prefix without claim headers
        host = request.headers.get("host", "").lower()
        if host.startswith("xrp.") or "/xrpl/" in path:
            required_drops = TOOL_PRICING_DROPS.get(path, 2000)
            x402_payload = {
                "status": 402,
                "error": "Payment Required",
                "protocol": "x402",
                "x402": {
                    "version": "1.0",
                    "scheme": "payment-channel",
                    "network": "xrpl:mainnet",
                    "asset": "XRP",
                    "payee": XRPL_TREASURY_ADDRESS,
                    "cost_drops": str(required_drops),
                    "cost_xrp": str(required_drops / 1_000_000),
                },
                "instructions": {
                    "autonomous": "Open an XRPL PaymentChannel to payee, sign claim for cumulative drops, and submit headers: X-XRPL-Channel-ID, X-XRPL-Claim-Drops, X-XRPL-Claim-Sig, X-XRPL-Public-Key.",
                    "developer": "Acquire API key at https://bristleconelogic.com or supply Bearer token."
                }
            }
            response = JSONResponse(status_code=402, content=x402_payload)
            response.headers["PAYMENT-REQUIRED"] = f'payment-channel; network="xrpl:mainnet"; asset="XRP"; payee="{XRPL_TREASURY_ADDRESS}"; drops="{required_drops}"'
            response.headers["X-Payment-Protocol"] = "x402"
            return response

        return await call_next(request)
