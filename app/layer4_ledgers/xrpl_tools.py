import os
from decimal import Decimal
from typing import Optional, Dict, Any, List, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models.requests import BookOffers
from xrpl.models.currencies import XRP, IssuedCurrency

router = APIRouter(prefix="/tools/xrpl", tags=["XRPL Tools"])

XRPL_RPC_URL = os.getenv("XRPL_JSON_RPC_URL") or os.getenv("XRPL_RPC_URL", "https://xrplcluster.com")


class AssetSpec(BaseModel):
    currency: str = Field(..., description="Asset ticker, e.g., 'XRP', 'RLUSD', 'USD'")
    issuer: Optional[str] = Field(None, description="Account address of the issuer; None for native XRP")


class OrderbookDepthRequest(BaseModel):
    base: AssetSpec = Field(default_factory=lambda: AssetSpec(currency="XRP"))
    quote: AssetSpec = Field(..., description="Counter-currency to price the base against")
    trade_amount: float = Field(100.0, gt=0, description="Volume of base asset to simulate executing")
    trade_side: str = Field("buy", pattern="^(buy|sell)$", description="'buy' consumes asks, 'sell' consumes bids")
    depth_limit: int = Field(20, ge=1, le=100, description="Max depth layers to inspect")


def to_xrpl_currency(asset: AssetSpec):
    if asset.currency.upper() == "XRP":
        return XRP()
    if not asset.issuer:
        raise HTTPException(status_code=400, detail=f"Issuer required for issued asset {asset.currency}")
    return IssuedCurrency(currency=asset.currency, issuer=asset.issuer)


def parse_xrpl_amount(amt: Any) -> Decimal:
    if isinstance(amt, str):
        # Native XRP in drops
        return Decimal(amt) / Decimal(1_000_000)
    elif isinstance(amt, dict) and "value" in amt:
        # Issued currency
        return Decimal(amt["value"])
    return Decimal(0)


@router.post("/orderbook-depth")
async def get_orderbook_depth(payload: OrderbookDepthRequest) -> Dict[str, Any]:
    client = AsyncJsonRpcClient(XRPL_RPC_URL)
    base_curr = to_xrpl_currency(payload.base)
    quote_curr = to_xrpl_currency(payload.quote)

    # Asks: Sellers offering Base in exchange for Quote (taker_gets=Base, taker_pays=Quote)
    req_asks = BookOffers(
        taker_gets=base_curr,
        taker_pays=quote_curr,
        limit=payload.depth_limit
    )

    # Bids: Buyers offering Quote in exchange for Base (taker_gets=Quote, taker_pays=Base)
    req_bids = BookOffers(
        taker_gets=quote_curr,
        taker_pays=base_curr,
        limit=payload.depth_limit
    )

    try:
        resp_asks, resp_bids = await client.request(req_asks), await client.request(req_bids)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XRPL RPC Error: {str(e)}")

    raw_asks: List[Dict[str, Any]] = resp_asks.result.get("offers", [])
    raw_bids: List[Dict[str, Any]] = resp_bids.result.get("offers", [])

    # Process Top of Book
    best_ask: Optional[Decimal] = None
    best_bid: Optional[Decimal] = None

    parsed_asks = []
    for offer in raw_asks:
        base_avail = parse_xrpl_amount(offer.get("TakerGets"))
        quote_req = parse_xrpl_amount(offer.get("TakerPays"))
        if base_avail > 0:
            price = quote_req / base_avail
            parsed_asks.append({"price": price, "base_volume": base_avail, "quote_volume": quote_req})
            if best_ask is None or price < best_ask:
                best_ask = price

    parsed_bids = []
    for offer in raw_bids:
        quote_avail = parse_xrpl_amount(offer.get("TakerGets"))
        base_req = parse_xrpl_amount(offer.get("TakerPays"))
        if base_req > 0:
            price = quote_avail / base_req
            parsed_bids.append({"price": price, "base_volume": base_req, "quote_volume": quote_avail})
            if best_bid is None or price > best_bid:
                best_bid = price

    mid_price = ((best_ask + best_bid) / Decimal(2)) if (best_ask and best_bid) else None
    spread = (best_ask - best_bid) if (best_ask and best_bid) else None

    # Simulate Trade Execution & Slippage
    target_vol = Decimal(str(payload.trade_amount))
    remaining = target_vol
    total_quote_spent_or_received = Decimal(0)
    book_to_walk = parsed_asks if payload.trade_side == "buy" else parsed_bids

    for level in book_to_walk:
        fill_base = min(remaining, level["base_volume"])
        fill_quote = fill_base * level["price"]
        total_quote_spent_or_received += fill_quote
        remaining -= fill_base
        if remaining <= 0:
            break

    fillable = remaining <= 0
    filled_volume = target_vol - max(Decimal(0), remaining)
    effective_price = (total_quote_spent_or_received / filled_volume) if filled_volume > 0 else Decimal(0)

    slippage_bps = None
    if mid_price and effective_price > 0:
        slippage_delta = abs(effective_price - mid_price) / mid_price
        slippage_bps = float(slippage_delta * Decimal(10_000))

    return {
        "pair": f"{payload.base.currency}/{payload.quote.currency}",
        "top_of_book": {
            "best_bid": float(best_bid) if best_bid else None,
            "best_ask": float(best_ask) if best_ask else None,
            "mid_price": float(mid_price) if mid_price else None,
            "spread": float(spread) if spread else None,
        },
        "simulation": {
            "side": payload.trade_side,
            "requested_volume": float(target_vol),
            "filled_volume": float(filled_volume),
            "fillable": fillable,
            "effective_price": float(effective_price),
            "total_quote_cost": float(total_quote_spent_or_received),
            "slippage_bps": slippage_bps
        },
        "depth": {
            "ask_levels": len(parsed_asks),
            "bid_levels": len(parsed_bids)
        }
    }


