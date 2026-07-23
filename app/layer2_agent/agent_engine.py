import logging
from typing import Dict, Any, Tuple
from app.layer2_agent.prompts import format_agent_prompt
from app.layer3_orchestration.orchestrator import Layer3Orchestrator

logger = logging.getLogger("bristlecone.layer2")

class AgentEngine:
    """
    Erasmus - Layer 2 Decision & Prompt Engine.
    Parses intent, generates structured payloads, and delegates execution to Layer 3.
    """

    def __init__(self):
        self.orchestrator = Layer3Orchestrator()
        self.agent_name = "Erasmus"

    def parse_intent_to_payload(self, user_request: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        Parses high-level user requests into concrete (tool_name, payload, metadata) tuples.
        Simple deterministic mapper for engine testing prior to live LLM binding.
        """
        req_lower = user_request.lower()

        if "read state" in req_lower or "check status" in req_lower:
            return "read_state", "op:read_state", {"source": "user_query"}
        elif "verify" in req_lower:
            return "verify_payload", "op:verify_payload", {"target": "incoming_data"}
        elif "sign" in req_lower or "transaction" in req_lower:
            return "sign_transaction", "tx_id:1001", {"amount": 100}
        elif "ledger" in req_lower or "audit" in req_lower:
            return "query_ledger", "op:query_ledger", {"filter": "recent"}
        else:
            # Fallback to an unwhitelisted tool to trigger Layer 3 rejection
            return "unauthorized_intent", "op:unauthorized", {}

    def execute_task(self, user_request: str) -> Dict[str, Any]:
        """
        Main execution pipeline for Erasmus.
        Formats prompt, extracts payload, and runs via Layer 3.
        """
        formatted_prompt = format_agent_prompt(user_request)
        tool_name, payload, metadata = self.parse_intent_to_payload(user_request)

        logger.info(f"[{self.agent_name}] Dispatching task '{tool_name}' through Layer 3 Orchestrator.")

        # Pass down to Layer 3 Orchestrator for signing & gated execution
        result = self.orchestrator.process_agent_request(
            tool_name=tool_name,
            payload=payload,
            metadata=metadata
        )

        result["agent"] = self.agent_name
        result["processed_prompt_length"] = len(formatted_prompt)
        return result
