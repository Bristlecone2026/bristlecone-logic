from typing import Dict, Any
from app.layer3_orchestration.tool_gater import ToolGater

class StateGraph:
    def __init__(self):
        self.state = {
            "status": "INITIALIZED", 
            "history": [], 
            "execution_count": 0,
            "active_task": None
        }
        self.gater = ToolGater()

    @property
    def current_state(self) -> Dict[str, Any]:
        return self.state

    def get_state(self) -> Dict[str, Any]:
        return self.state

    def execute_tool_transition(
        self, 
        tool_name: str, 
        params: Any, 
        signature: str, 
        action_data: Any = ""
    ) -> bool:
        if isinstance(params, str):
            payload_str = params
        elif isinstance(action_data, str) and action_data:
            payload_str = action_data
        else:
            payload_str = f"{tool_name}:{params}"

        if not self.gater.validate_tool_call(tool_name, payload_str, signature):
            raise ValueError(f"State Graph rejected transition: Invalid signature or unauthorized tool '{tool_name}'")

        self.state["execution_count"] += 1
        self.state["active_task"] = tool_name
        self.state["status"] = f"EXECUTED_{tool_name.upper()}"
        self.state["history"].append({"tool": tool_name, "params": params, "signature": signature})
        return True
