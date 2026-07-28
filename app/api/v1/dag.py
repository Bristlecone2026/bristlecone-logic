from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dag import CommitNode, CommitEdge
from app.schemas.dag import CommitNodeCreate, CommitNodeResponse, ProjectDAGResponse, CommitEdgeResponse
from app.services.dag_service import create_commit_node

router = APIRouter(prefix="/commits", tags=["Commit DAG Engine"])

def get_current_org_id() -> int:
    return 1  # Standard default org context for single-tenant / initial execution

@router.post("/", response_model=CommitNodeResponse, status_code=status.HTTP_201_CREATED)
def record_commit(
    commit_data: CommitNodeCreate,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Record a new execution state node in the Commit DAG."""
    node = create_commit_node(
        db=db,
        organization_id=org_id,
        project_id=commit_data.project_id,
        agent_role=commit_data.agent_role,
        payload=commit_data.payload,
        parent_ids=commit_data.parent_ids
    )
    
    parent_ids = [edge.parent_id for edge in db.query(CommitEdge).filter(CommitEdge.child_id == node.id).all()]
    
    return CommitNodeResponse(
        id=node.id,
        organization_id=node.organization_id,
        project_id=node.project_id,
        agent_role=node.agent_role,
        state_hash=node.state_hash,
        payload=node.payload,
        created_at=node.created_at,
        parent_ids=parent_ids
    )

@router.get("/project/{project_id}", response_model=ProjectDAGResponse)
def get_project_dag(
    project_id: int,
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    """Retrieve the entire DAG topology for a project."""
    nodes = db.query(CommitNode).filter(
        CommitNode.project_id == project_id,
        CommitNode.organization_id == org_id
    ).all()
    
    node_ids = [n.id for n in nodes]
    edges = db.query(CommitEdge).filter(CommitEdge.child_id.in_(node_ids)).all() if node_ids else []

    edge_map = {}
    for edge in edges:
        edge_map.setdefault(edge.child_id, []).append(edge.parent_id)

    node_responses = [
        CommitNodeResponse(
            id=n.id,
            organization_id=n.organization_id,
            project_id=n.project_id,
            agent_role=n.agent_role,
            state_hash=n.state_hash,
            payload=n.payload,
            created_at=n.created_at,
            parent_ids=edge_map.get(n.id, [])
        )
        for n in nodes
    ]

    edge_responses = [
        CommitEdgeResponse(parent_id=e.parent_id, child_id=e.child_id)
        for e in edges
    ]

    return ProjectDAGResponse(
        project_id=project_id,
        nodes=node_responses,
        edges=edge_responses
    )
