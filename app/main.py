import json
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

from app.routers import agent_auth
from app.services.tools import (
    extract_web_content, WebExtractRequest, WebExtractResponse,
    validate_json_schema, SchemaValidateRequest, SchemaValidateResponse
)
from app.core.metering import verify_metering, verify_api_key, create_api_key

# ---------------------------------------------------------
# Tool Definitions & Unified Execution
# ---------------------------------------------------------
TOOLS_METADATA = [
    types.Tool(
        name="extract_web",
        description="Extract and sanitize clean textual content from any target web page. SSRF-guarded.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The target HTTP/HTTPS web address to scrape."}
            },
            "required": ["url"]
        }
    ),
    types.Tool(
        name="validate_schema",
        description="Deterministically validate any JSON data against a provided JSON schema standard.",
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {"type": "object", "description": "The JSON schema to validate against."},
                "data": {"type": "object", "description": "The JSON payload to validate."}
            },
            "required": ["schema", "data"]
        }
    )
]

async def execute_mcp_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    args = arguments or {}
    if name == "extract_web":
        url = args.get("url")
        if not url:
            raise ValueError("Missing 'url' argument.")
        result = await extract_web_content(WebExtractRequest(url=url))
        return [types.TextContent(type="text", text=json.dumps(result.model_dump()))]
    elif name == "validate_schema":
        schema = args.get("schema", {})
        data = args.get("data", {})
        result = validate_json_schema(SchemaValidateRequest(schema_dict=schema, data=data))
        return [types.TextContent(type="text", text=json.dumps(result.model_dump()))]
    raise ValueError(f"Unknown MCP tool: {name}")

# ---------------------------------------------------------
# MCP Server (Stateful SSE)
# ---------------------------------------------------------
mcp_server = Server("bristlecone-logic")
sse = SseServerTransport("https://api.bristleconelogic.com/messages/")

@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return TOOLS_METADATA

@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    return await execute_mcp_tool(name, arguments)

# ---------------------------------------------------------
# Stateless JSON-RPC Handler (Streamable HTTP)
# ---------------------------------------------------------
async def handle_direct_jsonrpc(payload: dict) -> dict | None:
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "bristlecone-logic", "version": "1.0.0"}
            }
        }
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    elif method == "tools/list":
        tools_dict = [t.model_dump(by_alias=True, exclude_none=True) for t in TOOLS_METADATA]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_dict}}
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        try:
            content_objects = await execute_mcp_tool(tool_name, tool_args)
            content_list = [c.model_dump() for c in content_objects]
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": content_list, "isError": False}}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}
            }
    else:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}

# ---------------------------------------------------------
# FastAPI REST Application
# ---------------------------------------------------------
fastapi_app = FastAPI(
    title="Bristlecone Logic M2M Gateway & MCP Server",
    description="Deterministic compute, structured validation, and Model Context Protocol (MCP) tooling for AI agents.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(agent_auth.router)

class RegisterRequest(BaseModel):
    tenant_name: str

@fastapi_app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root_landing():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Bristlecone Logic, LLC | Enterprise M2M Gateway</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 850px; margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.6; }
            h1 { color: #1a365d; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; }
            .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
            code { background: #edf2f7; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
            a { color: #2b6cb0; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>Bristlecone Logic M2M Gateway</h1>
        <div class="card">
            <h3>Machine-to-Machine API Gateway & Model Context Protocol (MCP)</h3>
            <p>SSRF-guarded web extraction, JSON schema validation, and autonomous agent coordination.</p>
            <p><strong>Interactive OpenAPI Documentation:</strong> <a href="/docs">/docs</a></p>
            <p><strong>MCP Server SSE Endpoint:</strong> <code>https://api.bristleconelogic.com/sse</code></p>
        </div>
    </body>
    </html>
    """

@fastapi_app.get("/.well-known/agents.json")
async def agent_discovery():
    return {
        "name": "Bristlecone Logic M2M Gateway",
        "description": "Deterministic microservices, structured data extraction, and schema validation for autonomous AI agents.",
        "mcp_sse_url": "https://api.bristleconelogic.com/sse",
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

@fastapi_app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "service": "bristlecone-gateway", "version": "1.0.0"}

@fastapi_app.post("/api/v1/auth/register")
async def register_agent(req: RegisterRequest):
    return await create_api_key(req.tenant_name)

@fastapi_app.get("/api/v1/auth/balance")
async def check_balance(auth: dict = Depends(verify_api_key)):
    return {"tenant": auth.get("tenant"), "credits_remaining": auth.get("credits")}

@fastapi_app.post("/api/v1/tools/extract-web", response_model=WebExtractResponse)
async def api_extract_web(payload: WebExtractRequest, auth: dict = Depends(verify_metering)):
    try:
        return await extract_web_content(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@fastapi_app.post("/api/v1/tools/validate-schema", response_model=SchemaValidateResponse)
async def api_validate_schema(payload: SchemaValidateRequest, auth: dict = Depends(verify_metering)):
    return validate_json_schema(payload)

# ---------------------------------------------------------
# Unified ASGI Top-Level Transport Dispatcher
# ---------------------------------------------------------
async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "")
        method = scope.get("method", "")
        query_string = scope.get("query_string", b"").decode("utf-8")

        # 1. Global CORS Preflight
        if method == "OPTIONS" and (path.startswith("/messages") or path.startswith("/sse") or path.startswith("/api")):
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin", b"*"),
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"*"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        # 2. Stateful MCP SSE Connection Handshake
        if path == "/sse" and method == "GET":
            async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
                await mcp_server.run(
                    read_stream, write_stream, mcp_server.create_initialization_options()
                )
            return

        # 3. Message Routing (Stateful SSE Messages vs Direct Streamable HTTP JSON-RPC)
        if method == "POST" and (path.startswith("/messages") or path == "/sse"):
            if "session_id" in query_string:
                await sse.handle_post_message(scope, receive, send)
                return
            else:
                body = b""
                more_body = True
                while more_body:
                    msg = await receive()
                    body += msg.get("body", b"")
                    more_body = msg.get("more_body", False)

                try:
                    data = json.loads(body.decode("utf-8")) if body else {}
                    resp_data = await handle_direct_jsonrpc(data)
                except Exception as e:
                    resp_data = {"jsonrpc": "2.0", "error": {"code": -32700, "message": f"Parse error: {e}"}}

                if resp_data is None:
                    await send({
                        "type": "http.response.start",
                        "status": 204,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"access-control-allow-origin", b"*"),
                        ],
                    })
                    await send({"type": "http.response.body", "body": b""})
                else:
                    resp_bytes = json.dumps(resp_data).encode("utf-8")
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"access-control-allow-origin", b"*"),
                        ],
                    })
                    await send({"type": "http.response.body", "body": resp_bytes})
                return

    # 4. Standard FastAPI Route Fallthrough
    await fastapi_app(scope, receive, send)
