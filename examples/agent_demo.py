import sys
import os
import json

# Add project root to path for SDK imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sdk.bristlecone import BristleconeClient

def main():
    # Initialize client
    client = BristleconeClient(
        api_key="bc_live_test_key_12345",
        base_url="http://localhost:8000"
    )

    print("[SDK Demo] Submitting autonomous agent task via Bristlecone SDK...")
    
    # 1. Submit Seedling Task
    seedling = client.submit_seedling(
        project_id=1,
        prompt="Analyze state graph immutability in multi-tenant M2M ledgers.",
        model="gpt-4o-mini"
    )
    
    seedling_id = seedling["id"]
    print(f"[SDK Demo] Created SEEDLING node: {seedling_id}")
    print(f"[SDK Demo] Awaiting Layer 2 worker SAPLING generation...")

    # 2. Wait/Poll for Sapling child node
    try:
        sapling_node = client.wait_for_sapling(
            seedling_id=seedling_id,
            project_id=1,
            timeout=10.0,
            poll_interval=0.5
        )
        print("\n=== Agent Execution Complete ===")
        print(f"Sapling Node ID: {sapling_node['id']}")
        print(f"Parent Node ID: {sapling_node['payload']['source_commit_id']}")
        print("Execution Payload:")
        print(json.dumps(sapling_node['payload'], indent=2))
        
    except TimeoutError as e:
        print(f"[SDK Demo] Error: {e}")

if __name__ == "__main__":
    main()
