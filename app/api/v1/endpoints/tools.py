import ast
import re
import json
import logging
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.core.security import TenantContext, verify_api_key

logger = logging.getLogger("api.tools")
router = APIRouter()

COST_WEB_EXTRACT = "0.005000"
COST_JSON_REPAIR = "0.002000"

METER_LUA = """
local rate_key = KEYS[1]
local balance_key = KEYS[2]
local cost = tonumber(ARGV[1])
local max_rate = tonumber(ARGV[2])

local current_reqs = redis.call('INCR', rate_key)
if current_reqs == 1 then
    redis.call('EXPIRE', rate_key, 60)
end
if current_reqs > max_rate then
    return {429, tostring(current_reqs)}
end

local current_bal = tonumber(redis.call('GET', balance_key) or "0")
if current_bal < cost then
    return {402, tostring(current_bal)}
end

local new_bal = redis.call('INCRBYFLOAT', balance_key, -cost)
return {200, tostring(new_bal)}
"""

async def execute_metering(request: Request, tenant: TenantContext, endpoint: str, cost: str):
    redis_conn = request.app.state.redis
    rate_key = f"rate:{tenant.tenant_id}"
    balance_key = f"balance:{tenant.tenant_id}"

    res = await redis_conn.eval(METER_LUA, 2, rate_key, balance_key, cost, str(tenant.rate_limit_rpm))
    status_code = int(res[0])
    val = float(res[1])

    if status_code == 429:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {tenant.rate_limit_rpm} requests per minute."
        )
    elif status_code == 402:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_balance",
                "message": "Insufficient credit balance. Fund wallet with USDC on Base L2.",
                "current_balance_usd": val,
                "required_cost_usd": float(cost),
                "receiver_address": "0x1B4309CFdbCEee7618a7fBDc5b145691F9246D67"
            }
        )

    await redis_conn.xadd(
        "api_usage_stream",
        {
            "tenant_id": tenant.tenant_id,
            "api_key_id": tenant.key_id,
            "endpoint": endpoint,
            "units_consumed": "1",
            "cost": cost,
            "new_balance": str(val)
        }
    )
    return val

class WebExtractRequest(BaseModel):
    url: str
    extract_links: bool = False
    max_length: Optional[int] = 50000

class WebExtractResponse(BaseModel):
    url: str
    title: Optional[str]
    markdown: str
    extracted_links: Optional[List[str]] = None
    character_count: int
    remaining_balance_usd: float

class JsonRepairRequest(BaseModel):
    raw_text: str

class JsonRepairResponse(BaseModel):
    success: bool
    data: Any
    fixed_syntax: bool
    details: Optional[str] = None
    remaining_balance_usd: float

def clean_and_repair_json(raw: str):
    raw_clean = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_clean)
    if match:
        raw_clean = match.group(1).strip()

    try:
        parsed = json.loads(raw_clean)
        return parsed, False, "Valid JSON"
    except Exception:
        pass

    try:
        evaluated = ast.literal_eval(raw_clean)
        if isinstance(evaluated, (dict, list, str, int, float, bool)) or evaluated is None:
            return evaluated, True, "Repaired via AST evaluation"
    except Exception:
        pass

    repaired = re.sub(r",\s*([\]}])", r"\1", raw_clean)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"(?<!\\)'", '"', repaired)

    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    repaired += ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))

    try:
        parsed = json.loads(repaired)
        return parsed, True, "Repaired trailing commas, quotes, and unbalanced brackets"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to parse or repair input JSON: {str(e)}"
        )

@router.post("/web-extract", response_model=WebExtractResponse)
async def web_extract(
    payload: WebExtractRequest,
    request: Request,
    tenant: TenantContext = Depends(verify_api_key)
):
    remaining_balance = await execute_metering(
        request=request,
        tenant=tenant,
        endpoint="/api/v1/tools/web-extract",
        cost=COST_WEB_EXTRACT
    )

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                payload.url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BristleconeBot/1.0; +https://bristleconelogic.com)"}
            )
            resp.raise_for_status()
            html_content = resp.text
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch content from {payload.url}: {str(e)}"
        )

    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else None

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "iframe"]):
        tag.decompose()

    links = []
    if payload.extract_links:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("http") and href not in links:
                links.append(href)

    content_md = md(str(soup), heading_style="ATX", strip=["img"])
    content_md = re.sub(r"\n{3,}", "\n\n", content_md).strip()

    if payload.max_length and len(content_md) > payload.max_length:
        content_md = content_md[:payload.max_length] + "\n\n...[Truncated]"

    return WebExtractResponse(
        url=payload.url,
        title=title,
        markdown=content_md,
        extracted_links=links if payload.extract_links else None,
        character_count=len(content_md),
        remaining_balance_usd=remaining_balance
    )

@router.post("/json-repair", response_model=JsonRepairResponse)
async def json_repair(
    payload: JsonRepairRequest,
    request: Request,
    tenant: TenantContext = Depends(verify_api_key)
):
    remaining_balance = await execute_metering(
        request=request,
        tenant=tenant,
        endpoint="/api/v1/tools/json-repair",
        cost=COST_JSON_REPAIR
    )

    parsed_data, fixed_syntax, details = clean_and_repair_json(payload.raw_text)

    return JsonRepairResponse(
        success=True,
        data=parsed_data,
        fixed_syntax=fixed_syntax,
        details=details,
        remaining_balance_usd=remaining_balance
    )
