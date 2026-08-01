import asyncio
import os
import logging
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/bristlecone_db")

STREAM_KEY = "api_usage_stream"
GROUP_NAME = "logger_group"
CONSUMER_NAME = "worker_1"

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_consumer_group(redis):
    try:
        await redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Consumer group '{GROUP_NAME}' created.")
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass
        else:
            raise e

async def process_batch(redis, session, entries):
    if not entries:
        return

    log_rows = []
    ack_ids = []
    latest_balance_per_tenant = {}

    for stream, messages in entries:
        for msg_id, fields in messages:
            tenant_id = fields.get("tenant_id")
            api_key_id = fields.get("api_key_id")
            endpoint = fields.get("endpoint")
            units = int(fields.get("units_consumed", 1))
            cost = float(fields.get("cost", 0.0))
            new_bal = float(fields.get("new_balance", 0.0))

            log_rows.append({
                "tenant_id": tenant_id,
                "api_key_id": api_key_id,
                "endpoint": endpoint,
                "units_consumed": units,
                "cost": cost
            })
            latest_balance_per_tenant[tenant_id] = new_bal
            ack_ids.append(msg_id)

    if log_rows:
        await session.execute(
            text("""
                INSERT INTO api_usage_logs (tenant_id, api_key_id, endpoint, units_consumed, cost)
                VALUES (:tenant_id, :api_key_id, :endpoint, :units_consumed, :cost)
            """),
            log_rows
        )

        for tid, bal in latest_balance_per_tenant.items():
            await session.execute(
                text("""
                    INSERT INTO tenant_balances (tenant_id, balance_usd)
                    VALUES (:tenant_id, :balance)
                    ON CONFLICT (tenant_id) DO UPDATE SET balance_usd = :balance
                """),
                {"tenant_id": tid, "balance": bal}
            )

        await session.commit()

    if ack_ids:
        await redis.xack(STREAM_KEY, GROUP_NAME, *ack_ids)

async def main():
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await init_consumer_group(redis)

    logger.info("Worker started, listening for stream events...")

    while True:
        try:
            entries = await redis.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=50,
                block=1000
            )

            if entries:
                async with AsyncSessionLocal() as session:
                    await process_batch(redis, session, entries)

        except aioredis.ResponseError as e:
            if "NOGROUP" in str(e):
                logger.warning("Consumer group missing, recreating...")
                await init_consumer_group(redis)
            else:
                logger.error(f"Redis error: {e}")
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in stream worker: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