class AmmArbQuoteRequest(BaseModel):
    base: AssetSpec = Field(default_factory=lambda: AssetSpec(currency="XRP"))
    quote: AssetSpec = Field(..., description="Counter asset / quote currency")
    trade_amount: Optional[float] = Field(100.0, gt=0, description="Nominal base volume to evaluate")


def is_matching_asset(xrpl_amt: Any, spec: AssetSpec) -> bool:
    if spec.currency.upper() == "XRP":
        return isinstance(xrpl_amt, str)
    if isinstance(xrpl_amt, dict):
        return (
            xrpl_amt.get("currency", "").upper() == spec.currency.upper()
            and xrpl_amt.get("issuer") == spec.issuer
        )
    return False


@router.post("/amm-arb-quote")
async def get_amm_arb_quote(payload: AmmArbQuoteRequest) -> Dict[str, Any]:
    client = AsyncJsonRpcClient(XRPL_RPC_URL)
    base_curr = to_xrpl_currency(payload.base)
    quote_curr = to_xrpl_currency(payload.quote)

    # 1. Fetch CLOB offers (Top 10 bids and asks)
    req_asks = BookOffers(taker_gets=base_curr, taker_pays=quote_curr, limit=10)
    req_bids = BookOffers(taker_gets=quote_curr, taker_pays=base_curr, limit=10)

    # 2. Fetch AMM pool state
    try:
        from xrpl.models.requests import AMMInfo
        req_amm = AMMInfo(asset=base_curr, asset2=quote_curr)
    except Exception:
        from xrpl.models.requests.request import Request, RequestMethod
        from dataclasses import dataclass
        @dataclass(frozen=True)
        class GenericAMMInfo(Request):
            method: RequestMethod = RequestMethod.AMM_INFO
            asset: Any = None
            asset2: Any = None
        req_amm = GenericAMMInfo(asset=base_curr, asset2=quote_curr)

    resp_asks, resp_bids = await client.request(req_asks), await client.request(req_bids)

    amm_data = None
    try:
        resp_amm = await client.request(req_amm)
        if resp_amm.is_successful():
            amm_data = resp_amm.result.get("amm")
    except Exception:
        amm_data = None

    # Parse CLOB Top of Book
    best_ask: Optional[Decimal] = None
    for offer in resp_asks.result.get("offers", []):
        base_v = parse_xrpl_amount(offer.get("TakerGets"))
        quote_v = parse_xrpl_amount(offer.get("TakerPays"))
        if base_v > 0:
            price = quote_v / base_v
            if best_ask is None or price < best_ask:
                best_ask = price

    best_bid: Optional[Decimal] = None
    for offer in resp_bids.result.get("offers", []):
        quote_v = parse_xrpl_amount(offer.get("TakerGets"))
        base_v = parse_xrpl_amount(offer.get("TakerPays"))
        if base_v > 0:
            price = quote_v / base_v
            if best_bid is None or price > best_bid:
                best_bid = price

    clob_mid = ((best_ask + best_bid) / Decimal(2)) if (best_ask and best_bid) else None

    # If no AMM pool exists for pair
    if not amm_data:
        return {
            "pair": f"{payload.base.currency}/{payload.quote.currency}",
            "amm_exists": False,
            "message": "No active AMM instance found for this token pair.",
            "clob": {
                "best_bid": float(best_bid) if best_bid else None,
                "best_ask": float(best_ask) if best_ask else None,
                "mid_price": float(clob_mid) if clob_mid else None
            },
            "arbitrage": {
                "opportunity_detected": False,
                "strategy": "NONE"
            }
        }

    # Parse AMM pool reserves
    amt1 = amm_data.get("amount")
    amt2 = amm_data.get("amount2")

    if is_matching_asset(amt1, payload.base):
        r_base = parse_xrpl_amount(amt1)
        r_quote = parse_xrpl_amount(amt2)
    else:
        r_base = parse_xrpl_amount(amt2)
        r_quote = parse_xrpl_amount(amt1)

    trading_fee_val = Decimal(amm_data.get("trading_fee", 0))
    fee_rate = trading_fee_val / Decimal(100_000)
    fee_bps = float(fee_rate * Decimal(10_000))

    amm_spot = (r_quote / r_base) if r_base > 0 else None
    amm_buy_price = (amm_spot / (Decimal(1) - fee_rate)) if (amm_spot and fee_rate < 1) else None
    amm_sell_price = (amm_spot * (Decimal(1) - fee_rate)) if amm_spot else None

    # Evaluate Arbitrage Viability
    strategy = "NONE"
    gross_margin_bps = 0.0

    # Arb Direction A: Buy on AMM, Sell on CLOB (AMM buy price < CLOB best bid)
    if amm_buy_price and best_bid and best_bid > amm_buy_price:
        strategy = "BUY_AMM_SELL_CLOB"
        gross_margin_bps = float(((best_bid - amm_buy_price) / amm_buy_price) * Decimal(10_000))

    # Arb Direction B: Buy on CLOB, Sell on AMM (CLOB best ask < AMM sell price)
    elif best_ask and amm_sell_price and amm_sell_price > best_ask:
        strategy = "BUY_CLOB_SELL_AMM"
        gross_margin_bps = float(((amm_sell_price - best_ask) / best_ask) * Decimal(10_000))

    divergence_bps = None
    if amm_spot and clob_mid:
        divergence_bps = float(abs(amm_spot - clob_mid) / clob_mid * Decimal(10_000))

    return {
        "pair": f"{payload.base.currency}/{payload.quote.currency}",
        "amm_exists": True,
        "amm_account": amm_data.get("account"),
        "pool": {
            "base_reserve": float(r_base),
            "quote_reserve": float(r_quote),
            "trading_fee_bps": fee_bps,
            "amm_spot_price": float(amm_spot) if amm_spot else None,
            "amm_effective_buy": float(amm_buy_price) if amm_buy_price else None,
            "amm_effective_sell": float(amm_sell_price) if amm_sell_price else None
        },
        "clob": {
            "best_bid": float(best_bid) if best_bid else None,
            "best_ask": float(best_ask) if best_ask else None,
            "mid_price": float(clob_mid) if clob_mid else None
        },
        "arbitrage": {
            "opportunity_detected": strategy != "NONE",
            "strategy": strategy,
            "gross_margin_bps": gross_margin_bps,
            "divergence_bps": divergence_bps
        }
    }


