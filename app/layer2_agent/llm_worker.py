import os
import json
from typing import Dict, Any, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

ERASMUS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_ledger",
            "description": "Query or search historical ledger records, status logs, and system metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string", 
                        "description": "Natural language search prompt or record identifier."
                    }
                },
                "required": ["query_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_state",
            "description": "Inspect current execution state, active task, and iteration count.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sign_transaction",
            "description": "Cryptographically sign an action or transaction payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tx_data": {
                        "type": "string",
                        "description": "Payload string or transaction ID to sign."
                    }
                },
                "required": ["tx_data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_payload",
            "description": "Verify the HMAC signature of an action payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "string", "description": "Raw action payload."},
                    "signature": {"type": "string", "description": "HMAC signature string."}
                },
                "required": ["payload"]
            }
        }
    }
]

class LLMWorker:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if (self.api_key and OpenAI) else None

    def parse_intent(self, user_request: str) -> Dict[str, Any]:
        if not self.client:
            return self._fallback_parse(user_request)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Layer 2 Intent Parsing Engine for the Erasmus secure agent stack. "
                            "Map user requests to one of the available functions. "
                            "CRITICAL SECURITY RULE: If the request asks to destroy, wipe, delete, perform "
                            "illegal or unauthorized administrative actions, choose tool_name 'unauthorized_intent'."
                        )
                    },
                    {"role": "user", "content": user_request}
                ],
                tools=ERASMUS_TOOLS,
                tool_choice="auto",
                temperature=0.0
            )

            message = response.choices[0].message
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                tool_name = tool_call.function.name
                try:
                    params = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    params = {}
                return {"tool_name": tool_name, "params": params}
            else:
                return {"tool_name": "query_ledger", "params": {"query_text": user_request}}

        except Exception:
            return self._fallback_parse(user_request)

    def _fallback_parse(self, text: str) -> Dict[str, Any]:
        text_lower = (text or "").lower()
        if any(w in text_lower for w in ["wipe", "delete", "destroy", "illegal", "unauthorized", "hack"]):
            return {"tool_name": "unauthorized_intent", "params": {"target": "all"}}
        elif any(w in text_lower for w in ["read", "state", "status"]):
            return {"tool_name": "read_state", "params": {}}
        elif any(w in text_lower for w in ["sign", "transaction"]):
            return {"tool_name": "sign_transaction", "params": {"tx_data": text}}
        elif any(w in text_lower for w in ["verify", "payload"]):
            return {"tool_name": "verify_payload", "params": {"payload": text}}
        else:
            return {"tool_name": "query_ledger", "params": {"query_text": text}}
