import httpx
from typing import Any, Dict, Optional

class BristleconeClient:
    """Official client SDK for Bristlecone Logic deterministic microservices."""
    def __init__(self, base_url: str = "https://api.bristleconelogic.com", tenant_id: str = "default_agent", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "x-tenant-id": tenant_id,
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def repair_json(self, raw_json: str) -> Dict[str, Any]:
        """Repair malformed LLM JSON string deterministically."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.base_url}/tools/repair-json", json={"raw_json": raw_json}, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    def eval_expression(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate mathematical and logical AST expressions."""
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(f"{self.base_url}/tools/eval-expression", json={"expression": expression}, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    def chunk_text(self, text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> Dict[str, Any]:
        """Split text with sliding-window overlap for RAG ingestion."""
        payload = {"text": text, "chunk_size": chunk_size, "chunk_overlap": chunk_overlap}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.base_url}/tools/chunk-text", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    def audit_dns(self, domain: str) -> Dict[str, Any]:
        """Inspect DNS records and SSL security headers for a domain."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.base_url}/tools/audit-dns", json={"domain": domain}, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    def extract_web(self, url: str) -> Dict[str, Any]:
        """Extract clean text content from a web page."""
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{self.base_url}/tools/extract-web", json={"url": url}, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    def validate_schema(self, schema_definition: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate payload keys against a schema definition."""
        payload = {"schema_definition": schema_definition, "data": data}
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(f"{self.base_url}/tools/validate-schema", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
