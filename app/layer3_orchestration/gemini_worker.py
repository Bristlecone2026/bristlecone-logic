import os
import json
from typing import Dict, Any
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

class GeminiWorker:
    """
    Layer 2 LLM Integration Worker for Bristlecone Logic, LLC.
    Translates natural language requests into schema-validated task intents.
    """
    def __init__(self, api_key: str | None = None, model_name: str = "gemini-flash-latest"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured in .env")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name

    def parse_intent(self, user_request: str) -> Dict[str, Any]:
        system_instruction = (
            "You are an autonomous task planner for Bristlecone Logic, LLC.\n"
            "Translate user goals into a single JSON object matching our task schema.\n"
            "RULES:\n"
            "1. 'agent_name' MUST start with an approved prefix: 'seedling', 'sapling', 'ancient', "
            "'cambium', 'heartwood', 'resin', or 'krummholz' followed by '-' or '_' (e.g., 'sapling_01').\n"
            "2. 'action' MUST be one of: 'ping', 'mcp_tool', 'read_state', 'verify_payload', 'sign_transaction', 'query_ledger'.\n"
            "3. Include a 'parameters' dictionary containing required arguments for the action."
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_request,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,
            )
        )

        raw = json.loads(response.text)

        # Normalize keys to match Layer 3 Orchestrator expectations
        return {
            "agent_name": raw.get("agent_name"),
            "tool_name": raw.get("action", "query_ledger"),
            "params": raw.get("parameters", {}),
            "raw_response": raw
        }
