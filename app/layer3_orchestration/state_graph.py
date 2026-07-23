from typing import Dict, Any
from app.layer3_orchestration.tool_gater import ToolGater

class StateGraph:
    def __init__(self):
        self.state = {"status": "INITIALIZED", "history": []}
        self.gater = ToolGater()

    def get_state(self) -> Dict[str, Any]:
        return self.state

    def execute_tool_transition(
        self, 
        tool_name: str, 
        params: Dict[str, Any], 
        signature: str, 
        action_data: str
    ) -> Dict[str, Any]:
        payload_str = action_data if isinstance(action_data, str) else f"{tool_name}:{params}"

        # Re-verify at State Graph boundary (Zero Trust)
        if not self.gater.validate_tool_call(tool_name, payload_str, signature):
            raise ValueError(f"State Graph rejected transition: Invalid signature or unauthorized tool '{tool_name}'")

        self.state["status"] = f"EXECUTED_{tool_name.upper()}"
        self.state["history"].append({"tool": tool_name, "params": params, "signature": signature})
        return self.state
