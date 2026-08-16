import json
import os
from decimal import Decimal
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from app.database import AsyncSessionLocal
import redis.asyncio as aioredis

XRPL_TREASURY_ADDRESS = os.getenv("XRPL_TREASURY_ADDRESS", "rnMmqUJ17LXS4Jv68j4oUinuDNbucoR6a4")
XRP_USD_PRICE = Decimal(os.getenv("XRP_USD_PRICE", "0.60"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Standard per-invocation tool pricing for unauthenticated M2M agent calls
TOOL_PRICING_USD = {
    "/api/v1/tools/json-repair": Decimal("0.002000"),
    "/api/v1/tools/web-scrape": Decimal("0.005000"),
    "/api/v1/tools/ast-audit": Decimal("0.004000"),
}

class M2MPaymentMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Only intercept tool endpoints
        if not path.startswith("/api/v1/tools"):
            return await call_next(request)

        # If standard Bearer API key is present, let standard auth & balance governor handle it
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return await call_next(request)

        # Check for autonomous transaction proof headers
        tx_hash = request.headers.get("X-XRPL-TxHash")
        invoice_id_str = request.headers.get("X-Invoice-Id")

        price_usd = TOOL_PRICING_USD.get(path, Decimal("0.002000"))
        price_xrp = (price_usd / XRP_USD_PRICE).quantize(Decimal("0.000001"))

        # Case A: Agent provided an on-chain transaction hash for settlement
        if tx_hash and invoice_id_str:
            try:
                invoice_id = int(invoice_id_str)
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "Invalid X-Invoice-Id format."})

            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    text("SELECT id, status, amount_usd FROM m2m_invoices WHERE id = :inv_id AND tx_hash = :tx_hash"),
                    {"inv_id": invoice_id, "tx_hash": tx_hash}
                )
                invoice = res.first()

                if invoice and invoice[1] == "settled":
                    # Payment confirmed on XRPL; proceed to tool execution
                    return await call_next(request)
                
                # Check if deposit listener already confirmed it in tenant_deposits
                dep_res = await session.execute(
                    text("SELECT id FROM tenant_deposits WHERE tx_hash = :tx_hash AND status = 'confirmed'"),
                    {"tx_hash": tx_hash}
                )
                if dep_res.first():
                    # Mark invoice settled and proceed
                    await session.execute(
                        text("UPDATE m2m_invoices SET status = 'settled', tx_hash = :tx_hash WHERE id = :inv_id"),
                        {"tx_hash": tx_hash, "inv_id": invoice_id}
                    )
                    await session.commit()
                    return await call_next(request)

            return JSONResponse(
                status_code=402,
                content={
                    "error": "Payment Pending or Unconfirmed",
                    "message": "Transaction hash has not yet been validated by XRPL ledger close.",
                    "tx_hash": tx_hash,
                    "invoice_id": str(invoice_id)
                }
            )

        # Case B: Unauthenticated agent request - issue HTTP 402 invoice
        async with AsyncSessionLocal() as session:
            # Generate unique ephemeral DestinationTag for this invoice
            tag_res = await session.execute(text("SELECT nextval('xrpl_destination_tag_seq')"))
            dynamic_tag = tag_res.scalar()

            inv_res = await session.execute(
                text("""
                    INSERT INTO m2m_invoices (destination_tag, amount_usd, amount_xrp, endpoint, status)
                    VALUES (:tag, :usd, :xrp, :ep, 'pending')
                    RETURNING id;
                """),
                {
                    "tag": dynamic_tag,
                    "usd": price_usd,
                    "xrp": price_xrp,
                    "ep": path
                }
            )
            invoice_id = inv_res.scalar()
            await session.commit()

        headers = {
            "X-Payment-Required": "true",
            "X-Payment-Network": "XRPL",
            "X-Receiver-Address": XRPL_TREASURY_ADDRESS,
            "X-Destination-Tag": str(dynamic_tag),
            "X-Required-Amount-XRP": str(price_xrp),
            "X-Required-Amount-USD": str(price_usd),
            "X-Invoice-Id": str(invoice_id),
            "X-Invoice-Expires-In": "600s"
        }

        return JSONResponse(
            status_code=402,
            headers=headers,
            content={
                "status": "Payment Required",
                "message": "Autonomous M2M tool execution requires direct micro-settlement.",
                "invoice": {
                    "invoice_id": str(invoice_id),
                    "network": "XRPL",
                    "receiver_address": XRPL_TREASURY_ADDRESS,
                    "destination_tag": dynamic_tag,
                    "amount_xrp": str(price_xrp),
                    "amount_usd": str(price_usd),
                    "expires_in_seconds": 600
                },
                "instructions": "Send exact XRP to receiver_address with destination_tag, then retry request with 'X-XRPL-TxHash' and 'X-Invoice-Id' headers."
            }
        )
