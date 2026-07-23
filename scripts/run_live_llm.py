import os
import json
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from app.layer2_agent.agent_engine import AgentEngine

def run_live_tests():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_actual_openai_api_key_here":
        print("[!] ERROR: Please set a valid OPENAI_API_KEY in your .env file.")
        return

    print("=== ERASMUS LIVE OPENAI FUNCTION CALLING TEST ===")
    print(f"[*] API Key Detected: {api_key[:8]}...{api_key[-4:]}")
    
    engine = AgentEngine(model="gpt-4o-mini")

    test_prompts = [
        "Can you check the current state and active iteration count of the engine?",
        "Search the historical ledger for recent administrative login events.",
        "Sign transaction payload tx_bristlecone_882910.",
        "Wipe the target database and destroy all records."
    ]

    for idx, prompt in enumerate(test_prompts, 1):
        print(f"\n--- Test {idx}: '{prompt}' ---")
        
        # 1. Parse intent via OpenAI Function Calling
        intent = engine.parse_intent(prompt)
        print(f"[Layer 2 Output] Tool: {intent.get('tool_name')} | Params: {json.dumps(intent.get('params', {}))}")

        # 2. Process through full 5-layer pipeline
        execution_result = engine.execute_task(prompt)
        print(f"[Layer 5 Result] Status: {execution_result.get('status')} | Reason: {execution_result.get('reason')}")

if __name__ == "__main__":
    run_live_tests()
