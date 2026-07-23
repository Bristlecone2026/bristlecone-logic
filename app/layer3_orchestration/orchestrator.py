import logging
from typing import Dict, Any
from app.layer3_orchestration.state_graph import StateGraph
from app.layer4_crypto.signer import sign_payload

logger = logging.getLogger("bristlecone.layer3")

class Layer3Orchestrator:
    """High-level dispatcher connecting LLM/agent requests to gated state transitions."""

    def __init__(self):
        self.graph = StateGraph()

    def process_agent_request(self, tool_name: str, payload: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Receives an agent request, generates an HMAC signature for the payload,
        and attempts to execute a gated state transition.
        """
        metadata = metadata or {}
        
        # Sign payload in Layer 4
        signature = sign_payload(payload)

        # Attempt transition through state graph
        success = self.graph.execute_tool_transition(tool_name, payload, signature, metadata)

        if success:
            return {
                "status": "SUCCESS",
                "tool_executed": tool_name,
                "current_state": self.graph.current_state
            }
        else:
            return {
                "status": "REJECTED",
                "reason": f"Tool '{tool_name}' failed authorization or signature check.",
                "current_state": self.graph.current_state
            }
