from typing import Any
from app.layer4_crypto.signer import verify_signature

ALLOWED_TOOLS = {"read_state", "verify_payload", "sign_transaction", "query_ledger"}

class ToolGater:
    def __init__(self):
        self.allowed_tools = ALLOWED_TOOLS

    def is_tool_whitelisted(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools

    def validate_tool_call(self, tool_name: str, payload: Any, signature: str) -> bool:
        if not self.is_tool_whitelisted(tool_name):
            return False
        return verify_signature(payload, signature)
