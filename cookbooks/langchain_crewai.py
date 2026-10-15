"""
LangChain & CrewAI Integration Recipe for Bristlecone Logic.

Provides pre-built @tool decorators for LangChain and CrewAI agents to route
network requests through SSRF-guarded DNS pre-flight checks, deterministic JSON repair,
and native XRPL ledger state tools.
"""

import os
import httpx
from pydantic import BaseModel, Field

try:
    from langchain_core.tools import tool
except ImportError:
    # Fallback shim if langchain-core is not installed in current environment
    def tool(name=None, args_schema=None):
        def decorator(func):
            return func
        return decorator


SANDBOX_BASE_URL = os.environ.get(
    "BRISTLECONE_BASE_URL", 
    "https://api.bristleconelogic.com/v1/sandbox"
)


class DnsAuditInput(BaseModel):
    domain: str = Field(description="The target domain or IP to check against SSRF/CIDR blocklists.")


class JsonRepairInput(BaseModel):
    raw_json: str = Field(description="Malformed, truncated, or unescaped JSON text to reconstruct.")


class EvalMathInput(BaseModel):
    expression: str = Field(description="Arithmetic expression string to compute safely inside an AST sandbox.")


@tool("bristlecone_dns_audit", args_schema=DnsAuditInput)
def bristlecone_dns_audit(domain: str) -> dict:
    """Audits target domain reachability and enforces pre-socket SSRF blocking against private subnets."""
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        resp = client.post(f"{SANDBOX_BASE_URL}/audit-dns", json={"domain": domain})
        return resp.json() if resp.content else {"status": "error", "code": resp.status_code}


@tool("bristlecone_repair_json", args_schema=JsonRepairInput)
def bristlecone_repair_json(raw_json: str) -> dict:
    """Deterministically recovers truncated or malformed JSON payloads produced by LLMs."""
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        resp = client.post(f"{SANDBOX_BASE_URL}/repair-json", json={"raw_json": raw_json})
        return resp.json() if resp.content else {"status": "error", "code": resp.status_code}


@tool("bristlecone_eval_math", args_schema=EvalMathInput)
def bristlecone_eval_math(expression: str) -> dict:
    """Computes exact mathematical expressions inside an AST-isolated sandbox without eval()."""
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        resp = client.post(f"{SANDBOX_BASE_URL}/eval-expression", json={"expression": expression})
        return resp.json() if resp.content else {"status": "error", "code": resp.status_code}


@tool("bristlecone_xrpl_ledger")
def bristlecone_xrpl_ledger() -> dict:
    """Fetches real-time validated sequence and close time from XRPL Mainnet."""
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        resp = client.get(f"{SANDBOX_BASE_URL}/xrpl-ledger")
        return resp.json() if resp.content else {"status": "error", "code": resp.status_code}


if __name__ == "__main__":
    print(f"Testing tools against: {SANDBOX_BASE_URL}\n")
    
    # 1. Test SSRF Guard
    print("[1/3] Testing SSRF Guard against 127.0.0.1:")
    try:
        dns_res = bristlecone_dns_audit.invoke({"domain": "127.0.0.1"}) if hasattr(bristlecone_dns_audit, "invoke") else bristlecone_dns_audit("127.0.0.1")
        print(f"      Result: {dns_res}\n")
    except Exception as e:
        print(f"      Execution error: {e}\n")
    
    # 2. Test JSON Repair
    print("[2/3] Testing JSON Repair on truncated array:")
    try:
        corrupt = '{"agent": "crewai-crawler", "status": "running", "tags": ["prod", "agent"'
        json_res = bristlecone_repair_json.invoke({"raw_json": corrupt}) if hasattr(bristlecone_repair_json, "invoke") else bristlecone_repair_json(corrupt)
        print(f"      Result: {json_res}\n")
    except Exception as e:
        print(f"      Execution error: {e}\n")
    
    # 3. Test Live XRPL Ledger
    print("[3/3] Fetching live XRPL Mainnet validated ledger state:")
    try:
        ledger_res = bristlecone_xrpl_ledger.invoke({}) if hasattr(bristlecone_xrpl_ledger, "invoke") else bristlecone_xrpl_ledger()
        print(f"      Result: {ledger_res}\n")
    except Exception as e:
        print(f"      Execution error: {e}\n")
    
    print("Execution run completed.")
