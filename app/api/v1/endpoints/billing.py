from fastapi import APIRouter, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_tenant_context
from app.services.notifications import set_tenant_webhook, get_tenant_webhook

router = APIRouter()

class WebhookConfigRequest(BaseModel):
    webhook_url: str

@router.get("/balance")
async def get_balance(
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = tenant_context["tenant_id"]
    query = text("SELECT balance_usd FROM tenant_balances WHERE tenant_id = :tenant_id")
    result = await db.execute(query, {"tenant_id": tenant_id})
    row = result.fetchone()
    balance = float(row.balance_usd) if row else 100.0

    return {
        "tenant_id": tenant_id,
        "balance_usd": balance
    }

@router.post("/webhook")
async def configure_webhook(
    payload: WebhookConfigRequest,
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = tenant_context["tenant_id"]
    await set_tenant_webhook(tenant_id, payload.webhook_url, db)
    return {
        "status": "CONFIGURED",
        "tenant_id": tenant_id,
        "webhook_url": payload.webhook_url
    }

@router.get("/webhook")
async def fetch_webhook(
    tenant_context: dict = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = tenant_context["tenant_id"]
    url = await get_tenant_webhook(tenant_id, db)
    return {
        "tenant_id": tenant_id,
        "webhook_url": url
    }
