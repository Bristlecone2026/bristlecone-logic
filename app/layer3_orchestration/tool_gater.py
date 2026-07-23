import logging
from app.layer4_crypto.signer import verify_signature

logger = logging.getLogger("bristlecone.layer3")

class ToolGater:
    """Enforces Zero Trust policy gates for tool execution in Layer 3."""

    ALLOWED_TOOLS = {
        "read_state",
        "verify_payload",
        "sign_transaction",
        "query_ledger"
    }

    @classmethod
    def is_tool_whitelisted(cls, tool_name: str) -> bool:
        """Validates if the tool is in the explicit execution whitelist."""
        return tool_name in cls.ALLOWED_TOOLS

    @classmethod
    def validate_tool_call(cls, tool_name: str, payload: str, signature: str) -> bool:
        """
        Validates both tool whitelist permission and cryptographic integrity.
        Returns True only if both policy checks pass.
        """
        if not cls.is_tool_whitelisted(tool_name):
            logger.warning(f"Unauthorized tool attempt blocked: {tool_name}")
            return False

        if not verify_signature(payload, signature):
            logger.warning(f"HMAC validation failed for tool call: {tool_name}")
            return False

        logger.info(f"Tool call authorized successfully: {tool_name}")
        return True
