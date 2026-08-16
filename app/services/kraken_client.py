import ccxt.async_support as ccxt
import os
import logging

logger = logging.getLogger("uvicorn.error")

async def get_kraken_client():
    exchange = ccxt.kraken({
        'apiKey': os.getenv('KRAKEN_API_KEY'),
        'secret': os.getenv('KRAKEN_PRIVATE_KEY'),
        'enableRateLimit': True,
    })
    return exchange

async def fetch_kraken_balance():
    exchange = await get_kraken_client()
    try:
        balance = await exchange.fetch_balance()
        return balance.get('free', {})
    except Exception as e:
        logger.error(f"[Kraken] Error fetching balance: {e}")
        return {}
    finally:
        await exchange.close()

async def execute_market_buy(symbol: str, amount_usd: float):
    exchange = await get_kraken_client()
    try:
        # Fetch current ticker to determine order parameters
        ticker = await exchange.fetch_ticker(symbol)
        ask_price = ticker['ask']
        
        # Place market order (or limit order pegged to ask)
        order = await exchange.create_order(symbol, 'market', 'buy', None, amount_usd)
        logger.info(f"[Kraken] Executed buy order for {symbol}: {order['id']}")
        return order
    except Exception as e:
        logger.error(f"[Kraken] Trade execution failed: {e}")
        raise e
    finally:
        await exchange.close()
