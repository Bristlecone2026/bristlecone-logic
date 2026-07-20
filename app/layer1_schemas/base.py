from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    IDLE = "idle"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class SystemHealthResponse(BaseModel):
    entity: str = Field(default="Bristlecone Logic, LLC")
    status: str = Field(default="online")
    architecture: str = Field(default="5-Layer Microservice")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentTaskRequest(BaseModel):
    task_id: str = Field(..., description="Unique identifier for the agent task")
    agent_name: str = Field(..., description="Target agent node name")
    action: str = Field(..., description="Specific tool or microservice action requested")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated execution parameters")


class AgentTaskResponse(BaseModel):
    task_id: str
    status: AgentStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
