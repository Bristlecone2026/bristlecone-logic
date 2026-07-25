import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.layer4_crypto.signer import PayloadSigner

client = TestClient(app)
DEV_API_KEY = "bristlecone-dev-key"

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"

def test_protected_task_without_api_key():
    response = client.get("/api/v1/protected-task")
    assert response.status_code == 403

def test_protected_task_with_valid_api_key():
    headers = {"X-API-Key": DEV_API_KEY}
    response = client.get("/api/v1/protected-task", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"

def test_task_execute_valid_signature():
    headers = {"X-API-Key": DEV_API_KEY}
    payload_data = {"data": "engine_test_run"}
    
    # Construct exact envelope expected by Layer 4 gate
    payload_to_sign = {
        "task_id": "task-test-001",
        "task_type": "data_cleaning",
        "priority": "high",
        "payload": payload_data,
    }
    
    signature = PayloadSigner.sign_payload(payload_to_sign)
    
    body = {
        "task_id": "task-test-001",
        "task_type": "data_cleaning",
        "priority": "high",
        "payload": payload_data,
        "signature": signature
    }
    
    response = client.post("/api/v1/tasks/execute", json=body, headers=headers)
    assert response.status_code in [200, 201, 202]

def test_task_execute_tampered_payload_fails():
    headers = {"X-API-Key": DEV_API_KEY}
    payload_data = {"data": "original_payload"}
    
    payload_to_sign = {
        "task_id": "task-test-002",
        "task_type": "data_cleaning",
        "priority": "high",
        "payload": payload_data,
    }
    
    signature = PayloadSigner.sign_payload(payload_to_sign)
    
    # Tamper payload without updating signature
    tampered_body = {
        "task_id": "task-test-002",
        "task_type": "data_cleaning",
        "priority": "high",
        "payload": {"data": "tampered_payload"},
        "signature": signature
    }
    
    response = client.post("/api/v1/tasks/execute", json=tampered_body, headers=headers)
    assert response.status_code == 403
