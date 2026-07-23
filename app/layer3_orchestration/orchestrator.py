from typing import Dict, Any, Optional
from app.layer3_orchestration.state_graph import StateGraph
from app.layer4_crypto.signer import sign_payload

class Layer3Orchestrator:
    def __init__(self, llm_worker=None):
        self.state_graph = StateGraph()
        self.llm_worker = llm_worker

    def _default_parse_intent(self, text: str) -> Dict[str, Any]:
        text_lower = (text or "").lower()
        if "wipe" in text_lower or "delete" in text_lower or "destroy" in text_lower:
            return {"tool_name": "unauthorized_intent", "params": {"target": "all"}}
        elif "status" in text_lower or "check" in text_lower or "ledger" in text_lower:
            return {"tool_name": "query_ledger", "params": {"query_text": text}}
        elif "read" in text_lower or "state" in text_lower:
            return {"tool_name": "read_state", "params": {}}
        elif "sign" in text_lower or "transaction" in text_lower:
            return {"tool_name": "sign_transaction", "params": {}}
        elif "verify" in text_lower or "payload" in text_lower:
            return {"tool_name": "verify_payload", "params": {}}
        else:
            return {"tool_name": "query_ledger", "params": {"query_text": text}}

    def process_agent_request(
        self, 
        user_request: Optional[str] = None, 
        tool_name: Optional[str] = None, 
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        if not tool_name:
            req_text = user_request or kwargs.get("request", "") or kwargs.get("user_request", "")
            if self.llm_worker and hasattr(self.llm_worker, "parse_intent"):
                parsed = self.llm_worker.parse_intent(req_text)
                tool_name = parsed.get("tool_name")
                params = parsed.get("params", {})
            elif self.llm_worker and hasattr(self.llm_worker, "parse_request"):
                parsed = self.llm_worker.parse_request(req_text)
                tool_name = parsed.get("tool_name")
                params = parsed.get("params", {})
            else:
                parsed = self._default_parse_intent(req_text)
                tool_name = parsed.get("tool_name")
                params = parsed.get("params", {})

        if params is None:
            params = {}

        payload_str = f"{tool_name}:{params}"
        signature = sign_payload(payload_str)

        try:
            self.state_graph.execute_tool_transition(
                tool_name=tool_name,
                params=params,
                signature=signature,
                action_data=payload_str
            )
            updated_state = self.state_graph.current_state
            return {
                "status": "SUCCESS",
                "tool_executed": tool_name,
                "params": params,
                "hmac_signature": signature,
                "reason": None,
                "updated_state": updated_state,
                "current_state": updated_state
            }
        except ValueError as e:
            return {
                "status": "REJECTED",
                "tool_executed": None,
                "params": params,
                "hmac_signature": signature,
                "reason": f"failed authorization: {e}",
                "error": str(e),
                "updated_state": self.state_graph.current_state,
                "current_state": self.state_graph.current_state
            }
