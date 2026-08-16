import asyncio
import os
import logging
import uuid
import json
from decimal import Decimal
import httpx
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.services.xrpl_listener import start_xrpl_listener

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/bristlecone_db")

STREAM_KEY = "api_usage_stream"
GROUP_NAME = "logger_group"
CONSUMER_NAME = "worker_1"
BASE_RECEIVER_ADDRESS = "0x1B4309CFdbCEee7618a7fBDc5b145691F9246D67"

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_consumer_group(redis_client):
    try:
        await redis_client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Consumer group '{GROUP_NAME}' initialized on stream '{STREAM_KEY}'.")
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass
        else:
            raise e

async def send_low_balance_webhook(webhook_url: str, payload: dict):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(webhook_url, json=payload)
            logger.info(f"Low-balance webhook delivered to {webhook_url} (HTTP {res.status_code})")
    except Exception as e:
        logger.warning(f"Failed to deliver low-balance webhook to {webhook_url}: {e}")

async def check_and_alert_low_balance(redis_client, session: AsyncSession, tenant_id: uuid.UUID, new_balance: float):
    result = await session.execute(
        text("SELECT name, webhook_url, low_balance_threshold_usd FROM tenants WHERE id = :tid"),
        {"tid": tenant_id}
    )
    row = result.first()
    if not row:
        return

    tenant_name, webhook_url, threshold = row[0], row[1], float(row[2] or 1.0)
    alert_key = f"alert:low_balance:{tenant_id}"

    if new_balance <= threshold:
        is_alerted = await redis_client.get(alert_key)
        if not is_alerted:
            logger.warning(
                f"[LOW BALANCE ALERT] Tenant '{tenant_name}' ({tenant_id}) balance is ${new_balance:.6f} "
                f"(Threshold: ${threshold:.2f})"
            )
            await redis_client.set(alert_key, "alerted", ex=86400)

            if webhook_url:
                payload = {
                    "event": "tenant.low_balance",
                    "tenant_id": str(tenant_id),
                    "tenant_name": tenant_name,
                    "current_balance_usd": new_balance,
                    "threshold_usd": threshold,
                    "deposit_network": "Base L2 / XRPL",
                    "accepted_assets": ["USDC", "XRP", "RLUSD"],
                    "message": "Your credit balance is low. Please replenish via Base L2 or XRPL to avoid interruption."
                }
                asyncio.create_task(send_low_balance_webhook(webhook_url, payload))
    else:
        await redis_client.delete(alert_key)

async def credit_tenant_deposit(redis_client, session: AsyncSession, tenant_id: uuid.UUID, tx_hash: str, block_num: int, from_addr: str, amount_usdc: Decimal):
    insert_sql = text("""
        INSERT INTO tenant_deposits (
            tenant_id, tx_hash, block_number, from_address, to_address,
            amount_usdc, raw_amount, usd_value, network, asset, status
        ) VALUES (
            :tenant_id, :tx_hash, :block_num, :from_addr, :to_addr,
            :amount, :amount, :amount, 'base_l2', 'USDC', 'confirmed'
        )
        ON CONFLICT (tx_hash) DO NOTHING
        RETURNING id;
    """)

    result = await session.execute(
        insert_sql,
        {
            "tenant_id": tenant_id,
            "tx_hash": tx_hash,
            "block_num": block_num,
            "from_addr": from_addr,
            "to_addr": BASE_RECEIVER_ADDRESS,
            "amount": amount_usdc
        }
    )
    inserted_row = result.first()

    if not inserted_row:
        logger.info(f"Transaction {tx_hash} already credited. Skipping duplicate.")
        return False

    await session.execute(
        text("""
            UPDATE tenants 
            SET credit_balance_usd = credit_balance_usd + :amount,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :tenant_id
        """),
        {"tenant_id": tenant_id, "amount": amount_usdc}
    )
    await session.commit()

    balance_key = f"balance:{tenant_id}"
    new_balance = await redis_client.incrbyfloat(balance_key, float(amount_usdc))
    alert_key = f"alert:low_balance:{tenant_id}"
    await redis_client.delete(alert_key)

    logger.info(
        f"[BASE L2 DEPOSIT CREDITED] Tenant {tenant_id} topped up +${amount_usdc:.2f} USDC "
        f"(New Redis Balance: ${new_balance:.6f}) via Tx: {tx_hash}"
    )
    return True

