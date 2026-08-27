"""
Bristlecone Logic™ - Official Python Client SDK
Deterministic Guardrails & Machine-to-Machine Utilities for Autonomous Agents.
"""

import os
from typing import Any, Dict, Optional
import httpx


class BristleconeClient:
    """Synchronous & async client for consuming Bristlecone Logic deterministic micro-tools."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        tenant_id: str = "default_agent",
        timeout: float = 10.0,
    ):
        self.base_url = (
            base_url
            or os.getenv("BRISTLECONE_BASE_URL")
            or "https://api.bristleconelogic.com"
        ).rstrip("/")
        self.api_key = api_key or os.getenv("BRISTLECONE_API_KEY")
        self.tenant_id = tenant_id
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": self.tenant_id,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def repair_json(self, raw_json: str) -> Dict[str, Any]:
        """Sanitizes and repairs malformed/truncated JSON strings."""
        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(
                f"{self.base_url}/tools/repair-json",
                json={"raw_json": raw_json},
                headers=self._headers(),
            )
            res.raise_for_status()
            return res.json()

    def validate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validates payload structures against JSON Schema definitions."""
        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(
                f"{self.base_url}/tools/validate-schema",
                json={"data": data, "schema_definition": schema},
                headers=self._headers(),
            )
            res.raise_for_status()
            return res.json()

    def eval_expression(self, expression: str) -> Dict[str, Any]:
        """Evaluates mathematical AST expressions safely in an isolated sandbox."""
        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(
                f"{self.base_url}/tools/eval-expression",
                json={"expression": expression},
                headers=self._headers(),
            )
            res.raise_for_status()
            return res.json()

    def audit_dns(self, domain: str) -> Dict[str, Any]:
        """Audits domain names against private subnets and SSRF risk vectors."""
        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(
                f"{self.base_url}/tools/audit-dns",
                json={"domain": domain},
                headers=self._headers(),
            )
            res.raise_for_status()
            return res.json()
