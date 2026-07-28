from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dag import CommitNode
from app.schemas.dag import (
    CommitNodeCreate,
    CommitNodeResponse,
    ProjectDAGResponse,
    CommitEdgeResponse,
)
from app.services.dag_service import create_commit_node

router = APIRouter(prefix="/dag", tags=["dag"])


@router.post("/commits", response_model=CommitNodeResponse, status_code=status.HTTP_201_CREATED)
def create_commit(
    commit_in: CommitNodeCreate,
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    return create_commit_node(
        db=db,
        organization_id=organization_id,
        project_id=commit_in.project_id,
        agent_role=commit_in.agent_role,
        payload=commit_in.payload,
        parent_ids=commit_in.parent_ids
    )


@router.get("/projects/{project_id}", response_model=ProjectDAGResponse)
def get_project_dag(
    project_id: int,
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    nodes = db.query(CommitNode).filter(
        CommitNode.project_id == project_id,
        CommitNode.organization_id == organization_id
    ).all()

    edges = []
    for node in nodes:
        for parent in node.parents:
            edges.append(CommitEdgeResponse(parent_id=parent.id, child_id=node.id))

    return ProjectDAGResponse(
        project_id=project_id,
        nodes=nodes,
        edges=edges
    )
