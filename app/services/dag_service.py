import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dag import CommitNode, DendroRole

def calculate_state_hash(
    project_id: int,
    agent_role: DendroRole,
    payload: Dict[str, Any],
    parent_ids: List[UUID]
) -> str:
    """Calculates a deterministic SHA-256 hash for a commit state node."""
    sorted_parents = sorted([str(pid) for pid in parent_ids])
    canonical_payload = json.dumps(payload, sort_keys=True)
    
    raw_state = f"{project_id}:{agent_role.value}:{sorted_parents}:{canonical_payload}"
    return hashlib.sha256(raw_state.encode("utf-8")).hexdigest()

async def create_commit_node(
    db: AsyncSession,
    organization_id: int,
    project_id: int,
    agent_role: DendroRole,
    payload: Dict[str, Any],
    parent_ids: List[UUID]
) -> CommitNode:
    """Creates a commit node and links parent edge relationships via Async ORM."""
    parents = []
    if parent_ids:
        stmt = select(CommitNode).where(
            CommitNode.id.in_(parent_ids),
            CommitNode.organization_id == organization_id
        )
        result = await db.execute(stmt)
        parents = list(result.scalars().all())

        if len(parents) != len(parent_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more specified parent commits do not exist or belong to another tenant."
            )

    state_hash = calculate_state_hash(project_id, agent_role, payload, parent_ids)

    node = CommitNode(
        id=uuid.uuid4(),
        organization_id=organization_id,
        project_id=project_id,
        agent_role=agent_role,
        state_hash=state_hash,
        payload=payload,
        created_at=datetime.now(timezone.utc),
        parents=parents
    )
    db.add(node)
    await db.commit()
    return node
