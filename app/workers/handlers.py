import logging
from typing import Dict, Any
from uuid import UUID
from app.database import AsyncSessionLocal
from app.models.dag import DendroRole
from app.services.dag_service import create_commit_node

logger = logging.getLogger("bristlecone.workers")

async def process_seedling_commit(
    commit_id: UUID,
    organization_id: int,
    project_id: int,
    payload: Dict[str, Any]
) -> None:
    """
    Layer 2 Worker Task: Processes an incoming SEEDLING commit node
    and automatically posts a SAPLING child node with computed results.
    """
    logger.info(f"[Layer 2 Worker] Processing SEEDLING commit: {commit_id}")
    
    # Compute autonomous execution output
    output_payload = {
        "source_commit_id": str(commit_id),
        "status": "processed",
        "result": f"Autonomous execution completed for trigger input: {payload.get('status', 'unknown')}",
        "metadata": {
            "agent_engine": "bristlecone-v2-layer2-worker",
            "processed_keys": list(payload.keys())
        }
    }
    
    async with AsyncSessionLocal() as session:
        try:
            sapling_node = await create_commit_node(
                db=session,
                organization_id=organization_id,
                project_id=project_id,
                agent_role=DendroRole.SAPLING,
                payload=output_payload,
                parent_ids=[commit_id]
            )
            logger.info(
                f"[Layer 2 Worker] Successfully created SAPLING commit: {sapling_node.id} "
                f"linked to parent {commit_id}"
            )
        except Exception as e:
            logger.error(f"[Layer 2 Worker] Failed to process SEEDLING commit {commit_id}: {e}")
