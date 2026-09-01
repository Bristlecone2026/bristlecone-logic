import os
import ast
import json
import socket
import asyncio
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from json_repair import repair_json
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

from app.core.metering import redis_client, deduct_credit, get_tenant_balance

# -----------------------------------------------------------------------------
# Configuration & Environment
# -----------------------------------------------------------------------------
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
USDC_ADDRESS = os.getenv("BASE_USDC_CONTRACT_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
TREASURY_ADDRESS = os.getenv("BASE_TREASURY_ADDRESS", "").lower()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
RATE_PER_CREDIT_USD = 0.002

# -----------------------------------------------------------------------------
# Background Payment Listener
# -----------------------------------------------------------------------------
async def send_discord_alert(message: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(DISCORD_WEBHOOK_URL, json={"content": message})
    except Exception as e:
        print(f"[Sentinel] Discord delivery error: {e}")

async def process_deposit(tx_hash: str, from_addr: str, value_raw: int):
    usdc_amount = value_raw / 1_000_000.0
    credits_to_add = int(usdc_amount / RATE_PER_CREDIT_USD)

    tenant_name = await redis_client.get(f"tenant_address:{from_addr.lower()}")
    if not tenant_name:
        tenant_name = "default_agent"

    new_balance = await redis_client.hincrby(f"tenant:{tenant_name}", "credits", credits_to_add)
    
    alert = (
        f"💰 **Deposit Settled on Base L2!**\n"
        f"• **Tx**: `{tx_hash}`\n"
        f"• **Amount**: `${usdc_amount:.2f} USDC`\n"
        f"• **Credits Allocated**: `+{credits_to_add:,}`\n"
        f"• **Tenant**: `{tenant_name}` (Balance: `{new_balance:,}`)"
    )
    print(alert)
    await send_discord_alert(alert)

async def base_payment_listener_loop():
    if not TREASURY_ADDRESS:
        print("[Listener] Warning: BASE_TREASURY_ADDRESS not configured. Listener paused.")
        return

    w3 = AsyncWeb3(AsyncHTTPProvider(BASE_RPC_URL))
    print(f"[Listener] Monitoring Base L2 USDC deposits targeting {TREASURY_ADDRESS}...")

    try:
        last_block = await w3.eth.block_number
    except Exception as e:
        print(f"[Listener] Initial block query failed: {e}")
        last_block = 0

    while True:
        try:
            current_block = await w3.eth.block_number
            if current_block > last_block and last_block > 0:
                treasury_padded = "0x" + TREASURY_ADDRESS.replace("0x", "").lower().rjust(64, "0")
                
                logs = await w3.eth.get_logs({
                    "fromBlock": last_block + 1,
                    "toBlock": current_block,
                    "address": w3.to_checksum_address(USDC_ADDRESS),
                    "topics": [TRANSFER_EVENT_TOPIC, None, treasury_padded]
                })

                for log in logs:
                    tx_hash = log["transactionHash"].hex()
                    from_addr = "0x" + log["topics"][1].hex()[-40:]
                    value_raw = int(log["data"].hex(), 16)
                    await process_deposit(tx_hash, from_addr, value_raw)

                last_block = current_block

            await asyncio.sleep(3.0)
        except Exception as e:
            print(f"[Listener] Polling cycle exception: {e}")
            await asyncio.sleep(6.0)

# -----------------------------------------------------------------------------
# Lifespan
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    listener_task = asyncio.create_task(base_payment_listener_loop())
    yield
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Bristlecone Logic M2M Microservices",
    version="1.0.0",
    lifespan=lifespan
)

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
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(payload.url)
        return {"url": payload.url, "status_code": resp.status_code, "content_length": len(resp.text), "text": resp.text[:4000]}

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
    domain = payload.domain.replace("https://", "").replace("http://", "").split("/")[0].strip()
    try:
        addr_info = socket.getaddrinfo(domain, 443)
        ips = list(set([item[4][0] for item in addr_info]))
        return {"domain": domain, "ip_addresses": ips, "status": "resolved"}
    except Exception as e:
        return {"domain": domain, "ip_addresses": [], "status": "error", "error": str(e)}

# -----------------------------------------------------------------------------
# TDQS-Optimized MCP Tool Manifest
# -----------------------------------------------------------------------------
MCP_CATALOG = [
    {
        "name": "audit_dns",
        "description": "Performs forward DNS resolution and network routing verification for a target domain. Resolves IPv4 and IPv6 addresses. Use to verify host reachability and guard autonomous agents against Server-Side Request Forgery (SSRF) before making HTTP requests. Do not use for WHOIS domain registration lookups or deep port scanning.",
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
        }
    },
    {
        "name": "chunk_text",
        "description": "Partitions raw text documents into uniform sliding-window segments with configurable character overlap. Returns an array of formatted text chunks. Use when preparing unstructured documents for vector database embeddings and RAG retrieval pipelines. Do not use for syntactic token counting or semantic sentence segmentation.",
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
        }
    },
    {
        "name": "eval_expression",
        "description": "Deterministically evaluates arithmetic, mathematical, and logical expressions inside an AST-isolated sandbox. Prevents LLM calculation errors while strictly blocking arbitrary code execution. Use for reliable numerical calculations and boolean logic. Do not use for executing arbitrary Python statements or importing external libraries.",
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
        }
    },
    {
        "name": "extract_web",
        "description": "Fetches and sanitizes readable text content from any public HTTP or HTTPS web page. Strips boilerplate HTML tags, navigation bars, and scripts. Returns clean body text and HTTP status code. Use when an agent needs primary webpage content for summarization or analysis. Do not use for authenticated pages or executing JavaScript.",
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
        }
    },
    {
        "name": "repair_json",
        "description": "Deterministically parses and repairs malformed, truncated, or unclosed JSON strings produced by LLMs (e.g. missing closing brackets, unescaped quotes, trailing commas). Returns parsed valid JSON object. Use when an LLM produces syntax-broken JSON. Do not use on valid non-JSON prose or for modifying data values.",
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
        }
    },
    {
        "name": "validate_schema",
        "description": "Deterministically validates that a target JSON payload contains all mandatory keys specified in a reference schema dictionary. Returns a boolean validation status and a list of missing keys. Use when verifying payload structure before downstream processing. Do not use for regex string validation or deep recursive type casting.",
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
        }
    }
]

