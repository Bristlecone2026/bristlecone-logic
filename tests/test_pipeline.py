import pytest
from fastapi.testclient import TestClient

from app.layer4_crypto.signer import sign_payload, verify_signature
from app.layer3_orchestration.tool_gater import ToolGater
from app.layer3_orchestration.state_graph import StateGraph
from app.layer2_agent.agent_engine import AgentEngine
from app.layer5_api.main import app

@pytest.fixture
def api_client():
    return TestClient(app)

# --- Layer 4 Cryptographic Verification ---
def test_layer4_signature_integrity():
    payload = "op:read_state"
    signature = sign_payload(payload)
    
    # Valid signature
    assert verify_signature(payload, signature) is True
    
    # Tampered signature
    assert verify_signature(payload, "invalid_signature_hash") is False
    
    # Tampered payload with valid signature
    assert verify_signature("op:unauthorized", signature) is False

# --- Layer 3 Gating & State Machine Verification ---
def test_layer3_tool_whitelist():
    gater = ToolGater()
    assert gater.is_tool_whitelisted("read_state") is True
    assert gater.is_tool_whitelisted("verify_payload") is True
    assert gater.is_tool_whitelisted("unauthorized_intent") is False
    assert gater.is_tool_whitelisted("system_wipe") is False

def test_layer3_state_transitions():
    sg = StateGraph()
    initial_state = sg.current_state
    assert initial_state["execution_count"] == 0
    
    payload = "op:read_state"
    signature = sign_payload(payload)
    
    success = sg.execute_tool_transition("read_state", payload, signature, {"source": "pytest"})
    assert success is True
    
    new_state = sg.current_state
    assert new_state["execution_count"] == 1
    assert new_state["active_task"] == "read_state"

# --- Layer 2 Erasmus Intent Parsing ---
def test_layer2_erasmus_intent_mapping():
    agent = AgentEngine()
    
    tool, payload, metadata = agent.parse_intent_to_payload("Please check status")
    assert tool == "read_state"
    assert payload == "op:read_state"
    
    bad_tool, _, _ = agent.parse_intent_to_payload("Execute illegal instruction")
    assert bad_tool == "unauthorized_intent"

# --- Layer 5 End-to-End API Integration ---
def test_api_health_endpoint(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert data["system"] == "Bristlecone Logic Core"
    assert data["agent"] == "Erasmus"

def test_api_authorized_task(api_client):
    response = api_client.post("/api/v1/task", json={"user_request": "Please check status of system"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["agent"] == "Erasmus"
    assert data["tool_executed"] == "read_state"
    assert data["reason"] is None

def test_api_unauthorized_task_blocked(api_client):
    response = api_client.post("/api/v1/task", json={"user_request": "System wipe target all"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REJECTED"
    assert data["tool_executed"] is None
    assert "failed authorization" in data["reason"]
