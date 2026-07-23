import logging
from typing import Dict, Any, Optional
from app.layer3_orchestration.tool_gater import ToolGater

logger = logging.getLogger("bristlecone.layer3")

class StateGraph:
    """Manages system state transitions gated by Zero Trust policy checks."""

    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        self._state: Dict[str, Any] = initial_state or {
            "status": "INITIALIZED",
            "active_task": None,
            "execution_count": 0
        }

    @property
    def current_state(self) -> Dict[str, Any]:
        """Returns a copy of the current state."""
        return self._state.copy()

    def execute_tool_transition(self, tool_name: str, payload: str, signature: str, action_data: Dict[str, Any]) -> bool:
        """
        Attempts a state transition triggered by a tool execution.
        Must pass ToolGater checks prior to mutating internal state.
        """
        if not ToolGater.validate_tool_call(tool_name, payload, signature):
            logger.error(f"State transition denied for tool: {tool_name}")
            return False

        # Apply state transition on successful validation
        self._state["active_task"] = tool_name
        self._state["execution_count"] += 1
        self._state["last_payload"] = payload
        self._state["status"] = "ACTIVE"
        self._state.update(action_data)

        logger.info(f"State transition successful via tool '{tool_name}'. Execution count: {self._state['execution_count']}")
        return True
