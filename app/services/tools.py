import socket
import ipaddress
from urllib.parse import urlparse, urljoin
from typing import Dict, Any, Optional, List
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from fastapi import HTTPException
import jsonschema

# --- Security Constants ---
MAX_EXTRACT_BYTES = 5 * 1024 * 1024  # 5 MB maximum payload
REQUEST_TIMEOUT_SECONDS = 8.0         # 8 second hard limit
MAX_REDIRECT_HOPS = 3                # Limit redirect chaining
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "application/json",
)

def validate_safe_url(url: str) -> str:
    """
    Validates URL scheme and resolves target hostname to ensure
    it does not point to internal, private, loopback, or metadata IP ranges.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid target URL: missing hostname.")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Could not resolve host: {hostname}")

    for item in addr_info:
        ip_str = item[4][0]
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or ip == ipaddress.ip_address("169.254.169.254")
        ):
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: Target address ({ip_str}) resolves to a restricted internal network range."
            )

    return url

class WebExtractRequest(BaseModel):
    url: str = Field(..., description="Target web page URL to scrape and sanitize.")
    include_links: bool = Field(False, description="Extract and return outbound hyperlinks.")

class WebExtractResponse(BaseModel):
    url: str
    title: str
    clean_text: str
    links: Optional[List[str]] = None

class SchemaValidateRequest(BaseModel):
    data: Dict[str, Any] = Field(..., description="The JSON data payload to validate.")
    schema_def: Dict[str, Any] = Field(..., description="Standard JSON Schema definition.")

class SchemaValidateResponse(BaseModel):
    is_valid: bool
    errors: List[str] = []
    sanitized_data: Optional[Dict[str, Any]] = None

async def extract_web_content(req: WebExtractRequest) -> WebExtractResponse:
    current_url = req.url
    html_content = ""

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECT_HOPS + 1):
            validate_safe_url(current_url)
            
            try:
                resp = await client.get(
                    current_url,
                    headers={"User-Agent": "BristleconeLogic-Agent/1.0"}
                )
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail="Upstream request timed out (8s limit).")
            except httpx.RequestError as exc:
                raise HTTPException(status_code=502, detail=f"Failed to fetch upstream target: {str(exc)}")

            if resp.is_redirect:
                location = resp.headers.get("Location")
                if not location:
                    break
                current_url = urljoin(current_url, location)
                continue

            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Target web server returned HTTP {resp.status_code}"
                )

            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type and not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported upstream Content-Type: '{content_type}'. Only text and HTML documents are processed."
                )

            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_EXTRACT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Target document exceeds maximum allowed size ({MAX_EXTRACT_BYTES / (1024 * 1024):.1f} MB)."
                )

            body_bytes = resp.content
            if len(body_bytes) > MAX_EXTRACT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Target document exceeds maximum allowed size ({MAX_EXTRACT_BYTES / (1024 * 1024):.1f} MB)."
                )

            html_content = resp.text
            break
        else:
            raise HTTPException(status_code=400, detail="Exceeded maximum allowed redirect hops (3).")

    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.string.strip() if (soup.title and soup.title.string) else ""
    text = " ".join(soup.stripped_strings)
    links = [a["href"] for a in soup.find_all("a", href=True)] if req.include_links else None

    return WebExtractResponse(url=current_url, title=title, clean_text=text, links=links)

def validate_json_schema(req: SchemaValidateRequest) -> SchemaValidateResponse:
    validator = jsonschema.Draft202012Validator(req.schema_def)
    errors = [e.message for e in validator.iter_errors(req.data)]
    return SchemaValidateResponse(
        is_valid=len(errors) == 0,
        errors=errors,
        sanitized_data=req.data if len(errors) == 0 else None
    )
