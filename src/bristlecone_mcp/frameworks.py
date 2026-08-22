"""
Bristlecone Logic — Python SDK & Agent Framework Wrappers
Compatible with LangChain, CrewAI, and standalone Python agents.
"""

import os
import httpx
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel, Field, ConfigDict

# Optional imports for agent frameworks
try:
    from langchain.tools import BaseTool
except ImportError:
    class BaseTool:
        pass


class ExtractWebInput(BaseModel):
    url: str = Field(..., description="The HTTP or HTTPS URL of the target web page to extract.")


class ValidateSchemaInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    json_schema: Dict[str, Any] = Field(..., alias="schema", description="The standard JSON Schema definition object.")
    data: Dict[str, Any] = Field(..., description="The JSON data payload to validate.")


class BristleconeClient:
    """Synchronous & Asynchronous HTTP Client for Bristlecone Logic API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("BRISTLECONE_API_KEY")
        self.base_url = (base_url or os.getenv("BRISTLECONE_API_URL") or "https://api.bristleconelogic.com").rstrip("/")
        if not self.api_key:
            raise ValueError("BRISTLECONE_API_KEY is required.")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def extract_web(self, url: str) -> str:
        """Extract clean text content from a web page."""
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/api/v1/tools/extract-web",
                headers=self._headers(),
                json={"url": url}
            )
            resp.raise_for_status()
            data = resp.json()
            return f"Title: {data.get('title', '')}\n\nContent:\n{data.get('content', '')}"

    def validate_schema(self, schema: Dict[str, Any], data: Dict[str, Any]) -> str:
        """Validate JSON data against a JSON schema."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{self.base_url}/api/v1/tools/validate-schema",
                headers=self._headers(),
                json={"schema": schema, "data": data}
            )
            resp.raise_for_status()
            res = resp.json()
            if res.get("valid"):
                return "Schema Validation Successful: Payload is valid."
            return f"Schema Validation Failed: {res.get('errors')}"


# --- LangChain / CrewAI Tool Classes ---

class BristleconeExtractWebTool(BaseTool):
    name: str = "bristlecone_extract_web"
    description: str = (
        "Extracts and sanitizes readable textual content from any target public web page. "
        "Useful for gathering clean web data, news articles, or documentation."
    )
    args_schema: Type[BaseModel] = ExtractWebInput
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def _run(self, url: str) -> str:
        client = BristleconeClient(api_key=self.api_key, base_url=self.base_url)
        return client.extract_web(url)


class BristleconeValidateSchemaTool(BaseTool):
    name: str = "bristlecone_validate_schema"
    description: str = (
        "Validates structured JSON data against a provided JSON Schema specification. "
        "Useful for validating intermediate reasoning steps or structured model outputs."
    )
    args_schema: Type[BaseModel] = ValidateSchemaInput
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def _run(self, schema: Dict[str, Any], data: Dict[str, Any]) -> str:
        client = BristleconeClient(api_key=self.api_key, base_url=self.base_url)
        return client.validate_schema(schema, data)