class TicketPoolRequest(BaseModel):
    account: str = Field(..., description="Classic XRPL address to evaluate (r...)")
    target_pool_size: int = Field(10, ge=1, le=250, description="Desired minimum tickets available in reserve")


@router.post("/ticket-pool")
async def get_ticket_pool(payload: TicketPoolRequest) -> Dict[str, Any]:
    client = AsyncJsonRpcClient(XRPL_RPC_URL)

    # 1. Fetch account info for current base sequence and reserve metrics
    from xrpl.models.requests import AccountInfo, AccountObjects
    
    req_info = AccountInfo(account=payload.account, ledger_index="validated")
    req_objects = AccountObjects(account=payload.account, type="ticket", ledger_index="validated", limit=400)

    try:
        resp_info = await client.request(req_info)
        if not resp_info.is_successful():
            error_data = resp_info.result.get("error_message") or resp_info.result.get("error") or "Unknown error"
            raise HTTPException(status_code=404, detail=f"Account {payload.account} lookup failed: {error_data}")
        resp_objects = await client.request(req_objects)
        if not resp_objects.is_successful():
            error_data = resp_objects.result.get("error_message") or resp_objects.result.get("error") or "Unknown error"
            raise HTTPException(status_code=502, detail=f"Ticket query failed: {error_data}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XRPL RPC Connection Error: {str(e)}")

    account_data = resp_info.result.get("account_data", {})
    current_sequence = account_data.get("Sequence", 0)
    owner_count = account_data.get("OwnerCount", 0)
    balance_drops = int(account_data.get("Balance", 0))

    # 2. Extract active tickets
    raw_objects = resp_objects.result.get("account_objects", [])
    active_tickets: List[int] = sorted([
        obj.get("TicketSequence") for obj in raw_objects if "TicketSequence" in obj
    ])

    ticket_count = len(active_tickets)
    deficit = max(0, payload.target_pool_size - ticket_count)
    
    # 0.2 XRP owner reserve per ticket object on mainnet
    reserve_per_ticket_xrp = 0.2
    estimated_reserve_required_xrp = round(deficit * reserve_per_ticket_xrp, 4)

    recommendation = {
        "status": "HEALTHY" if deficit == 0 else "DEFICIT",
        "action": "NONE" if deficit == 0 else "EXECUTE_TICKET_CREATE",
        "tickets_to_create": deficit,
        "additional_reserve_xrp": estimated_reserve_required_xrp,
        "suggested_tx": None
    }

    if deficit > 0:
        recommendation["suggested_tx"] = {
            "TransactionType": "TicketCreate",
            "Account": payload.account,
            "TicketCount": deficit,
            "Sequence": current_sequence,
            "Fee": "12"
        }

    return {
        "account": payload.account,
        "current_sequence": current_sequence,
        "owner_count": owner_count,
        "balance_xrp": round(balance_drops / 1_000_000, 6),
        "pool": {
            "target_size": payload.target_pool_size,
            "available_count": ticket_count,
            "active_tickets": active_tickets
        },
        "recommendation": recommendation
    }


