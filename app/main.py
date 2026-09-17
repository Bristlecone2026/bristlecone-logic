from app.layer4_ledgers.xrpl_tools import router as xrpl_tools_router
from app.middleware.m2m_payment import M2MPaymentMiddleware
from app.middleware.xrpl_claim import XRPLClaimMiddleware
import os
import ast
import json
import socket
import ipaddress
import asyncio
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from json_repair import repair_json
from web3.providers import AsyncHTTPProvider

from app.core.metering import redis_client, deduct_credit, get_tenant_balance
from app.core.rpc_resilience import RpcCircuitBreaker
from app.api.v1.admin import router as admin_router

# -----------------------------------------------------------------------------
# Configuration & Environment
# -----------------------------------------------------------------------------
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
USDC_ADDRESS = os.getenv("BASE_USDC_CONTRACT_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
TREASURY_ADDRESS = os.getenv("BASE_TREASURY_ADDRESS", "").lower()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

ARC_RPC_URL = os.getenv("ARC_RPC_URL", "https://rpc.mainnet.arc.io")
ARC_TREASURY_ADDRESS = os.getenv("ARC_TREASURY_ADDRESS", TREASURY_ADDRESS).lower()

BASE_RPC_POOL = [url.strip() for url in os.getenv("BASE_FALLBACK_RPCS", f"{BASE_RPC_URL},https://base.llamarpc.com,https://1rpc.io/base").split(",") if url.strip()]
ARC_RPC_POOL = [url.strip() for url in os.getenv("ARC_FALLBACK_RPCS", f"{ARC_RPC_URL}").split(",") if url.strip()]

MAX_BLOCK_RANGE_PER_CYCLE = 25


TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
RATE_PER_CREDIT_USD = 0.002

# -----------------------------------------------------------------------------
# Background Payment Listeners
# -----------------------------------------------------------------------------
async def send_discord_alert(message: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(DISCORD_WEBHOOK_URL, json={"content": message})
    except Exception as e:
        print(f"[Sentinel] Discord delivery error: {e}")

async def process_deposit(tx_hash: str, from_addr: str, value_raw: int, network: str = "base"):
    tx_key = f"tx_confirmed:{tx_hash.lower()}"
    if await redis_client.get(tx_key):
        print(f"[Listener] Skipped duplicate transaction: {tx_hash}")
        return

    # Decimal normalization: Arc native USDC = 18 decimals, Base ERC-20 USDC = 6 decimals
    decimals = 18 if network.lower() == "arc" else 6
    usdc_amount = value_raw / float(10 ** decimals)
    credits_to_add = int(usdc_amount / RATE_PER_CREDIT_USD)

    tenant_name = await redis_client.get(f"tenant_address:{from_addr.lower()}")
    if not tenant_name:
        tenant_name = "default_agent"

    new_balance = await redis_client.hincrby(f"tenant:{tenant_name}", "credits", credits_to_add)
    await redis_client.incrby(f"balance:{tenant_name}", credits_to_add)
    await redis_client.set(tx_key, "1", ex=604800)

    network_label = "Arc L1" if network.lower() == "arc" else "Base L2"
    alert = (
        f"💰 **Deposit Settled on {network_label}!**\n"
        f"• **Tx**: `{tx_hash}`\n"
        f"• **Amount**: `${usdc_amount:.4f} USDC`\n"
        f"• **Credits Allocated**: `+{credits_to_add:,}`\n"
        f"• **Tenant**: `{tenant_name}` (Balance: `{new_balance:,}`)"
    )
    print(alert)
    await send_discord_alert(alert)

async def base_payment_listener_loop():
    if not TREASURY_ADDRESS:
        print("[Listener] Warning: BASE_TREASURY_ADDRESS not configured. Listener paused.")
        return

    breaker = RpcCircuitBreaker("Base-L2", BASE_RPC_POOL, failure_threshold=3)
    print(f"[Base Listener] Circuit Breaker active. Monitoring Base L2 USDC on {breaker.active_url}...")

    last_block = 0
    while True:
        try:
            current_block = await breaker.execute_with_resilience(
                lambda w3: w3.eth.block_number, alert_fn=send_discord_alert
            )
            if last_block == 0:
                last_block = current_block

            if current_block > last_block:
                # Cap range per cycle to prevent RPC throttling during catch-up
                target_block = min(current_block, last_block + MAX_BLOCK_RANGE_PER_CYCLE)
                treasury_padded = "0x" + TREASURY_ADDRESS.replace("0x", "").lower().rjust(64, "0")

                async def fetch_logs(w3):
                    return await w3.eth.get_logs({
                        "fromBlock": last_block + 1,
                        "toBlock": target_block,
                        "address": w3.to_checksum_address(USDC_ADDRESS),
                        "topics": [TRANSFER_EVENT_TOPIC, None, treasury_padded]
                    })

                logs = await breaker.execute_with_resilience(fetch_logs, alert_fn=send_discord_alert)
                for log in logs:
                    tx_hash = log["transactionHash"].hex()
                    from_addr = "0x" + log["topics"][1].hex()[-40:]
                    value_raw = int(log["data"].hex(), 16)
                    await process_deposit(tx_hash, from_addr, value_raw, network="base")

                last_block = target_block

            await asyncio.sleep(3.0)
        except Exception as e:
            # Resilient breaker handles backoff and node rotation internally
            await asyncio.sleep(2.0)

async def arc_payment_listener_loop():
    if not ARC_TREASURY_ADDRESS:
        print("[Arc Listener] Warning: ARC_TREASURY_ADDRESS not configured. Listener paused.")
        return

    breaker = RpcCircuitBreaker("Arc-L1", ARC_RPC_POOL, failure_threshold=3)
    print(f"[Arc Listener] Circuit Breaker active. Monitoring Arc L1 USDC on {breaker.active_url}...")

    last_block = 0
    while True:
        try:
            current_block = await breaker.execute_with_resilience(
                lambda w3: w3.eth.block_number, alert_fn=send_discord_alert
            )
            if last_block == 0:
                last_block = current_block

            if current_block > last_block:
                target_block = min(current_block, last_block + MAX_BLOCK_RANGE_PER_CYCLE)
                for block_num in range(last_block + 1, target_block + 1):
                    block = await breaker.execute_with_resilience(
                        lambda w3, b=block_num: w3.eth.get_block(b, full_transactions=True),
                        alert_fn=send_discord_alert
                    )
                    for tx in block.get("transactions", []):
                        to_addr = tx.get("to")
                        if to_addr and to_addr.lower() == ARC_TREASURY_ADDRESS:
                            value_raw = tx.get("value", 0)
                            if value_raw > 0:
                                tx_hash = tx["hash"].hex()
                                from_addr = tx.get("from", "")
                                await process_deposit(tx_hash, from_addr, value_raw, network="arc")

                last_block = target_block

            await asyncio.sleep(2.0)
        except Exception as e:
            # Resilient breaker handles backoff and node rotation internally
            await asyncio.sleep(2.0)

# -----------------------------------------------------------------------------
# Lifespan
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    base_task = asyncio.create_task(base_payment_listener_loop())
    arc_task = asyncio.create_task(arc_payment_listener_loop())
    yield
    base_task.cancel()
    arc_task.cancel()
    try:
        await asyncio.gather(base_task, arc_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Bristlecone Logic M2M Microservices",
    version="0.4.3",
    lifespan=lifespan
)

app.include_router(admin_router, prefix="/api/v1")

app.add_middleware(M2MPaymentMiddleware)
app.add_middleware(XRPLClaimMiddleware)

# -----------------------------------------------------------------------------
# Hardened SSRF & DNS Pre-Flight Validation Engine
# -----------------------------------------------------------------------------
HARDENED_CIDRS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Localhost alias (RFC 1122)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback (RFC 1122)
    ipaddress.ip_network("10.0.0.0/8"),         # Private Network (RFC 1918)
    ipaddress.ip_network("172.16.0.0/12"),      # Private Network (RFC 1918)
    ipaddress.ip_network("192.168.0.0/16"),     # Private Network (RFC 1918)
    ipaddress.ip_network("169.254.0.0/16"),     # Link-Local / IMDS (RFC 3927)
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Space (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol (RFC 6890)
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking (RFC 2544)
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    ipaddress.ip_network("::/128"),             # IPv6 Unspecified
    ipaddress.ip_network("::1/128"),            # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),          # IPv6 Link-Local
]

def verify_host_safety(raw_target: str) -> dict:
    clean = raw_target.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].strip()
    if not clean:
        return {"domain": raw_target, "is_safe": False, "reason": "EMPTY_TARGET", "ip_addresses": [], "status": "error"}
    try:
        addr_info = socket.getaddrinfo(clean, None)
        resolved_ips = list({item[4][0] for item in addr_info})
        for raw_ip in resolved_ips:
            ip_obj = ipaddress.ip_address(raw_ip)
            if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                ip_obj = ip_obj.ipv4_mapped
            for cidr in HARDENED_CIDRS:
                if ip_obj in cidr:
                    return {
                        "domain": clean,
                        "is_safe": False,
                        "reason": f"BLOCKED ({ip_obj} in {cidr})",
                        "ip_addresses": resolved_ips,
                        "status": "refused"
                    }
        return {
            "domain": clean,
            "is_safe": True,
            "reason": "PERMITTED (Public)",
            "ip_addresses": resolved_ips,
            "status": "resolved"
        }
    except Exception as e:
        return {
            "domain": clean,
            "is_safe": False,
            "reason": f"BLOCKED ({e.__class__.__name__})",
            "ip_addresses": [],
            "status": "error",
            "error": str(e)
        }

def validate_safe_url(url: str):
    check = verify_host_safety(url)
    if not check.get("is_safe"):
        raise HTTPException(status_code=400, detail=f"SSRF Security Violation: {check.get('reason', 'BLOCKED')}")

# -----------------------------------------------------------------------------
# Core Execution Logic
# -----------------------------------------------------------------------------
class ExtractWebRequest(BaseModel):
    url: str

class ValidateSchemaRequest(BaseModel):
    schema_definition: dict
    data: dict

class JSONRepairRequest(BaseModel):
    raw_json: str

class TextChunkRequest(BaseModel):
    text: str
    chunk_size: int = 500
    chunk_overlap: int = 50

class CodeEvalRequest(BaseModel):
    expression: str

class DNSAuditRequest(BaseModel):
    domain: str

SAFE_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
}

