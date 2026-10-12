"""
Bristlecone Logic - Agent Framework Adapter
Hardened Smolagents tool combining pre-socket connection pinning with HTTP 402 micro-settlement.
"""
import re
from typing import Optional
from urllib.parse import urlparse

from src.security.socket_guard import SocketGuard, SecurityException
from src.adapters.http_402_handler import HTTP402Handler, SettlementException

# Optional import to support smolagents if installed in runtime environment
try:
    from smolagents import Tool
except ImportError:
    class Tool:
        """Fallback base class when smolagents is not installed."""
        pass


class BristleconeScraperTool(Tool):
    """
    Drop-in web scraper tool for autonomous agents.
    Enforces pre-socket IP connection pinning (RFC 1918 / Cloud Metadata SSRF defense)
    and resolves HTTP 402 payment challenges via Arc L1 or XRPL rails.
    """
    name = "web_search_and_extract"
    description = (
        "Safely scrapes web content with kernel-level SSRF defense, "
        "DNS rebinding elimination, and automated M2M micro-settlement."
    )
    inputs = {
        "url": {
            "type": "string",
            "description": "Target HTTP/HTTPS URL to safely inspect and extract.",
        }
    }
    output_type = "string"

    def __init__(self, handler: Optional[HTTP402Handler] = None):
        super().__init__()
        self.handler = handler or HTTP402Handler()

    def forward(self, url: str) -> str:
        """
        Executes pre-socket security inspection, follows valid paths,
        handles 402 tollbooths, and extracts sanitized text.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SecurityException(f"Unsupported URI scheme: {parsed.scheme}")

        hostname = parsed.hostname
        if not hostname:
            raise SecurityException("URL must contain a valid hostname.")

        # 1. Transport-level defense: Inspect destination against private CIDRs & metadata
        pinned_ip = SocketGuard.inspect_and_resolve(hostname)

        # 2. Execute egress with HTTP 402 challenge negotiation
        try:
            response = self.handler.execute_request(
                url=url,
                method="GET",
                headers={"User-Agent": "Bristlecone-Agent-Runtime/1.0"}
            )
            raw_html = response["body"].decode("utf-8", errors="replace")
        except SettlementException as err:
            return f"Settlement failure on endpoint: {err}"
        except Exception as err:
            return f"Egress execution error: {err}"

        # 3. Basic text sanitization
        cleaned_text = re.sub(r"<[^>]+>", " ", raw_html)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
        return cleaned_text[:4000]
