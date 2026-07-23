from typing import Any
from app.layer4_crypto.signer import verify_signature

ALLOWED_TOOLS = {"read_state", "verify_payload", "sign_transaction", "query_ledger"}

class ToolGater:
    def __init__(self):
        self.allowed_tools = ALLOWED_TOOLS

    def validate_tool_call(self, tool_name: str, payload: Any, signature: str) -> bool:
        if tool_name not in self.allowed_tools:
            return False
        return verify_signature(payload, signature)