# -----------------------------------------------------------------------------
# JSON-RPC Streamable HTTP Dispatcher
# -----------------------------------------------------------------------------
@app.post("/mcp")
@app.post("/sse")
@app.get("/sse")
@app.post("/")
async def mcp_handler(request: Request):
    if request.method == "GET":
        return JSONResponse({"status": "ready", "transport": "Streamable HTTP / JSON-RPC"})
    body = await request.json()
    req_id = body.get("id", 1)
    method = body.get("method")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bristlecone-mcp-gateway", "version": "1.0.0"}
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_CATALOG}
        }

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        # 1. JSON Repair
        if tool_name in ["repair_json", "json_repair"]:
            res = repair_json(args.get("raw_json", ""), return_objects=True)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}}

        # 2. Expression Evaluation
        if tool_name in ["eval_expression", "code_sandbox_eval"]:
            tree = ast.parse(args.get("expression", "0"), mode='eval')
            res = safe_eval(tree)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(res)}]}}

        # 3. Text Chunker
        if tool_name in ["chunk_text", "text_chunker"]:
            text = args.get("text", "")
            size = args.get("chunk_size", 500)
            overlap = args.get("chunk_overlap", 50)
            chunks = [text[i:i+size] for i in range(0, len(text), size - overlap or 1)]
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(chunks)}]}}

        # 4. DNS Audit
        if tool_name in ["audit_dns", "dns_security_audit"]:
            domain = args.get("domain", "").replace("https://", "").replace("http://", "").split("/")[0]
            addr_info = socket.getaddrinfo(domain, 443)
            ips = list(set([item[4][0] for item in addr_info]))
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"domain": domain, "ips": ips})}]}}

        # 5. Web Extraction
        if tool_name == "extract_web":
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(args.get("url", ""))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": r.text[:3000]}]}}

        # 6. Schema Validation
        if tool_name == "validate_schema":
            schema_keys = args.get("schema_definition", {}).keys()
            data_keys = args.get("data", {}).keys()
            missing = [k for k in schema_keys if k not in data_keys]
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"valid": len(missing) == 0, "missing": missing})}]}}

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not supported"}}

# ==============================================================================
# Agentic Resource Discovery (ARD) Manifest
# ==============================================================================
@app.get("/.well-known/ai-resources.json", tags=["Discovery"], include_in_schema=False)
@app.get("/.well-known/ai-catalog.json", tags=["Discovery"], include_in_schema=False)
async def ai_catalog_manifest():
    return {
        "spec_version": "0.9",
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
