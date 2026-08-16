import asyncio
import os
import logging
import uuid
from decimal import Decimal
import httpx
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deposit_daemon")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/bristlecone_db")

# Base L2 Configuration
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
# Base Native USDC Contract (6 Decimals)
USDC_CONTRACT_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913".lower()
RECEIVER_ADDRESS = "0x1B4309CFdbCEee7618a7fBDc5b145691F9246D67".lower()

# ERC-20 Transfer Event Signature Topic: Transfer(address,address,uint256)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=10)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def credit_tenant_deposit(
    redis_client,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    tx_hash: str,
    block_num: int,
    from_addr: str,
    amount_usdc: Decimal
) -> bool:
    """Idempotently records deposit and increments Redis + DB balances."""
    # 1. Insert into database with ON CONFLICT DO NOTHING
    insert_sql = text("""
        INSERT INTO tenant_deposits (
            tenant_id, tx_hash, block_number, from_address, to_address, amount_usdc, status
        ) VALUES (
            :tenant_id, :tx_hash, :block_num, :from_addr, :to_addr, :amount, 'confirmed'
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
            "to_addr": RECEIVER_ADDRESS,
            "amount": amount_usdc
        }
    )
    inserted_row = result.first()

    if not inserted_row:
        logger.info(f"Transaction {tx_hash} already credited. Skipping duplicate.")
        return False

    # 2. Increment PostgreSQL Balance
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

    # 3. Atomically Increment Redis Balance
    balance_key = f"balance:{tenant_id}"
    new_balance = await redis_client.incrbyfloat(balance_key, float(amount_usdc))

    # 4. Clear low balance alert debounce lock
    alert_key = f"alert:low_balance:{tenant_id}"
    await redis_client.delete(alert_key)

    logger.info(
        f"[DEPOSIT CREDITED] Tenant {tenant_id} topped up +${amount_usdc:.2f} USDC "
        f"(New Redis Balance: ${new_balance:.6f}) via Tx: {tx_hash}"
    )
    return True

async def manual_or_simulated_deposit_listener():
    """Background listener for verified transactions."""
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"Base L2 USDC deposit daemon listening for receiver: {RECEIVER_ADDRESS}")

    while True:
        try:
            # Polling channel / stream for incoming confirmed deposit jobs
            # This handles webhooks from Alchemy/QuickNode or internal RPC block scanner
            msg = await redis_client.lpop("base_deposit_queue")
            if msg:
                import json
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
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in deposit daemon loop: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(manual_or_simulated_deposit_listener())
