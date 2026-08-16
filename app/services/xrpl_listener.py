import asyncio
import json
import logging
import os
import uuid
from decimal import Decimal
import websockets
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("worker.xrpl")

XRPL_WS_URL = os.getenv("XRPL_WS_URL", "wss://s.altnet.rippletest.net:51233")
XRPL_TREASURY_ADDRESS = os.getenv("XRPL_TREASURY_ADDRESS", "rPT1Sjq2YGrBMTttX4GZHjKu9DYfzbpAYe")
XRP_USD_PRICE = Decimal(os.getenv("XRP_USD_PRICE", "0.60"))

async def process_xrpl_payment(redis_client, session_factory, tx: dict):
    if tx.get("TransactionType") != "Payment":
        return

    meta = tx.get("meta") or tx.get("metaData", {})
    if meta.get("TransactionResult") != "tesSUCCESS":
        return

    destination = tx.get("Destination")
    if destination != XRPL_TREASURY_ADDRESS:
        return

    destination_tag = tx.get("DestinationTag")
    if destination_tag is None:
        logger.warning(f"[XRPL] Payment received without DestinationTag. Tx: {tx.get('hash')}")
        return

    tx_hash = tx.get("hash")
    from_addr = tx.get("Account", "unknown")
    ledger_index = tx.get("ledger_index", 0)
    raw_amount_field = tx.get("Amount")

    if isinstance(raw_amount_field, str):
        drops = Decimal(raw_amount_field)
        xrp_amount = drops / Decimal("1000000")
        usd_value = (xrp_amount * XRP_USD_PRICE).quantize(Decimal("0.000001"))
        asset = "XRP"
        raw_amt = xrp_amount
    elif isinstance(raw_amount_field, dict):
        asset = raw_amount_field.get("currency", "UNKNOWN")
        raw_amt = Decimal(str(raw_amount_field.get("value", "0")))
        if asset in ["RLUSD", "USD", "USDC"]:
            usd_value = raw_amt.quantize(Decimal("0.000001"))
        else:
            logger.warning(f"[XRPL] Unsupported token '{asset}' on Tx {tx_hash}")
            return
    else:
        return

    async with session_factory() as session:
        res = await session.execute(
            text("SELECT id, name FROM tenants WHERE xrpl_destination_tag = :tag AND is_active = true"),
            {"tag": int(destination_tag)}
        )
        tenant_row = res.first()
        if not tenant_row:
            logger.error(f"[XRPL] No active tenant found for DestinationTag: {destination_tag}")
            return

        tenant_id, tenant_name = tenant_row[0], tenant_row[1]

        insert_sql = text("""
            INSERT INTO tenant_deposits (
                tenant_id, tx_hash, block_number, from_address, to_address,
                amount_usdc, raw_amount, usd_value, network, asset, destination_tag, status
            ) VALUES (
                :tenant_id, :tx_hash, :block_num, :from_addr, :to_addr,
                :amount_usdc, :raw_amount, :usd_value, 'xrpl', :asset, :tag, 'confirmed'
            )
            ON CONFLICT (tx_hash) DO NOTHING
            RETURNING id;
        """)

        insert_res = await session.execute(
            insert_sql,
            {
                "tenant_id": tenant_id,
                "tx_hash": tx_hash,
                "block_num": ledger_index,
                "from_addr": from_addr,
                "to_addr": destination,
                "amount_usdc": usd_value,
                "raw_amount": raw_amt,
                "usd_value": usd_value,
                "asset": asset,
                "tag": int(destination_tag)
            }
        )
        row = insert_res.first()
        if not row:
            logger.info(f"[XRPL] Tx {tx_hash} already credited. Skipping duplicate.")
            return

        await session.execute(
            text("""
                UPDATE tenants
                SET credit_balance_usd = credit_balance_usd + :usd_val,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :tenant_id
            """),
            {"tenant_id": tenant_id, "usd_val": usd_value}
        )
        await session.commit()

    balance_key = f"balance:{tenant_id}"
    new_balance = await redis_client.incrbyfloat(balance_key, float(usd_value))
    await redis_client.delete(f"alert:low_balance:{tenant_id}")

    logger.info(
        f"[XRPL DEPOSIT CREDITED] Tenant '{tenant_name}' ({tenant_id}) | Tag: {destination_tag} | "
        f"+{raw_amt} {asset} (~${usd_value:.4f} USD) | New Redis Balance: ${new_balance:.6f} | Tx: {tx_hash}"
    )

async def start_xrpl_listener(redis_client, session_factory):
    logger.info(f"Connecting to XRPL WebSocket on {XRPL_WS_URL} for account {XRPL_TREASURY_ADDRESS}...")
    backoff = 2

    while True:
        try:
            async with websockets.connect(XRPL_WS_URL, ping_interval=20, ping_timeout=10) as ws:
                logger.info(f"[XRPL WS] Connected to {XRPL_WS_URL}. Subscribing to stream...")
                subscribe_msg = {
                    "id": 1,
                    "command": "subscribe",
                    "accounts": [XRPL_TREASURY_ADDRESS]
                }
                await ws.send(json.dumps(subscribe_msg))
                sub_response = await ws.recv()
                logger.info(f"[XRPL WS] Subscription response: {sub_response}")
                backoff = 2

                async for message in ws:
                    try:
                        data = json.loads(message)
                        if data.get("type") == "transaction" and data.get("validated") is True:
                            tx = data.get("transaction", {})
                            tx["meta"] = data.get("meta")
                            tx["ledger_index"] = data.get("ledger_index")
                            asyncio.create_task(process_xrpl_payment(redis_client, session_factory, tx))
                    except Exception as e:
                        logger.error(f"[XRPL WS] Error parsing message: {e}")

        except Exception as e:
            logger.warning(f"[XRPL WS] Connection error: {e}. Retrying in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
