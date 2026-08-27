from typing import Any, Dict, Optional

try:
    from crewai.tools import tool
except ImportError:
    raise ImportError(
        "CrewAI dependencies missing. Install with: pip install 'bristlecone-logic[crewai]'"
    )

from bristlecone_logic.client import BristleconeClient

_default_client: Optional[BristleconeClient] = None


def _get_client() -> BristleconeClient:
    global _default_client
    if _default_client is None:
        _default_client = BristleconeClient()
    return _default_client


@tool("Repair Broken JSON")
def repair_json_tool(json_str: str) -> Dict[str, Any]:
    """Sanitizes, fixes unclosed syntax, and parses broken JSON returned by LLM agents."""
    return _get_client().repair_json(json_str)


@tool("Deterministic Math Evaluation")
def safe_eval_tool(expression: str) -> Dict[str, Any]:
    """Evaluates mathematical formulas deterministically outside LLM context to prevent hallucinations."""
    return _get_client().eval_expression(expression)


@tool("SSRF DNS Audit")
def audit_dns_tool(hostname: str) -> Dict[str, Any]:
    """Validates target hostnames to ensure agents do not probe private network infrastructure."""
    return _get_client().audit_dns(hostname)
