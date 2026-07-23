from typing import Dict, Any, Tuple
from app.layer2_agent.llm_worker import LLMWorker
from app.layer3_orchestration.orchestrator import Layer3Orchestrator

class AgentEngine:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.agent_name = "Erasmus"
        self.worker = LLMWorker(model=model)
        self.orchestrator = Layer3Orchestrator(llm_worker=self.worker)

    def parse_intent(self, user_request: str) -> Dict[str, Any]:
        return self.worker.parse_intent(user_request)

    def parse_intent_to_payload(self, user_request: str) -> Tuple[str, str, Dict[str, Any]]:
        intent = self.parse_intent(user_request)
        tool_name = intent.get("tool_name", "query_ledger")
        payload_str = f"op:{tool_name}"
        return tool_name, payload_str, {"raw_intent": intent}

    def execute_task(self, user_request: str) -> Dict[str, Any]:
        res = self.orchestrator.process_agent_request(user_request=user_request)
        status = res.get("status")
        tool_executed = res.get("tool_name") if status == "SUCCESS" else None

        return {
            "status": status,
            "agent": self.agent_name,
            "tool_executed": tool_executed,
            "reason": res.get("reason"),
            "current_state": {
                "task_id": res.get("task_id"),
                "signature": res.get("signature"),
                "status": status
            },
            "processed_prompt_length": len(user_request),
            "task_id": res.get("task_id"),
            "tool_name": res.get("tool_name"),
            "signature": res.get("signature")
        }

    def process_request(self, user_request: str) -> Dict[str, Any]:
        return self.execute_task(user_request)