async def deposit_listener_loop(redis_client):
    logger.info("Base L2 deposit listener coroutine active on 'base_deposit_queue'...")
    while True:
        try:
            msg = await redis_client.lpop("base_deposit_queue")
            if msg:
                payload = json.loads(msg)
                async with AsyncSessionLocal() as session:
                    await credit_tenant_deposit(
                        redis_client=redis_client,
                        session=session,
                        tenant_id=uuid.UUID(payload["tenant_id"]),
                        tx_hash=payload["tx_hash"],
                        block_num=int(payload.get("block_number", 0)),
                        from_addr=payload.get("from_address", "0x0"),
                        amount_usdc=Decimal(str(payload["amount_usdc"]))
                    )
            else:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in Base L2 deposit listener: {e}")
            await asyncio.sleep(1)

async def usage_sync_loop(redis_client):
    await init_consumer_group(redis_client)
    logger.info("Usage ledger sync coroutine active on 'api_usage_stream'...")
    while True:
        try:
            entries = await redis_client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=50,
                block=1000
            )
            if entries:
                async with AsyncSessionLocal() as session:
                    await process_batch(redis_client, session, entries)
        except Exception as e:
            logger.error(f"Error in usage sync: {e}")
            await asyncio.sleep(1)

async def process_batch(redis_client, session: AsyncSession, entries):
    ledger_rows = []
    ack_ids = []
    latest_balance_per_tenant = {}
    used_api_keys = set()

    for stream, messages in entries:
        for msg_id, fields in messages:
            if "data" in fields:
                try:
                    fields = json.loads(fields["data"])
                except Exception:
                    pass

            tenant_raw = fields.get("tenant_id")
            key_raw = fields.get("api_key_id")
            endpoint = fields.get("endpoint", "unknown")
            model_req = fields.get("model_requested", endpoint)
            provider = fields.get("provider", "tools_engine")
            
            prompt_tokens = int(fields.get("prompt_tokens", 0))
            completion_tokens = int(fields.get("completion_tokens", 0))
            total_tokens = int(fields.get("total_tokens", fields.get("units_consumed", 0)))
            
            cost = float(fields.get("billed_cost_usd", fields.get("cost", 0.0)))
            new_bal = float(fields.get("new_balance", 0.0))

            tenant_id = uuid.UUID(tenant_raw) if tenant_raw else None
            api_key_id = uuid.UUID(key_raw) if key_raw else None

            if tenant_id:
                ledger_rows.append({
                    "tenant_id": tenant_id,
                    "api_key_id": api_key_id,
                    "model_requested": model_req,
                    "provider": provider,
                    "is_byok": False,
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "raw_cost_usd": cost,
                    "billed_cost_usd": cost,
                    "latency_ms": None,
                    "status_code": 200
                })
                latest_balance_per_tenant[tenant_id] = new_bal
                if api_key_id:
                    used_api_keys.add(api_key_id)

            ack_ids.append(msg_id)

    if ledger_rows:
        await session.execute(
            text("""
                INSERT INTO llm_usage_ledger (
                    tenant_id, api_key_id, model_requested, provider, is_byok,
                    input_tokens, output_tokens, total_tokens, raw_cost_usd, billed_cost_usd,
                    latency_ms, status_code
                ) VALUES (
                    :tenant_id, :api_key_id, :model_requested, :provider, :is_byok,
                    :input_tokens, :output_tokens, :total_tokens, :raw_cost_usd, :billed_cost_usd,
                    :latency_ms, :status_code
                )
            """),
            ledger_rows
        )

        for tid, bal in latest_balance_per_tenant.items():
            await session.execute(
                text("""
                    UPDATE tenants
                    SET credit_balance_usd = :balance,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :tenant_id
                """),
                {"tenant_id": tid, "balance": bal}
            )
            await check_and_alert_low_balance(redis_client, session, tid, bal)

        for kid in used_api_keys:
            await session.execute(
                text("""
                    UPDATE api_keys
                    SET last_used_at = CURRENT_TIMESTAMP
                    WHERE id = :key_id
                """),
                {"key_id": kid}
            )

        await session.commit()
        logger.info(f"Persisted {len(ledger_rows)} records and synchronized balances.")

    if ack_ids:
        await redis_client.xack(STREAM_KEY, GROUP_NAME, *ack_ids)

async def main():
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Starting Bristlecone background daemons (Usage, Base L2, XRPL WebSocket)...")
    await asyncio.gather(
        usage_sync_loop(redis_client),
        deposit_listener_loop(redis_client),
        start_xrpl_listener(redis_client, AsyncSessionLocal)
    )

if __name__ == "__main__":
    asyncio.run(main())
