import json
from app.layer3_orchestration.orchestrator import Layer3Orchestrator

def main():
    test_prompt = "Inspect the system health and query the active cluster state."
    print(f"📥 Goal Sent to Orchestrator: \"{test_prompt}\"\n")

    orchestrator = Layer3Orchestrator()
    execution_result = orchestrator.process_agent_request(user_request=test_prompt)

    print(f"🔒 Pipeline Execution Result:\n{json.dumps(execution_result, indent=2)}")

if __name__ == "__main__":
    main()
