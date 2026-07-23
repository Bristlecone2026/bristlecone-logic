import os
import pytest
from app.layer2_agent.llm_worker import LLMWorker
from app.layer3_orchestration.orchestrator import Layer3Orchestrator
from app.layer3_orchestration.state_store import SQLiteStateStore

TEST_DB = "test_erasmus_state.db"

@pytest.fixture(autouse=True)
def cleanup_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_sqlite_task_persistence():
    orchestrator = Layer3Orchestrator(db_path=TEST_DB)
    result = orchestrator.process_agent_request("Check engine status")
    
    assert result["status"] == "SUCCESS"
    task_id = result["task_id"]

    store = SQLiteStateStore(db_path=TEST_DB)
    saved_task = store.get_task(task_id)
    
    assert saved_task is not None
    assert saved_task["task_id"] == task_id
    assert saved_task["status"] == "SUCCESS"
    assert saved_task["tool_name"] == "query_ledger"

def test_sqlite_audit_trail_logging():
    worker = LLMWorker()
    orchestrator = Layer3Orchestrator(llm_worker=worker, db_path=TEST_DB)
    result = orchestrator.process_agent_request("System wipe target all")
    
    assert result["status"] == "REJECTED"
    task_id = result["task_id"]

    store = SQLiteStateStore(db_path=TEST_DB)
    audit_trail = store.get_audit_trail(task_id)

    assert len(audit_trail) == 2
    assert audit_trail[0]["event_type"] == "TASK_CREATED"
    assert audit_trail[1]["event_type"] == "STATE_REJECTED"
