import uuid
from typing import Dict, Any, Optional
from app.layer3_orchestration.tool_gater import ToolGater
from app.layer3_orchestration.state_store import SQLiteStateStore
from app.layer4_crypto.signer import sign_payload, verify_signature

class Layer3Orchestrator:
    def __init__(self, llm_worker=None, db_path: str = "erasmus_state.db"):
        self.llm_worker = llm_worker
        self.tool_gater = ToolGater()
        self.state_store = SQLiteStateStore(db_path=db_path)

    def process_agent_request(self, user_request: str) -> Dict[str, Any]:
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.state_store.create_task(task_id, user_request)

        # 1. Intent Parsing (Layer 2)
        if self.llm_worker:
            intent = self.llm_worker.parse_intent(user_request)
        else:
            intent = {"tool_name": "query_ledger", "params": {"query_text": user_request}}

        tool_name = intent.get("tool_name", "query_ledger")
        
        # 2. Security Evaluation (Layer 3 Tool Gater)
        is_allowed = self.tool_gater.is_tool_whitelisted(tool_name)
        if not is_allowed:
            gate_reason = f"Tool '{tool_name}' is not in the approved whitelist (failed authorization)."
            self.state_store.update_task(task_id, status="REJECTED", tool_name=tool_name, reason=gate_reason)
            return {
                "task_id": task_id,
                "status": "REJECTED",
                "reason": gate_reason,
                "tool_name": tool_name
            }

        # 3. Signature Integrity Check (Layer 4)
        payload = f"op:{tool_name}"
        signature = sign_payload(payload)
        is_valid = verify_signature(payload, signature)

        if not is_valid:
            reason = "Cryptographic signature validation failed"
            self.state_store.update_task(task_id, status="FAILED", tool_name=tool_name, reason=reason)
            return {
                "task_id": task_id,
                "status": "FAILED",
                "reason": reason,
                "tool_name": tool_name
            }

        # 4. Successful Execution State
        self.state_store.update_task(
            task_id, 
            status="SUCCESS", 
            tool_name=tool_name, 
            reason=None, 
            payload_hash=signature[:12]
        )

        return {
            "task_id": task_id,
            "status": "SUCCESS",
            "reason": None,
            "tool_name": tool_name,
            "signature": signature
        }
