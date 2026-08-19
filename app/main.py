from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from app.services.tools import (
    extract_web_content, WebExtractRequest, WebExtractResponse,
    validate_json_schema, SchemaValidateRequest, SchemaValidateResponse
)
from app.core.metering import verify_metering, create_api_key

app = FastAPI(
    title="Bristlecone Logic M2M Gateway",
    description="Deterministic compute, structured validation, and extraction microservices for autonomous AI agents.",
    version="1.0.0"
)

class RegisterRequest(BaseModel):
    tenant_name: str

@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "bristlecone-gateway", "version": "1.0.0"}

@app.get("/.well-known/agents.json")
async def agent_discovery_manifest():
    return {
        "name": "Bristlecone Logic Agent Gateway",
        "description": "Deterministic microservices, web sanitization, and structured validation for autonomous AI systems.",
        "url": "https://api.bristleconelogic.com",
        "version": "1.0.0",
        "capabilities": [
            {
                "name": "extract_web_content",
                "description": "Scrapes and sanitizes web pages into clean, LLM-ready text.",
                "endpoint": "/api/v1/tools/extract-web",
                "cost_per_call": "1 credit"
            },
            {
                "name": "validate_json_schema",
                "description": "Validates arbitrary JSON against Draft 2020-12 JSON Schemas.",
                "endpoint": "/api/v1/tools/validate-schema",
                "cost_per_call": "1 credit"
            }
        ],
        "authentication": {
            "type": "apiKey",
            "header": "X-API-Key",
            "self_registration": "/api/v1/auth/register"
        },
        "payment": {
            "protocol": "x402",
            "accepted_tokens": ["USDC"],
            "network": "Base",
            "rate": "1 credit = $0.002 USDC"
        },
        "openapi_url": "https://api.bristleconelogic.com/openapi.json"
    }

@app.post("/api/v1/auth/register")
async def register_agent(req: RegisterRequest):
    return await create_api_key(req.tenant_name)

@app.get("/api/v1/auth/balance")
async def check_balance(auth: dict = Depends(verify_metering)):
    return {"tenant": auth.get("tenant"), "credits_remaining": auth.get("credits")}

@app.post("/api/v1/tools/extract-web", response_model=WebExtractResponse)
async def api_extract_web(payload: WebExtractRequest, auth: dict = Depends(verify_metering)):
    try:
        return await extract_web_content(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/tools/validate-schema", response_model=SchemaValidateResponse)
async def api_validate_schema(payload: SchemaValidateRequest, auth: dict = Depends(verify_metering)):
    return validate_json_schema(payload)
