import json
import os
from typing import Dict, Any
from openai import OpenAI
from app.config import settings

class LLMWorker:
    """
    Layer 3 LLM Worker: Responsible ONLY for translating natural language
    into structured candidate tool calls. Holds ZERO execution authority.
    """
    def __init__(self):
        # Initializes client if key is present in settings or environment
        api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key and api_key != "your_openai_api_key_here" else None

    def propose_tool_call(self, user_input: str) -> Dict[str, Any]:
        """
        Parses user input and returns a proposed tool call payload.
        If no API key is set, returns a deterministic fallback payload.
        """
        if not self.client:
            # Deterministic off-grid fallback when API keys are absent
            return {
                "tool_name": "query_ledger" if "status" in user_input.lower() or "check" in user_input.lower() else "unauthorized_action",
                "params": {"query_text": user_input}
            }

        system_prompt = (
            "You are an isolated Layer 3 Worker node in a Zero-Trust architecture. "
            "Your ONLY job is to translate the user request into a JSON object with two fields:\n"
            "1. 'tool_name': Must be one of ['read_state', 'verify_payload', 'sign_transaction', 'query_ledger']\n"
            "2. 'params': A dictionary of parameters for the tool.\n"
            "If the request does not map to an allowed tool, return 'tool_name': 'unauthorized_action'.\n"
            "Output ONLY raw JSON."
        )

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )

        content = response.choices[0].message.content
        return json.loads(content)
