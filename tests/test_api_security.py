import pytest
import httpx

BASE_URL = "http://localhost:8000"
VALID_API_KEY = "bc_live_test_key_12345"
ADMIN_KEY = "bc_admin_master_secret_2026"

@pytest.mark.asyncio
async def test_missing_api_key_returns_401():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/api/v1/logs")
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "missing_api_key"

@pytest.mark.asyncio
async def test_invalid_api_key_returns_401():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/api/v1/logs", headers={"X-API-Key": "invalid_key_99999"})
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "invalid_api_key"

@pytest.mark.asyncio
async def test_valid_api_key_returns_200():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/api/v1/logs", headers={"X-API-Key": VALID_API_KEY})
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_admin_endpoint_forbidden_without_admin_key():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/api/v1/admin/sweep-low-balances", headers={"X-API-Key": VALID_API_KEY})
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "admin_access_required"

@pytest.mark.asyncio
async def test_admin_endpoint_success_with_admin_key():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/api/v1/admin/sweep-low-balances", headers={"X-Admin-Key": ADMIN_KEY})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
