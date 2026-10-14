import ast
import time
import socket
import ipaddress
from collections import defaultdict
import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from json_repair import repair_json

router = APIRouter(prefix="/v1/sandbox", tags=["Zero-Auth Developer Sandbox"])

# In-memory sliding window rate limiter: 5 requests per 60 seconds per IP
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 60
_ip_requests = defaultdict(list)

HARDENED_CIDRS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

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

def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
        return SAFE_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
        return SAFE_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")

def enforce_sandbox_limit(request: Request) -> int:
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    now = time.time()
    history = [t for t in _ip_requests[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(history) >= RATE_LIMIT_MAX:
        retry_in = int(RATE_LIMIT_WINDOW - (now - history[0]))
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Sandbox rate limit exceeded (5 req/min).",
                "retry_after_seconds": retry_in,
                "upgrade": "Use production endpoints (/tools/* or /mcp) via HTTP 402 (Arc L1 / Base L2 / XRPL Payment Channels) or Bearer API key."
            },
            headers={"Retry-After": str(retry_in)}
        )
    history.append(now)
    _ip_requests[client_ip] = history
    return RATE_LIMIT_MAX - len(history)

class SandboxDNSRequest(BaseModel):
    domain: str

class SandboxRepairRequest(BaseModel):
    raw_json: str

class SandboxEvalRequest(BaseModel):
    expression: str

@router.post("/audit-dns")
async def sandbox_audit_dns(payload: SandboxDNSRequest, request: Request):
    remaining = enforce_sandbox_limit(request)
    clean = payload.domain.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Empty domain target.")
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
                        "sandbox": True,
                        "sandbox_requests_remaining": remaining,
                        "domain": clean,
                        "is_safe": False,
                        "reason": f"BLOCKED ({ip_obj} in {cidr})",
                        "ip_addresses": resolved_ips,
                        "status": "refused"
                    }
        return {
            "sandbox": True,
            "sandbox_requests_remaining": remaining,
            "domain": clean,
            "is_safe": True,
            "reason": "PERMITTED (Public Routable IP)",
            "ip_addresses": resolved_ips,
            "status": "resolved"
        }
    except Exception as e:
        return {
            "sandbox": True,
            "sandbox_requests_remaining": remaining,
            "domain": clean,
            "is_safe": False,
            "reason": f"BLOCKED ({e.__class__.__name__})",
            "ip_addresses": [],
            "status": "error"
        }

@router.post("/repair-json")
async def sandbox_repair_json(payload: SandboxRepairRequest, request: Request):
    remaining = enforce_sandbox_limit(request)
    try:
        repaired = repair_json(payload.raw_json[:2000], return_objects=True)
        return {
            "sandbox": True,
            "sandbox_requests_remaining": remaining,
            "valid": True,
            "repaired": repaired
        }
    except Exception as e:
        return {
            "sandbox": True,
            "sandbox_requests_remaining": remaining,
            "valid": False,
            "error": str(e)
        }

@router.post("/eval-expression")
async def sandbox_eval_expression(payload: SandboxEvalRequest, request: Request):
    remaining = enforce_sandbox_limit(request)
    try:
        tree = ast.parse(payload.expression[:200], mode="eval")
        res = _safe_eval(tree)
        return {
            "sandbox": True,
            "sandbox_requests_remaining": remaining,
            "expression": payload.expression,
            "result": res,
            "success": True
        }
    except Exception as e:
        return {
            "sandbox": True,
            "sandbox_requests_remaining": remaining,
            "expression": payload.expression,
            "result": None,
            "success": False,
            "error": str(e)
        }

@router.get("/xrpl-ledger")
async def sandbox_xrpl_ledger(request: Request):
    remaining = enforce_sandbox_limit(request)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://xrplcluster.com/",
                json={"method": "ledger", "params": [{"ledger_index": "validated", "transactions": False}]}
            )
            ledger = resp.json().get("result", {}).get("ledger", {})
            return {
                "sandbox": True,
                "sandbox_requests_remaining": remaining,
                "network": "xrpl:mainnet",
                "ledger_index": ledger.get("ledger_index"),
                "ledger_hash": ledger.get("ledger_hash"),
                "close_time_human": ledger.get("close_time_human"),
                "production_gateway": "https://xrp.bristleconelogic.com"
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XRPL RPC query failed: {str(e)}")
