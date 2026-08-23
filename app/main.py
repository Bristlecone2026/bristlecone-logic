from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.routers import agent_auth
from app.services.tools import (
    extract_web_content, WebExtractRequest, WebExtractResponse,
    validate_json_schema, SchemaValidateRequest, SchemaValidateResponse
)
from app.core.metering import verify_metering, create_api_key

app = FastAPI(
    title="Bristlecone Logic M2M Gateway",
    description="Deterministic compute, structured validation, and extraction microservices for autonomous AI agents and enterprise developers.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(agent_auth.router)

class RegisterRequest(BaseModel):
    tenant_name: str

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root_landing():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bristlecone Logic, LLC | Enterprise M2M Gateway</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 850px; margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.6; }
            h1 { color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; }
            .btn { display: inline-block; background: #2563eb; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 6px; font-weight: 600; margin-top: 10px; }
            .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 20px 0; }
            ul { margin-top: 5px; }
            code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <h1>Bristlecone Logic, LLC</h1>
        <p><strong>Autonomous Agent Microservices & Machine-to-Machine (M2M) Compute Gateway</strong></p>
        <p>Bristlecone Logic provides deterministic compute, schema validation, and web data sanitization services for autonomous AI systems, developer frameworks, and enterprise applications.</p>
        
        <div class="card">
            <h3>Interactive Developer Documentation</h3>
            <p>Explore endpoint schemas, authentication headers, request payloads, and test tools via the interactive OpenAPI portal:</p>
            <a class="btn" href="/docs" target="_blank">Open Interactive API Docs</a>
        </div>

        <div class="card">
            <h3>Machine-to-Machine Protocols</h3>
            <ul>
                <li><strong>Interactive Swagger Portal:</strong> <a href="/docs" target="_blank">https://api.bristleconelogic.com/docs</a></li>
                <li><strong>ReDoc Reference:</strong> <a href="/redoc" target="_blank">https://api.bristleconelogic.com/redoc</a></li>
                <li><strong>Agent Discovery Manifest:</strong> <a href="/.well-known/agents.json" target="_blank">/.well-known/agents.json</a></li>
                <li><strong>Raw OpenAPI Spec:</strong> <a href="/openapi.json" target="_blank">/openapi.json</a></li>
            </ul>
        </div>
        
        <p style="color: #64748b; font-size: 0.85em; margin-top: 40px;">&copy; 2026 Bristlecone Logic, LLC. All rights reserved.</p>
    </body>
    </html>
    """

@app.api_route("/api/v1/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "healthy", "service": "bristlecone-gateway", "version": "1.0.0"}

@app.api_route("/.well-known/agents.json", methods=["GET", "HEAD"])
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
            "self_registration": "/api/v1/auth/agent-register"
        },
        "payment": {
            "protocol": "x402",
            "accepted_tokens": ["USDC"],
            "network": "Base",
            "rate": "1 credit = $0.002 USDC"
        },
        "openapi_url": "https://api.bristleconelogic.com/openapi.json",
        "documentation_url": "https://api.bristleconelogic.com/docs"
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
