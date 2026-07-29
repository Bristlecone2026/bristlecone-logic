from typing import List
from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.dag import CommitNode, DendroRole
from app.schemas.dag import (
    CommitNodeCreate,
    CommitNodeResponse,
    ProjectDAGResponse,
    CommitEdgeResponse,
)
from app.services.dag_service import create_commit_node
from app.workers.handlers import process_seedling_commit

router = APIRouter(prefix="/dag", tags=["dag"])


@router.post("/commits", response_model=CommitNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_commit(
    commit_in: CommitNodeCreate,
    background_tasks: BackgroundTasks,
    organization_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    node = await create_commit_node(
        db=db,
        organization_id=organization_id,
        project_id=commit_in.project_id,
        agent_role=commit_in.agent_role,
        payload=commit_in.payload,
        parent_ids=commit_in.parent_ids
    )
    
    # Layer 2 Execution Trigger: Enqueue background worker for SEEDLING nodes
    if node.agent_role == DendroRole.SEEDLING:
        background_tasks.add_task(
            process_seedling_commit,
            commit_id=node.id,
            organization_id=node.organization_id,
            project_id=node.project_id,
            payload=node.payload
        )

    return CommitNodeResponse(
        id=node.id,
        organization_id=node.organization_id,
        project_id=node.project_id,
        agent_role=node.agent_role,
        state_hash=node.state_hash,
        payload=node.payload,
        created_at=node.created_at,
        parent_ids=commit_in.parent_ids
    )


@router.get("/projects/{project_id}", response_model=ProjectDAGResponse)
async def get_project_dag(
    project_id: int,
    organization_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(CommitNode)
        .where(
            CommitNode.project_id == project_id,
            CommitNode.organization_id == organization_id
        )
        .options(selectinload(CommitNode.parents))
    )
    result = await db.execute(stmt)
    nodes = list(result.scalars().all())

    node_responses = []
    edges = []
    for node in nodes:
        parent_ids = [p.id for p in node.parents]
        node_responses.append(
            CommitNodeResponse(
                id=node.id,
                organization_id=node.organization_id,
                project_id=node.project_id,
                agent_role=node.agent_role,
                state_hash=node.state_hash,
                payload=node.payload,
                created_at=node.created_at,
                parent_ids=parent_ids
            )
        )
        for parent in node.parents:
            edges.append(CommitEdgeResponse(parent_id=parent.id, child_id=node.id))

    return ProjectDAGResponse(
        project_id=project_id,
        nodes=node_responses,
        edges=edges
    )