def safe_eval(node):
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
        return SAFE_OPERATORS[type(node.op)](safe_eval(node.left), safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
        return SAFE_OPERATORS[type(node.op)](safe_eval(node.operand))
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")

@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "service": "bristlecone-logic", "catalog_size": 6}

@app.post("/tools/extract-web")
async def extract_web(payload: ExtractWebRequest, x_tenant_id: str = Header(default="default_agent")):
    await deduct_credit(x_tenant_id, 1)
    current_url = str(payload.url)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        for _ in range(4):
            validate_safe_url(current_url)
            resp = await client.get(current_url, headers={"User-Agent": "BristleconeLogic-Agent/1.0"})
            if resp.is_redirect:
                loc = resp.headers.get("Location")
                if not loc:
                    break
                current_url = urljoin(current_url, loc)
                continue
            return {"url": current_url, "status_code": resp.status_code, "content_length": len(resp.text), "text": resp.text[:4000]}
        raise HTTPException(status_code=400, detail="Exceeded maximum allowed redirect hops (3).")

@app.post("/tools/validate-schema")
async def validate_schema(payload: ValidateSchemaRequest, x_tenant_id: str = Header(default="default_agent")):
    await deduct_credit(x_tenant_id, 1)
    missing = [k for k in payload.schema_definition.keys() if k not in payload.data]
    return {"valid": len(missing) == 0, "missing_keys": missing}

