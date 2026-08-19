import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import jsonschema

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
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        resp = await client.get(req.url, headers={"User-Agent": "BristleconeLogic-Agent/1.0"})
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else ""
    text = " ".join(soup.stripped_strings)
    links = [a["href"] for a in soup.find_all("a", href=True)] if req.include_links else None

    return WebExtractResponse(url=req.url, title=title, clean_text=text, links=links)

def validate_json_schema(req: SchemaValidateRequest) -> SchemaValidateResponse:
    validator = jsonschema.Draft202012Validator(req.schema_def)
    errors = [e.message for e in validator.iter_errors(req.data)]
    return SchemaValidateResponse(
        is_valid=len(errors) == 0,
        errors=errors,
        sanitized_data=req.data if len(errors) == 0 else None
    )
