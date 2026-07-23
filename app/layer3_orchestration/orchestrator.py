from typing import Dict, Any
from app.layer3_orchestration.llm_worker import LLMWorker
from app.layer3_orchestration.tool_gater import ToolGater
from app.layer3_orchestration.state_graph import StateGraph
from app.layer4_crypto.signer import sign_payload

class Layer3Orchestrator:
    def __init__(self):
        self.worker = LLMWorker()
        self.gater = ToolGater()
        self.state_graph = StateGraph()

    def process_agent_request(self, user_command: str) -> Dict[str, Any]:
        # 1. Ask LLM Worker to propose a tool call structure
        proposed_call = self.worker.propose_tool_call(user_command)
        tool_name = proposed_call.get("tool_name", "unknown")
        params = proposed_call.get("params", {})

        # 2. Serialize payload & generate Layer 4 HMAC Signature
        payload_str = f"{tool_name}:{params}"
        hmac_signature = sign_payload(payload_str)

        # 3. Cryptographically gate and validate against whitelist
        is_allowed = self.gater.validate_tool_call(
            tool_name=tool_name,
            payload=payload_str,
            signature=hmac_signature
        )

        if not is_allowed:
            return {
                "status": "REJECTED",
                "reason": f"Tool '{tool_name}' failed Layer 3 Whitelist or Layer 4 HMAC check.",
                "proposed_call": proposed_call,
                "current_state": self.state_graph.get_state()
            }

        # 4. Mutate State Graph cleanly upon authorized execution
        new_state = self.state_graph.execute_tool_transition(
            tool_name,
            params,
            signature=hmac_signature,
            action_data=payload_str
        )

        return {
            "status": "SUCCESS",
            "tool_executed": tool_name,
            "params": params,
            "hmac_signature": hmac_signature,
            "updated_state": new_state
        }
