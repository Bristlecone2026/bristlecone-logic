from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

try:
    from langchain_core.tools import BaseTool
except ImportError:
    raise ImportError(
        "LangChain dependencies missing. Install with: pip install 'bristlecone-logic[langchain]'"
    )

from bristlecone_logic.client import BristleconeClient


class JsonRepairInput(BaseModel):
    json_str: str = Field(..., description="Malformed or raw JSON string to sanitize and repair.")


class BristleconeJsonRepairTool(BaseTool):
    name: str = "bristlecone_repair_json"
    description: str = (
        "Deterministically repairs and parses truncated, unescaped, or malformed JSON strings "
        "into valid Python dictionary objects."
    )
    args_schema: Type[BaseModel] = JsonRepairInput
    client: Optional[BristleconeClient] = None

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.client = BristleconeClient(api_key=api_key)

    def _run(self, json_str: str) -> Dict[str, Any]:
        return self.client.repair_json(json_str)

    async def _arun(self, json_str: str) -> Dict[str, Any]:
        return await self.client.arepair_json(json_str)


class SafeEvalInput(BaseModel):
    expression: str = Field(..., description="Mathematical or logical expression to evaluate (e.g., '14 * (2.5 + 3.1)').")


class BristleconeSafeEvalTool(BaseTool):
    name: str = "bristlecone_eval_expression"
    description: str = (
        "Safely and deterministically evaluates mathematical expressions in a sandboxed AST "
        "to prevent LLM calculation hallucinations."
    )
    args_schema: Type[BaseModel] = SafeEvalInput
    client: Optional[BristleconeClient] = None

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.client = BristleconeClient(api_key=api_key)

    def _run(self, expression: str) -> Dict[str, Any]:
        return self.client.eval_expression(expression)

    async def _arun(self, expression: str) -> Dict[str, Any]:
        return await self.client.aeval_expression(expression)


class DnsAuditInput(BaseModel):
    hostname: str = Field(..., description="Target domain or hostname to audit before making outbound requests.")


class BristleconeDnsAuditTool(BaseTool):
    name: str = "bristlecone_audit_dns"
    description: str = (
        "Audits domain names for SSRF risks, private IP ranges, and DNS anomalies "
        "before allowing autonomous agent crawlers to fetch external content."
    )
    args_schema: Type[BaseModel] = DnsAuditInput
    client: Optional[BristleconeClient] = None

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.client = BristleconeClient(api_key=api_key)

    def _run(self, hostname: str) -> Dict[str, Any]:
        return self.client.audit_dns(hostname)

    async def _arun(self, hostname: str) -> Dict[str, Any]:
        return await self.client.aaudit_dns(hostname)
