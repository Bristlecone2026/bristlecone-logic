import os
from typing import Any, Dict, Optional
import httpx

DEFAULT_BASE_URL = "https://api.bristleconelogic.com"


class BristleconeClient:
    """Client for interacting with Bristlecone Logic™ micro-utilities and guardrails."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or os.getenv("BRISTLECONE_API_KEY", "")
        self.base_url = (base_url or os.getenv("BRISTLECONE_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._headers = {
            "User-Agent": "bristlecone-python-sdk/0.3.0",
            "Content-Type": "application/json",
        }
        if self.api_key:
            self._headers["Authorization"] = f"Bearer {self.api_key}"

    # Synchronous methods
    def repair_json(self, json_str: str) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as client:
            res = client.post(f"{self.base_url}/repair_json", json={"json_str": json_str})
            res.raise_for_status()
            return res.json()

    def eval_expression(self, expression: str) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as client:
            res = client.post(f"{self.base_url}/eval_expression", json={"expression": expression})
            res.raise_for_status()
            return res.json()

    def audit_dns(self, hostname: str) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as client:
            res = client.post(f"{self.base_url}/audit_dns", json={"hostname": hostname})
            res.raise_for_status()
            return res.json()

    def validate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as client:
            res = client.post(f"{self.base_url}/validate_schema", json={"data": data, "schema": schema})
            res.raise_for_status()
            return res.json()

    # Asynchronous methods
    async def arepair_json(self, json_str: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client:
            res = await client.post(f"{self.base_url}/repair_json", json={"json_str": json_str})
            res.raise_for_status()
            return res.json()

    async def aeval_expression(self, expression: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client:
            res = await client.post(f"{self.base_url}/eval_expression", json={"expression": expression})
            res.raise_for_status()
            return res.json()

    async def aaudit_dns(self, hostname: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client:
            res = await client.post(f"{self.base_url}/audit_dns", json={"hostname": hostname})
            res.raise_for_status()
            return res.json()

    async def avalidate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as client:
            res = await client.post(f"{self.base_url}/validate_schema", json={"data": data, "schema": schema})
            res.raise_for_status()
            return res.json()
