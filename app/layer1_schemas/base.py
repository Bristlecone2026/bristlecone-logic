from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator

APPROVED_PREFIXES = (
    "seedling", "sapling", "ancient", 
    "cambium", "heartwood", "resin", "krummholz"
)

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
    agent_name: str = Field(..., description="Target agent node name using approved taxonomy")
    action: str = Field(..., description="Specific tool or microservice action requested")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated execution parameters")

    @field_validator("agent_name")
    @classmethod
    def validate_agent_taxonomy(cls, v: str) -> str:
        valid = any(v.startswith(f"{prefix}-") or v.startswith(f"{prefix}_") for prefix in APPROVED_PREFIXES)
        if not valid:
            prefixes_str = ", ".join(APPROVED_PREFIXES)
            raise ValueError(
                f"Invalid agent_name '{v}'. Must start with an approved taxonomy prefix "
                f"({prefixes_str}) followed by '-' or '_' (e.g., 'sapling_01' or 'resin-gate')."
            )
        return v

class AgentTaskResponse(BaseModel):
    task_id: str
    status: AgentStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