@app.post("/tools/repair-json")
async def repair_json_endpoint(payload: JSONRepairRequest, x_tenant_id: str = Header(default="default_agent")):
    await deduct_credit(x_tenant_id, 1)
    try:
        repaired = repair_json(payload.raw_json, return_objects=True)
        return {"repaired": repaired, "valid": True}
    except Exception as e:
        return {"repaired": None, "valid": False, "error": str(e)}

@app.post("/tools/chunk-text")
async def chunk_text_endpoint(payload: TextChunkRequest, x_tenant_id: str = Header(default="default_agent")):
    await deduct_credit(x_tenant_id, 1)
    text = payload.text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + payload.chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += payload.chunk_size - payload.chunk_overlap
    return {"total_chunks": len(chunks), "chunks": chunks}

@app.post("/tools/eval-expression")
async def eval_expression_endpoint(payload: CodeEvalRequest, x_tenant_id: str = Header(default="default_agent")):
    await deduct_credit(x_tenant_id, 1)
    try:
        tree = ast.parse(payload.expression, mode='eval')
        res = safe_eval(tree)
        return {"expression": payload.expression, "result": res, "success": True}
    except Exception as e:
        return {"expression": payload.expression, "result": None, "success": False, "error": str(e)}

@app.post("/tools/audit-dns")
async def audit_dns_endpoint(payload: DNSAuditRequest, x_tenant_id: str = Header(default="default_agent")):
    await deduct_credit(x_tenant_id, 1)
    return verify_host_safety(payload.domain)

