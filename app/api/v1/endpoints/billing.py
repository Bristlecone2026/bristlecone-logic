import os
import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.billing import TenantBalance
from app.schemas.billing import WebhookTopUpPayload

logger = logging.getLogger(__name__)
router = APIRouter()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "bl_webhook_secret_2026")

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_payment_webhook(
    payload: WebhookTopUpPayload,
    x_webhook_secret: str = Header(..., alias="X-Webhook-Secret"),
    db: AsyncSession = Depends(get_db)
):
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook secret header"
        )

    if payload.event_type != "payment.succeeded":
        return {"status": "ignored", "reason": f"Unhandled event type: {payload.event_type}"}

    tenant_id_str = payload.tenant_id
    amount = payload.amount_usd

    # Row-level pessimistic locking to handle concurrent webhook callbacks cleanly
    stmt = select(TenantBalance).where(
        TenantBalance.tenant_id == tenant_id_str
    ).with_for_update()
    
    result = await db.execute(stmt)
    tenant_balance = result.scalars().first()

    if not tenant_balance:
        tenant_balance = TenantBalance(
            tenant_id=tenant_id_str,
            balance_usd=amount
        )
        db.add(tenant_balance)
    else:
        tenant_balance.balance_usd += amount

    await db.commit()
    await db.refresh(tenant_balance)

    logger.info(f"Top-up succeeded: tenant {tenant_id_str} credited +${amount}")

    return {
        "status": "success",
        "tenant_id": tenant_id_str,
        "amount_added": str(amount),
        "new_balance_usd": str(tenant_balance.balance_usd),
        "transaction_id": payload.transaction_id
    }
