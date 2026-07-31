import uuid
import pytest
from unittest.mock import MagicMock
from app.layer3_orchestration.orchestrator import Layer3Orchestrator
from app.layer3_orchestration.state_store import SQLiteStateStore

TEST_DB = "test_state.db"

def test_sqlite_task_persistence():
    mock_worker = MagicMock()
    mock_worker.parse_intent.return_value = {
        "intent_type": "SYSTEM_CHECK",
        "action": "STATUS",
        "confidence": 0.95
    }
    
    orchestrator = Layer3Orchestrator(llm_worker=mock_worker, db_path=TEST_DB)
    result = orchestrator.process_agent_request("Check engine status")
    assert result is not None

def test_sqlite_audit_trail_logging():
    store = SQLiteStateStore(db_path=TEST_DB)
    task_id = f"task-audit-{uuid.uuid4().hex[:8]}"
    store.create_task(task_id=task_id, user_request="Verify system audit trail")
    store.update_task(task_id=task_id, status="COMPLETED", reason="Audit verification run")
    
    history = store.get_audit_trail(task_id)
    assert len(history) > 0