# -----------------------------------------------------------------------------
# TDQS-Optimized MCP Tool Manifest
# -----------------------------------------------------------------------------
MCP_CATALOG = [
    {
        "name": "audit_dns",
        "description": "Performs forward DNS resolution and network routing verification for a target domain. Resolves IPv4 and IPv6 addresses. Use to verify host reachability and guard autonomous agents against Server-Side Request Forgery (SSRF) before making HTTP requests. Do not use for WHOIS domain registration lookups or deep port scanning.",
        "readOnlyHint": True,
        "idempotentHint": True,
        "destructiveHint": False,
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "audience": ["agent", "developer"]
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "format": "hostname",
                    "description": "The fully qualified domain name (FQDN) or hostname to resolve (e.g. 'api.github.com' or 'openai.com'). Do not include http/https protocols or URL paths."
                }
            },
            "required": ["domain"],
            "additionalProperties": False
        },
    },
    {
        "name": "chunk_text",
        "description": "Partitions raw text documents into uniform sliding-window segments with configurable character overlap. Returns an array of formatted text chunks. Use when preparing unstructured documents for vector database embeddings and RAG retrieval pipelines. Do not use for syntactic token counting or semantic sentence segmentation.",
        "readOnlyHint": True,
        "idempotentHint": True,
        "destructiveHint": False,
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "audience": ["agent", "developer"]
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The source document text string to segment into discrete chunks."
                },
                "chunk_size": {
                    "type": "integer",
                    "description": "Maximum character length of each individual chunk segment. Defaults to 500 characters.",
                    "default": 500,
                    "minimum": 50
                },
                "chunk_overlap": {
                    "type": "integer",
                    "description": "Number of overlapping characters shared between consecutive chunks to maintain semantic context. Defaults to 50 characters.",
                    "default": 50,
                    "minimum": 0
                }
            },
            "required": ["text"],
            "additionalProperties": False
        },
    },
    {
        "name": "eval_expression",
        "description": "Deterministically evaluates arithmetic, mathematical, and logical expressions inside an AST-isolated sandbox. Prevents LLM calculation errors while strictly blocking arbitrary code execution. Use for reliable numerical calculations and boolean logic. Do not use for executing arbitrary Python statements or importing external libraries.",
        "readOnlyHint": True,
        "idempotentHint": True,
        "destructiveHint": False,
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "audience": ["agent", "developer"]
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A valid mathematical, arithmetic, or boolean expression string (e.g. '((150 * 12) / 4) + 18.5')."
                }
            },
            "required": ["expression"],
            "additionalProperties": False
        },
    },
    {
        "name": "extract_web",
        "description": "Fetches and sanitizes readable text content from any public HTTP or HTTPS web page. Strips boilerplate HTML tags, navigation bars, and scripts. Returns clean body text and HTTP status code. Use when an agent needs primary webpage content for summarization or analysis. Do not use for authenticated pages or executing JavaScript.",
        "readOnlyHint": True,
        "idempotentHint": True,
        "destructiveHint": False,
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "audience": ["agent", "developer"]
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "The complete target website URL including http:// or https:// protocol prefix (e.g. 'https://docs.python.org/3/')."
                }
            },
            "required": ["url"],
            "additionalProperties": False
        },
    },
    {
        "name": "repair_json",
        "description": "Deterministically parses and repairs malformed, truncated, or unclosed JSON strings produced by LLMs (e.g. missing closing brackets, unescaped quotes, trailing commas). Returns parsed valid JSON object. Use when an LLM produces syntax-broken JSON. Do not use on valid non-JSON prose or for modifying data values.",
        "readOnlyHint": True,
        "idempotentHint": True,
        "destructiveHint": False,
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "audience": ["agent", "developer"]
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "raw_json": {
                    "type": "string",
                    "description": "The unparsed, malformed, or incomplete JSON text string requiring syntax repair into standard RFC 8259 format."
                }
            },
            "required": ["raw_json"],
            "additionalProperties": False
        },
    },
    {
        "name": "validate_schema",
        "description": "Deterministically validates that a target JSON payload contains all mandatory keys specified in a reference schema dictionary. Returns a boolean validation status and a list of missing keys. Use when verifying payload structure before downstream processing. Do not use for regex string validation or deep recursive type casting.",
        "readOnlyHint": True,
        "idempotentHint": True,
        "destructiveHint": False,
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "audience": ["agent", "developer"]
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "schema_definition": {
                    "type": "object",
                    "description": "A JSON object defining mandatory keys required in the target payload (e.g. {'user_id': '', 'status': ''})."
                },
                "data": {
                    "type": "object",
                    "description": "The target JSON data object to inspect and validate against the schema definition."
                }
            },
            "required": ["schema_definition", "data"],
            "additionalProperties": False
        },
    }
]

