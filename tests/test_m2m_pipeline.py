import pytest
import httpx
from unittest.mock import patch, AsyncMock
from fastapi import Header, HTTPException
from httpx import ASGITransport
from app.main import app
from app.core.security import verify_api_key

DEV_API_KEY = "bc_live_test_key_12345"

async def mock_verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    if not x_api_key or x_api_key != DEV_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return {"tenant_id": "tenant-test-123", "id": "key-test-123", "key": x_api_key}

app.dependency_overrides[verify_api_key] = mock_verify_api_key

@pytest.mark.asyncio
async def test_health_check():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_protected_logs_without_api_key():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/logs")
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_protected_logs_with_valid_api_key():
    headers = {"X-API-Key": DEV_API_KEY}
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/logs", headers=headers)
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_agent_run_valid_request():
    headers = {"X-API-Key": DEV_API_KEY}
    body = {
        "intent": "Check system status",
        "provider": "google",
        "model": "gemini-flash-latest"
    }
    with patch("app.api.v1.endpoints.agent.process_execution_billing", new_callable=AsyncMock) as mock_billing:
        mock_billing.return_value = {
            "success": True,
            "new_balance": 100.0,
            "billed_cost_usd": 0.005
        }
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/agent/run", json=body, headers=headers)
            assert response.status_code in [200, 201, 202]

@pytest.mark.asyncio
async def test_agent_run_missing_api_key_fails():
    body = {
        "intent": "Check system status",
        "provider": "google",
        "model": "gemini-flash-latest"
    }
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/agent/run", json=body)
        assert response.status_code == 401
