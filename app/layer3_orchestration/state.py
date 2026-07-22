from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class GraphStatus(str, Enum):
    PENDING = "pending"
    WORKING = "working"
    INVIGILATING = "invigilating"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentState(BaseModel):
    user_goal: str
    task_draft: Optional[Dict[str, Any]] = None
    
    # Invigilator tracking
    invigilator_approved: bool = False
    rejection_reason: Optional[str] = None
    
    # Execution & Evaluation
    execution_result: Optional[Dict[str, Any]] = None
    evaluator_feedback: Optional[str] = None
    
    # Control loop safeguards
    status: GraphStatus = GraphStatus.PENDING
    iteration_count: int = 0
    max_iterations: int = 3
