import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Standard rates per 1,000,000 tokens (USD)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "o1": {"prompt": 15.00, "completion": 60.00},
    
    # Anthropic
    "claude-3-5-sonnet-20241022": {"prompt": 3.00, "completion": 15.00},
    "claude-3-haiku-20240307": {"prompt": 0.25, "completion": 1.25},
    
    # Google
    "gemini-1.5-pro": {"prompt": 1.25, "completion": 5.00},
    "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30},

    # Fallback default
    "default": {"prompt": 2.00, "completion": 8.00}
}


def calculate_execution_cost(
    model: str, 
    prompt_tokens: int = 0, 
    completion_tokens: int = 0, 
    total_tokens: int = 0
) -> float:
    """Calculates cost in USD based on provider/model rates per 1M tokens."""
    rates = MODEL_PRICING.get(model.lower(), MODEL_PRICING["default"])
    
    if prompt_tokens == 0 and completion_tokens == 0 and total_tokens > 0:
        prompt_tokens = int(total_tokens * 0.75)
        completion_tokens = total_tokens - prompt_tokens

    prompt_cost = (prompt_tokens / 1_000_000) * rates["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * rates["completion"]
    
    total_cost = round(prompt_cost + completion_cost, 6)
    return max(total_cost, 0.000001)


async def record_usage_and_deduct_credit(
    db: AsyncSession,
    tenant_id: str,
    provider: str,
    model: str,
    total_tokens: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    status_code: int = 200
) -> float:
    """Logs token usage to ledger and decrements tenant balance in a single transaction."""
    billed_cost_usd = calculate_execution_cost(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens
    )

    try:
        ledger_query = text("""
            INSERT INTO llm_usage_ledger (
                tenant_id, provider, model_requested, total_tokens, 
                latency_ms, billed_cost_usd, created_at
            ) VALUES (
                :tenant_id, :provider, :model, :total_tokens, 
                :latency_ms, :billed_cost_usd, NOW()
            )
        """)
        await db.execute(ledger_query, {
            "tenant_id": tenant_id,
            "provider": provider,
            "model": model,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "billed_cost_usd": billed_cost_usd
        })

        tenant_query = text("""
            UPDATE tenants 
            SET credit_balance_usd = GREATEST(0.0, credit_balance_usd - :billed_cost)
            WHERE id = :tenant_id
        """)
        await db.execute(tenant_query, {
            "billed_cost": billed_cost_usd,
            "tenant_id": tenant_id
        })

        await db.commit()
        logger.info(f"Deducted ${billed_cost_usd:.6f} from tenant {tenant_id} for {total_tokens} tokens ({model})")
        return billed_cost_usd

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to record usage and deduct credits for tenant {tenant_id}: {str(e)}")
        raise e