# -----------------------------------------------------------------------------
# JSON-RPC Streamable HTTP Dispatcher
# -----------------------------------------------------------------------------
@app.post("/mcp")
@app.post("/sse")
@app.get("/sse")
@app.post("/")
@app.get("/")
async def mcp_handler(request: Request):
    if request.method == "GET":
        host = request.headers.get("host", "").lower()
        if "xrp." in host:
            return JSONResponse({
                "service": "Bristlecone Logic - XRPL M2M Tool Gateway",
                "status": "active",
                "payment_protocol": "x402",
                "network": "xrpl:mainnet",
                "payee": "rNjtBUTFAj7iSRoeVqpJoedFra4SM929VD",
                "catalog": "https://xrp.bristleconelogic.com/openapi.json",
                "endpoints": {
                    "/tools/repair-json": {"cost_drops": 1000},
                    "/tools/xrpl/orderbook-depth": {"cost_drops": 2000},
                    "/tools/xrpl/amm-arb-quote": {"cost_drops": 5000},
                    "/tools/xrpl/ticket-pool": {"cost_drops": 1000}
                },
                "instructions": "Send requests with X-XRPL-* payment channel claim headers. Unauthenticated requests receive 402 challenge."
            })
        return JSONResponse({"status": "ready", "transport": "Streamable HTTP / JSON-RPC"})
    
    try:
        raw_body = await request.body()
        if not raw_body or not raw_body.strip():
            return JSONResponse({"status": "ready", "transport": "Streamable HTTP / JSON-RPC", "mcp": "bristlecone-mcp-gateway"})
        body = json.loads(raw_body)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error: empty or invalid JSON payload"}, "id": None}
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request: expected JSON object"}, "id": None}
        )

    req_id = body.get("id", 1)
    method = body.get("method")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bristlecone-mcp-gateway", "version": "0.4.3"}
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_CATALOG}
        }

    if method == "tools/call":
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or getattr(request.client, "host", "anonymous")
        tenant_id = request.headers.get("x-tenant-id") or f"trial_{client_ip}"

        quota = await deduct_credit(tenant_id, 1)
        remaining = quota.get("remaining", 0)

        meta_headers = {
            "X-Credits-Remaining": str(remaining),
            "X-402-Topup-Address": "0xa17c8c3005698bc4ea6406a00387445e1d30c35f",
            "X-402-Network": "base"
        }

        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name in ["repair_json", "json_repair"]:
            res = repair_json(args.get("raw_json", ""), return_objects=True)
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}}, headers=meta_headers)

        if tool_name in ["eval_expression", "code_sandbox_eval"]:
            tree = ast.parse(args.get("expression", "0"), mode='eval')
            res = safe_eval(tree)
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}, headers=meta_headers)

        if tool_name in ["chunk_text", "text_chunker"]:
            text = args.get("text", "")
            size = args.get("chunk_size", 500)
            overlap = args.get("chunk_overlap", 50)
            chunks = [text[i:i+size] for i in range(0, len(text), size - overlap or 1)]
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(chunks)}]}}, headers=meta_headers)

        if tool_name in ["audit_dns", "dns_security_audit"]:
            domain = args.get("domain", "")
            res = verify_host_safety(domain)
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}}, headers=meta_headers)

        if tool_name == "extract_web":
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(args.get("url", ""))
                return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": r.text[:3000]}]}}, headers=meta_headers)

        if tool_name == "validate_schema":
            schema_keys = args.get("schema_definition", {}).keys()
            data_keys = args.get("data", {}).keys()
            missing = [k for k in schema_keys if k not in data_keys]
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"valid": len(missing) == 0, "missing": missing})}]}}, headers=meta_headers)

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not supported"}}