@router.get("/manifest", include_in_schema=False)
async def get_tools_manifest():
    return {
        "manifest_version": "1.0",
        "provider": "Bristlecone Logic - Xylem M2M",
        "network": "xrpl:mainnet",
        "settlement_scheme": "payment-channel",
        "payee": "rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD",
        "tools": [
            {
                "id": "orderbook-depth",
                "name": "XRPL CLOB Depth & Slippage Simulator",
                "endpoint": "/tools/xrpl/orderbook-depth",
                "method": "POST",
                "price_drops": 2000,
                "price_xrp": 0.002,
                "description": "Calculates orderbook depth, bid/ask spread, and exact execution slippage curve for a given trade size."
            },
            {
                "id": "amm-arb-quote",
                "name": "XRPL AMM vs CLOB Arbitrage Scanner",
                "endpoint": "/tools/xrpl/amm-arb-quote",
                "method": "POST",
                "price_drops": 5000,
                "price_xrp": 0.005,
                "description": "Cross-evaluates AMM invariant pool pricing against CLOB top-of-book to detect arbitrage margins."
            },
            {
                "id": "ticket-pool",
                "name": "XRPL Concurrency Ticket Allocator",
                "endpoint": "/tools/xrpl/ticket-pool",
                "method": "POST",
                "price_drops": 1000,
                "price_xrp": 0.001,
                "description": "Audits active Sequence Tickets and outputs transaction payloads to replenish ticket pools for parallel bot execution."
            },
            {
                "id": "repair-json",
                "name": "Deterministic JSON Repair Engine",
                "endpoint": "/tools/repair-json",
                "method": "POST",
                "price_drops": 1000,
                "price_xrp": 0.001,
                "description": "Repairs malformed or truncated JSON emitted by autonomous LLM agents."
            }
        ]
    }
