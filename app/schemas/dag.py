from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.dag import DendroRole

class CommitNodeCreate(BaseModel):
    project_id: int
    agent_role: DendroRole
    payload: Dict[str, Any] = Field(default_factory=dict)
    parent_ids: List[UUID] = Field(default_factory=list)

class CommitNodeResponse(BaseModel):
    id: UUID
    organization_id: int
    project_id: int
    agent_role: DendroRole
    state_hash: str
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime
    parent_ids: List[UUID] = Field(default_factory=list)

    class Config:
        from_attributes = True

class CommitEdgeResponse(BaseModel):
    parent_id: UUID
    child_id: UUID

    class Config:
        from_attributes = True

class ProjectDAGResponse(BaseModel):
    project_id: int
    nodes: List[CommitNodeResponse]
    edges: List[CommitEdgeResponse]