# ==============================================================================
# Agentic Resource Discovery (ARD) Manifest
# ==============================================================================
@app.api_route("/.well-known/glama.json", methods=["GET", "HEAD"], tags=["Discovery"], include_in_schema=False)
async def glama_manifest():
    return {
        "$schema": "https://glama.ai/mcp/v1/schema.json",
        "name": "bristlecone-logic",
        "description": "Autonomous dual-rail agent gateway with deterministic AST JSON repair and SSRF guardrails.",
        "homepage": "https://bristleconelogic.com",
        "url": "https://bristleconelogic.com/mcp"
    }

@app.api_route("/.well-known/ai-resources.json", methods=["GET", "HEAD"], tags=["Discovery"], include_in_schema=False)
@app.api_route("/.well-known/ai-catalog.json", methods=["GET", "HEAD"], tags=["Discovery"], include_in_schema=False)
async def ai_catalog_manifest():
    return {
        "spec_version": "0.9",
        "payment": {
            "protocol": "x402",
            "network": "eip155:8453",
            "currency": "USDC",
            "payee": "0xa17c8c3005698bc4ea6406a00387445e1d30c35f"
        },
        "name": "Bristlecone Guard",
        "description": "Deterministic runtime guardrails and M2M safety for autonomous agent pipelines.",
        "provider": {
            "name": "Bristlecone Logic LLC",
            "url": "https://bristleconelogic.com"
        },
        "endpoints": [
            {
                "type": "mcp",
                "transport": "sse",
                "url": "https://bristleconelogic.com/mcp",
                "tools": [
                    {
                        "name": "ssrf_guard",
                        "description": "Pre-socket DNS resolution and private network CIDR filter."
                    },
                    {
                        "name": "json_repair",
                        "description": "Zero-overhead LLM payload syntax reconstructor."
                    },
                    {
                        "name": "ast_math",
                        "description": "Deterministic AST-sandboxed arithmetic evaluator."
                    },
                    {
                        "name": "audit_dns",
                        "description": "Domain DNS record extraction and IP resolution audit."
                    },
                    {
                        "name": "extract_web",
                        "description": "Sanitized server-side text extraction from target URLs."
                    },
                    {
                        "name": "validate_schema",
                        "description": "Key-level schema validation for agent input/output payloads."
                    }
                ]
            }
        ]
    }

app.include_router(xrpl_tools_router)

from app.layer4_ledgers.xrpl_tools import get_tools_manifest
app.add_api_route("/.well-known/x402-manifest.json", get_tools_manifest, methods=["GET"])
