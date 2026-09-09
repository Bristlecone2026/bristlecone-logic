import os
import sys
sys.path.insert(0, '/app')
import asyncio
import logging
from decimal import Decimal
from dotenv import load_dotenv

# Load local .env variables
load_dotenv("/app/.env")
load_dotenv()

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.transaction import autofill_and_sign, submit_and_wait
from xrpl.models.transactions import PaymentChannelClaim, Payment
from xrpl.models.requests import AccountInfo
from xrpl.wallet import Wallet
from app.core.metering import redis_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("xylem.settler")

XRPL_RPC_URL = os.getenv("XRPL_RPC_URL", "https://s1.ripple.com:51234")
TREASURY_SEED = os.getenv("XRPL_TREASURY_SEED")
COLD_VAULT_ADDRESS = os.getenv("XRPL_COLD_VAULT_ADDRESS")

CLAIM_THRESHOLD_DROPS = int(os.getenv("CLAIM_THRESHOLD_DROPS", "10000000"))       # 10 XRP
HOT_WALLET_RESERVE_DROPS = int(os.getenv("HOT_WALLET_RESERVE_DROPS", "15000000")) # 15 XRP
SWEEP_THRESHOLD_DROPS = int(os.getenv("SWEEP_THRESHOLD_DROPS", "50000000"))         # 50 XRP


async def settle_payment_channels(client: AsyncJsonRpcClient, wallet: Wallet):
    """
    Scans Redis for active vouchers and submits PaymentChannelClaim transactions.
    """
    logger.info("Checking active payment channel claims in Redis...")
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="xrpl:channel:*:latest_claim", count=50)
        for key in keys:
            channel_id = key.split(":")[2]
            claim_data = await redis_client.hgetall(key)
            if not claim_data:
                continue

            authorized_drops = int(claim_data.get("amount_drops") or claim_data.get("drops", 0))
            settled_key = f"xrpl:channel:{channel_id}:settled_drops"
            last_settled_raw = await redis_client.get(settled_key)
            last_settled = int(last_settled_raw) if last_settled_raw else 0

            unsettled_drops = authorized_drops - last_settled
            if unsettled_drops < CLAIM_THRESHOLD_DROPS:
                logger.info(f"Channel {channel_id[:16]} unsettled: {unsettled_drops} drops (< threshold). Skipping.")
                continue

            logger.info(f"Redeeming {unsettled_drops} drops for channel {channel_id[:16]} on-ledger...")

            claim_tx = PaymentChannelClaim(
                account=wallet.classic_address,
                channel=channel_id,
                balance=str(authorized_drops),
                signature=claim_data["signature"],
                public_key=claim_data["public_key"],
            )

            try:
                signed_tx = await autofill_and_sign(claim_tx, client, wallet)
                resp = await submit_and_wait(signed_tx, client)
                result_code = resp.result.get("meta", {}).get("TransactionResult")

                if result_code == "tesSUCCESS":
                    logger.info(f"Claim successful for {channel_id[:16]}. Ledger Hash: {resp.result.get('hash')}")
                    await redis_client.set(settled_key, authorized_drops)
                else:
                    logger.error(f"Failed claiming channel {channel_id[:16]}: {result_code}")

            except Exception as e:
                logger.error(f"Error submitting claim for channel {channel_id[:16]}: {e}")

        if cursor == 0:
            break


async def sweep_to_vault(client: AsyncJsonRpcClient, wallet: Wallet):
    """
    Transfers excess drops above reserve threshold to Trezor cold storage.
    """
    if not COLD_VAULT_ADDRESS or not COLD_VAULT_ADDRESS.startswith("r"):
        logger.warning("Cold vault address not configured or invalid. Skipping sweep.")
        return

    req = AccountInfo(account=wallet.classic_address, ledger_index="validated")
    try:
        resp = await client.request(req)
        account_data = resp.result.get("account_data", {})
        current_balance_drops = int(account_data.get("Balance", 0))
    except Exception as e:
        logger.error(f"Failed to fetch hot wallet account info: {e}")
        return

    balance_xrp = Decimal(current_balance_drops) / 1_000_000
    logger.info(f"Hot wallet balance: {balance_xrp} XRP")

    excess_drops = current_balance_drops - HOT_WALLET_RESERVE_DROPS
    if excess_drops >= SWEEP_THRESHOLD_DROPS:
        sweep_amount = excess_drops - 12  # Subtract ~12 drops for standard tx fee
        logger.info(f"Triggering sweep of {Decimal(sweep_amount) / 1_000_000} XRP to Trezor vault ({COLD_VAULT_ADDRESS})...")

        tx = Payment(
            account=wallet.classic_address,
            destination=COLD_VAULT_ADDRESS,
            amount=str(sweep_amount)
        )

        try:
            signed_tx = await autofill_and_sign(tx, client, wallet)
            resp = await submit_and_wait(signed_tx, client)
            result_code = resp.result.get("meta", {}).get("TransactionResult")

            if result_code == "tesSUCCESS":
                logger.info(f"Sweep successful. Tx Hash: {resp.result.get('hash')}")
            else:
                logger.error(f"Sweep failed with result code: {result_code}")
        except Exception as e:
            logger.error(f"Error submitting sweep payment: {e}")
    else:
        logger.info("Balance below sweep threshold. No sweep required.")


async def main():
    if not TREASURY_SEED:
        raise ValueError("XRPL_TREASURY_SEED environment variable is required.")

    wallet = Wallet.from_seed(TREASURY_SEED)
    client = AsyncJsonRpcClient(XRPL_RPC_URL)

    logger.info(f"Settler daemon started for hot wallet: {wallet.classic_address}")
    await settle_payment_channels(client, wallet)
    await sweep_to_vault(client, wallet)


if __name__ == "__main__":
    asyncio.run(main())
