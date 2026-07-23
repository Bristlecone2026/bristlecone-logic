from pydantic import BaseModel
from typing import Dict, Any, Optional

class TaskRequest(BaseModel):
    user_request: str

class TaskResponse(BaseModel):
    status: str
    agent: str
    tool_executed: Optional[str] = None
    reason: Optional[str] = None
    current_state: Dict[str, Any]
    processed_prompt_length: int

class HealthResponse(BaseModel):
    status: str
    system: str
    agent: str
