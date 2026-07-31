import logging
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("bristlecone.notifications")

LOW_BALANCE_THRESHOLD_USD = 5.00

async def ensure_notification_schema(db: AsyncSession):
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS tenant_notifications (
            tenant_id VARCHAR(255) PRIMARY KEY,
            webhook_url VARCHAR(512) NULL,
            low_balance_notified BOOLEAN DEFAULT FALSE,
            last_notified_at TIMESTAMP WITH TIME ZONE NULL
        )
    """))
    await db.commit()

async def set_tenant_webhook(tenant_id: str, webhook_url: str, db: AsyncSession):
    await ensure_notification_schema(db)
    query = text("""
        INSERT INTO tenant_notifications (tenant_id, webhook_url)
        VALUES (:tenant_id, :webhook_url)
        ON CONFLICT (tenant_id) DO UPDATE
        SET webhook_url = EXCLUDED.webhook_url
    """)
    await db.execute(query, {"tenant_id": tenant_id, "webhook_url": webhook_url})
    await db.commit()

async def get_tenant_webhook(tenant_id: str, db: AsyncSession) -> str:
    await ensure_notification_schema(db)
    query = text("SELECT webhook_url FROM tenant_notifications WHERE tenant_id = :tenant_id")
    result = await db.execute(query, {"tenant_id": tenant_id})
    row = result.fetchone()
    return row.webhook_url if row else None

async def check_and_notify_low_balance(tenant_id: str, current_balance: float, db: AsyncSession):
    await ensure_notification_schema(db)

    # Fetch notification configuration
    res = await db.execute(
        text("SELECT webhook_url, low_balance_notified FROM tenant_notifications WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id}
    )
    row = res.fetchone()

    # Case A: Balance recovered above threshold -> Reset notification trigger state
    if current_balance >= LOW_BALANCE_THRESHOLD_USD:
        if row and row.low_balance_notified:
            await db.execute(
                text("UPDATE tenant_notifications SET low_balance_notified = FALSE WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id}
            )
            await db.commit()
            logger.info(f"Tenant {tenant_id} balance recovered above threshold (${current_balance:.2f}). Trigger reset.")
        return

    # Case B: Balance dropped under threshold ($5.00)
    if current_balance < LOW_BALANCE_THRESHOLD_USD:
        if row and row.low_balance_notified:
            # Alert already dispatched for this breach session
            return

        webhook_url = row.webhook_url if row else None

        logger.warning(f"[ALERT] Tenant {tenant_id} balance dropped to ${current_balance:.4f} (Under threshold of ${LOW_BALANCE_THRESHOLD_USD:.2f})")

        # Mark as notified atomically
        await db.execute(text("""
            INSERT INTO tenant_notifications (tenant_id, low_balance_notified, last_notified_at)
            VALUES (:tenant_id, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO UPDATE
            SET low_balance_notified = TRUE, last_notified_at = CURRENT_TIMESTAMP
        """), {"tenant_id": tenant_id})
        await db.commit()

        # Fire async HTTP webhook if configured
        if webhook_url:
            payload = {
                "event": "tenant.low_balance_warning",
                "tenant_id": tenant_id,
                "current_balance_usd": round(current_balance, 4),
                "threshold_usd": LOW_BALANCE_THRESHOLD_USD,
                "message": f"Tenant credit balance is now ${current_balance:.4f} USD, falling below the ${LOW_BALANCE_THRESHOLD_USD:.2f} threshold."
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(webhook_url, json=payload)
                    logger.info(f"Low-balance webhook delivered to {webhook_url} - Status: {resp.status_code}")
            except Exception as e:
                logger.error(f"Failed to deliver low balance webhook to {webhook_url}: {e}")
